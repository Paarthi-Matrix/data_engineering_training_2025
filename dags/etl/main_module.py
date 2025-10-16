import os
from pathlib import Path
import pandas as pd
from uuid import uuid4
from typing import Dict, List, Tuple

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from .read_csv_module import read_csv


def build_star_schema(df: pd.DataFrame) -> None:
    project_root = Path(__file__).resolve().parents[2]

    expected_columns = {
        "invoice_no",
        "stock_code",
        "description",
        "quantity",
        "invoice_date",
        "unit_price",
        "customer_id",
        "country",
    }
    missing = expected_columns - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    df = df.copy()
    df["customer_id"] = _clean_customer_id_series(df["customer_id"])  # may introduce <NA>

    product_dim = (
        df[["stock_code", "description"]]
        .drop_duplicates()
    )
    product_dim.insert(0, "product_id", [uuid4().hex for _ in range(len(product_dim))])

    customer_dim = (
        df[["customer_id", "country"]]
        .dropna(subset=["customer_id"])  # drop null customer_ids to satisfy NOT NULL
        .drop_duplicates()
    )
    customer_dim.insert(0, "customer_sk", [uuid4().hex for _ in range(len(customer_dim))])

    date_dim = (
        pd.DataFrame({"date": df["invoice_date"].dt.date})
        .drop_duplicates()
    )
    date_ts = pd.to_datetime(date_dim["date"])
    date_dim["year"] = date_ts.dt.year
    date_dim["month"] = date_ts.dt.month
    date_dim["day"] = date_ts.dt.day
    date_dim.insert(0, "date_key", [uuid4().hex for _ in range(len(date_dim))])

    fact_df = df[[
        "invoice_no",
        "quantity",
        "unit_price",
        "stock_code",
        "description",
        "customer_id",
        "country",
        "invoice_date",
    ]].copy()
    fact_df = fact_df.dropna(subset=["customer_id"])  # avoid NOT NULL violation downstream

    fact_df = fact_df.merge(
        product_dim,
        on=["stock_code", "description"],
        how="left",
        validate="many_to_one",
    )

    fact_df = fact_df.merge(
        customer_dim,
        on=["customer_id", "country"],
        how="left",
        validate="many_to_one",
    )

    fact_df["date"] = fact_df["invoice_date"].dt.date
    fact_df = fact_df.merge(
        date_dim[["date_key", "date"]],
        on="date",
        how="left",
        validate="many_to_one",
    )

    sales_fact = fact_df[[
        "invoice_no",
        "quantity",
        "unit_price",
        "product_id",
        "customer_sk",
        "date_key",
    ]].copy()
    sales_fact.insert(0, "fact_id", [uuid4().hex for _ in range(len(sales_fact))])

    assert sales_fact["product_id"].notna().all(), "Null product_id in sales_fact"
    assert sales_fact["customer_sk"].notna().all(), "Null customer_sk in sales_fact"
    assert sales_fact["date_key"].notna().all(), "Null date_key in sales_fact"

    assert set(sales_fact["product_id"]).issubset(set(product_dim["product_id"]))
    assert set(sales_fact["customer_sk"]).issubset(set(customer_dim["customer_sk"]))
    assert set(sales_fact["date_key"]).issubset(set(date_dim["date_key"]))

    product_dim.to_csv(project_root / "product_dim.csv", index=False)
    customer_dim.to_csv(project_root / "customer_dim.csv", index=False)
    date_dim.to_csv(project_root / "date_dim.csv", index=False)
    sales_fact.to_csv(project_root / "sales_fact.csv", index=False)

    print(
        f"product_dim shape: {product_dim.shape}\n"
        f"customer_dim shape: {customer_dim.shape}\n"
        f"date_dim shape: {date_dim.shape}\n"
        f"sales_fact shape: {sales_fact.shape}"
    )

    engine = get_pg_engine()
    with engine.begin() as conn:
        ensure_tables(conn)

        upsert_dimension(
            conn,
            table_name="product_dim",
            rows=product_dim.to_dict(orient="records"),
            pk_column="product_id",
            delta_key_columns=["stock_code"],
            update_columns=["description"],
        )
        upsert_dimension(
            conn,
            table_name="customer_dim",
            rows=customer_dim.to_dict(orient="records"),
            pk_column="customer_sk",
            delta_key_columns=["customer_id"],
            update_columns=["country"],
        )
        upsert_dimension(
            conn,
            table_name="date_dim",
            rows=date_dim.to_dict(orient="records"),
            pk_column="date_key",
            delta_key_columns=["date"],
            update_columns=["year", "month", "day"],
        )

        product_map = fetch_uuid_map(conn, "product_dim", key_cols=["stock_code"], uuid_col="product_id")
        customer_map = fetch_uuid_map(conn, "customer_dim", key_cols=["customer_id"], uuid_col="customer_sk")
        date_map = fetch_uuid_map(conn, "date_dim", key_cols=["date"], uuid_col="date_key")

        fact_db = fact_df.copy()
        fact_db["product_id"] = fact_db["stock_code"].map(lambda k: product_map.get((k,), None))
        fact_db["customer_sk"] = fact_db["customer_id"].map(lambda k: customer_map.get((k,), None))
        fact_db["date_key"] = fact_db["date"].map(lambda k: date_map.get((k,), None))
        fact_db.insert(0, "fact_id", [uuid4().hex for _ in range(len(fact_db))])

        upsert_fact(
            conn,
            table_name="sales_fact",
            rows=fact_db[[
                "fact_id",
                "invoice_no",
                "stock_code",
                "customer_id",
                "invoice_date",
                "quantity",
                "unit_price",
                "product_id",
                "customer_sk",
                "date_key",
            ]].to_dict(orient="records"),
        )


def main() -> None:
    df = read_csv()
    build_star_schema(df)


def get_pg_engine() -> Engine:
    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    db = os.getenv("PGDATABASE", "sales_dimensional_model")
    user = os.getenv("PGUSER", "postgres")
    pwd = os.getenv("PGPASSWORD", "Paarthi")
    url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
    return create_engine(url, future=True)


def ensure_tables(conn) -> None:
    print("Creating/ensuring tables exist...")
    conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS product_dim (
            product_id UUID PRIMARY KEY,
            stock_code TEXT NOT NULL,
            description TEXT,
            CONSTRAINT uq_product_stock_code UNIQUE(stock_code)
        );
        """
    ))
    conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS customer_dim (
            customer_sk UUID PRIMARY KEY,
            customer_id TEXT NOT NULL,
            country TEXT,
            CONSTRAINT uq_customer_id UNIQUE(customer_id)
        );
        """
    ))
    conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS date_dim (
            date_key UUID PRIMARY KEY,
            date DATE NOT NULL,
            year INT,
            month INT,
            day INT,
            CONSTRAINT uq_date UNIQUE(date)
        );
        """
    ))
    conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS sales_fact (
            fact_id UUID PRIMARY KEY,
            invoice_no TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            invoice_date TIMESTAMP NOT NULL,
            quantity INT,
            unit_price NUMERIC,
            product_id UUID,
            customer_sk UUID,
            date_key UUID,
            CONSTRAINT uq_sales_natural UNIQUE(invoice_no, stock_code, customer_id, invoice_date),
            CONSTRAINT fk_sales_product FOREIGN KEY(product_id) REFERENCES product_dim(product_id),
            CONSTRAINT fk_sales_customer FOREIGN KEY(customer_sk) REFERENCES customer_dim(customer_sk),
            CONSTRAINT fk_sales_date FOREIGN KEY(date_key) REFERENCES date_dim(date_key)
        );
        """
    ))

    conn.execute(text(
        """
        DO $$ BEGIN
            BEGIN
                ALTER TABLE product_dim ALTER COLUMN product_id TYPE UUID USING product_id::uuid;
            EXCEPTION WHEN others THEN NULL; END;
            BEGIN
                ALTER TABLE customer_dim ALTER COLUMN customer_sk TYPE UUID USING customer_sk::uuid;
            EXCEPTION WHEN others THEN NULL; END;
            BEGIN
                ALTER TABLE date_dim ALTER COLUMN date_key TYPE UUID USING date_key::uuid;
            EXCEPTION WHEN others THEN NULL; END;
            BEGIN
                ALTER TABLE sales_fact ALTER COLUMN fact_id TYPE UUID USING fact_id::uuid;
            EXCEPTION WHEN others THEN NULL; END;
            BEGIN
                ALTER TABLE sales_fact ALTER COLUMN product_id TYPE UUID USING product_id::uuid;
            EXCEPTION WHEN others THEN NULL; END;
            BEGIN
                ALTER TABLE sales_fact ALTER COLUMN customer_sk TYPE UUID USING customer_sk::uuid;
            EXCEPTION WHEN others THEN NULL; END;
            BEGIN
                ALTER TABLE sales_fact ALTER COLUMN date_key TYPE UUID USING date_key::uuid;
            EXCEPTION WHEN others THEN NULL; END;
        END $$;
        """
    ))
    print("Tables created/verified successfully")


def upsert_dimension(
    conn,
    table_name: str,
    rows: List[Dict],
    pk_column: str,
    delta_key_columns: List[str],
    update_columns: List[str],
) -> None:
    if not rows:
        return
    print(f"Upserting {len(rows)} rows into {table_name}...")
    rows_uuid = []
    for r in rows:
        nr = dict(r)
        val = nr.get(pk_column)
        if isinstance(val, str):
            nr[pk_column] = _hyphen_uuid(val)
        rows_uuid.append(nr)
    rows_uuid = [r for r in rows_uuid if all(r.get(k) not in (None, "") for k in delta_key_columns)]

    all_columns = [pk_column] + delta_key_columns + update_columns
    placeholders = ", ".join(f":{c}" for c in all_columns)
    assignments = ", ".join(f"{c}=EXCLUDED.{c}" for c in update_columns)
    conflict_cols = ", ".join(delta_key_columns)
    sql = text(
        f"""
        INSERT INTO {table_name} ({', '.join(all_columns)})
        VALUES ({placeholders})
        ON CONFLICT ({conflict_cols}) DO UPDATE
        SET {assignments}
        """
    )
    conn.execute(sql, rows_uuid)
    print(f"Successfully upserted {len(rows_uuid)} rows into {table_name}")


def fetch_uuid_map(conn, table: str, key_cols: List[str], uuid_col: str) -> Dict[Tuple, str]:
    cols = ", ".join(key_cols + [uuid_col])
    rs = conn.execute(text(f"SELECT {cols} FROM {table}"))
    mapping: Dict[Tuple, str] = {}
    for row in rs.mappings():
        key = tuple(row[c] for c in key_cols)
        mapping[key] = row[uuid_col]
    return mapping


def upsert_fact(conn, table_name: str, rows: List[Dict]) -> None:
    if not rows:
        return
    print(f"Upserting {len(rows)} rows into {table_name}...")
    rows_uuid = []
    for r in rows:
        nr = dict(r)
        for c in ["fact_id", "product_id", "customer_sk", "date_key"]:
            val = nr.get(c)
            if isinstance(val, str):
                nr[c] = _hyphen_uuid(val)
        rows_uuid.append(nr)
    required_nk = ["invoice_no", "stock_code", "customer_id", "invoice_date"]
    rows_uuid = [r for r in rows_uuid if all(r.get(k) not in (None, "") for k in required_nk)]

    columns = [
        "fact_id",
        "invoice_no",
        "stock_code",
        "customer_id",
        "invoice_date",
        "quantity",
        "unit_price",
        "product_id",
        "customer_sk",
        "date_key",
    ]
    placeholders = ", ".join(f":{c}" for c in columns)
    assignments = ", ".join(
        f"{c}=EXCLUDED.{c}" for c in [
            "quantity",
            "unit_price",
            "product_id",
            "customer_sk",
            "date_key",
        ]
    )
    sql = text(
        f"""
        INSERT INTO {table_name} ({', '.join(columns)})
        VALUES ({placeholders})
        ON CONFLICT (invoice_no, stock_code, customer_id, invoice_date) DO UPDATE
        SET {assignments}
        """
    )
    conn.execute(sql, rows_uuid)
    print(f"Successfully upserted {len(rows_uuid)} rows into {table_name}")


def _hyphen_uuid(u: str) -> str:
    s = u.replace("-", "").lower()
    if len(s) != 32:
        return u
    return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:32]}"


def _clean_customer_id_series(s: pd.Series) -> pd.Series:
    s_str = s.astype("string")
    s_num = pd.to_numeric(s_str, errors="coerce")
    mask_num = s_num.notna()
    result = s_str.copy()
    result.loc[mask_num] = s_num.loc[mask_num].astype("Int64").astype("string")
    result = result.replace({"": pd.NA})
    return result


