import logging
import os
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
import pandas as pd

logger = logging.getLogger(__name__)


def merge_and_push(**context) -> None:
    """
    Merge dimension tables into fact table and push to database.
    Gets all tables via XCom and handles database operations.
    """
    try:
        ti = context["task_instance"]

        # Pull all table file paths from XCom
        sales_fact_path = ti.xcom_pull(task_ids="task_7_create_sales_fact", key="sales_fact_path")
        date_dim_path = ti.xcom_pull(task_ids="task_4_create_date_dim", key="date_dim_path")
        product_dim_path = ti.xcom_pull(task_ids="task_5_create_product_dim", key="product_dim_path")
        customer_dim_path = ti.xcom_pull(task_ids="task_6_create_customer_dim", key="customer_dim_path")

        # Load DataFrames from Parquet files
        sales_fact = pd.read_parquet(sales_fact_path)
        logger.debug(f"sales_fact columns: {list(sales_fact.columns)}")
        date_dim = pd.read_parquet(date_dim_path)
        product_dim = pd.read_parquet(product_dim_path)
        customer_dim = pd.read_parquet(customer_dim_path)

        logger.info("Starting database operations...")

        # Get database connection
        engine = get_pg_engine()

        with engine.begin() as conn:
            # Create tables if they don't exist
            ensure_tables(conn)

            # Upsert dimensions first
            upsert_dimension(
                conn,
                table_name="product_dim",
                rows=product_dim.to_dict(orient="records"),
                pk_column="stock_code",
                delta_key_columns=["stock_code"],
                update_columns=["description"],
            )

            upsert_dimension(
                conn,
                table_name="customer_dim",
                rows=customer_dim.to_dict(orient="records"),
                pk_column="customer_id",
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

            # Get dimension mappings
            product_map = fetch_uuid_map(conn, "product_dim", key_cols=["stock_code"], uuid_col="product_id")
            customer_map = fetch_uuid_map(conn, "customer_dim", key_cols=["customer_id"], uuid_col="customer_sk")
            date_map = fetch_uuid_map(conn, "date_dim", key_cols=["date"], uuid_col="date_key")

            # Update fact table with surrogate keys
            sales_fact["product_id"] = sales_fact["stock_code"].map(lambda k: product_map.get((k,), None))
            sales_fact["customer_sk"] = sales_fact["customer_id"].map(lambda k: customer_map.get((k,), None))
            sales_fact["date_key"] = sales_fact["invoice_date"].dt.date.map(lambda k: date_map.get((k,), None))

            # Drop rows with null customer_id or customer_sk
            before_drop = len(sales_fact)
            sales_fact = sales_fact.dropna(subset=["customer_id", "customer_sk"])
            dropped = before_drop - len(sales_fact)
            if dropped > 0:
                logger.warning(f"Dropped {dropped} rows from sales_fact due to missing customer_id or customer_sk.")

            # insert fact table
            insert_fact(
                conn,
                table_name="sales_fact",
                rows=sales_fact[[
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

        logger.info("Successfully completed database operations")

    except Exception as e:
        logger.error(f"Error in merge and push operation: {str(e)}")
        raise


def get_pg_engine() -> Engine:
    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    db = os.getenv("PGDATABASE", "sales_dimensional_model")
    user = os.getenv("PGUSER", "postgres")
    pwd = os.getenv("PGPASSWORD", "Paarthi")
    url = f"postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{db}"
    return create_engine(url, future=True)


def ensure_tables(conn) -> None:
    logger.info("Creating/ensuring tables exist...")
    conn.execute(text(
        """
        CREATE TABLE IF NOT EXISTS product_dim (
            product_id UUID PRIMARY KEY,
            stock_code TEXT NOT NULL,
            description TEXT,
            CONSTRAINT uq_product_stock_code UNIQUE(stock_code)
        );

        CREATE TABLE IF NOT EXISTS customer_dim (
            customer_sk UUID PRIMARY KEY,
            customer_id TEXT NOT NULL,
            country TEXT,
            CONSTRAINT uq_customer_id UNIQUE(customer_id)
        );

        CREATE TABLE IF NOT EXISTS date_dim (
            date_key UUID PRIMARY KEY,
            date DATE NOT NULL,
            year INT,
            month INT,
            day INT,
            CONSTRAINT uq_date UNIQUE(date)
        );

        CREATE TABLE IF NOT EXISTS sales_fact (
            fact_id UUID PRIMARY KEY,
            invoice_no TEXT NOT NULL,
            stock_code TEXT NOT NULL,
            customer_id TEXT NOT NULL,
            invoice_date TIMESTAMP NOT NULL,
            quantity INT,
            unit_price FLOAT,
            product_id UUID,
            customer_sk UUID,
            date_key UUID,
            FOREIGN KEY (product_id) REFERENCES product_dim(product_id),
            FOREIGN KEY (customer_sk) REFERENCES customer_dim(customer_sk),
            FOREIGN KEY (date_key) REFERENCES date_dim(date_key)
        );
        """
    ))

def fetch_uuid_map(conn, table: str, key_cols: list, uuid_col: str) -> dict:
    """Fetch UUID mappings from a dimension table."""
    cols = ", ".join(key_cols + [uuid_col])
    rs = conn.execute(text(f"SELECT {cols} FROM {table}"))
    mapping = {}
    for row in rs.mappings():
        key = tuple(row[c] for c in key_cols)
        mapping[key] = row[uuid_col]
    return mapping


def insert_fact(conn, table_name: str, rows: list) -> None:
    """
    Insert rows into a fact table.
    Fact tables are typically append-only (no updates).
    Uses batch insert and transactional safety.
    """
    if not rows:
        logger.info(f"No rows to insert into {table_name}.")
        return

    logger.info(f"Inserting {len(rows)} new fact rows into {table_name}...")

    columns = rows[0].keys()
    col_list = ', '.join(columns)
    val_placeholders = ', '.join([f':{col}' for col in columns])

    sql = f"""
        INSERT INTO {table_name} ({col_list})
        VALUES ({val_placeholders})
    """

    for row in rows:
        conn.execute(text(sql), row)


def upsert_dimension(conn, table_name: str, rows: list,
                     pk_column: str, delta_key_columns: list,
                     update_columns: list) -> None:
    if not rows:
        return

    logger.info(f"Upserting {len(rows)} rows into {table_name}...")

    columns = rows[0].keys()
    col_list = ', '.join(columns)
    val_placeholders = ', '.join([f':{col}' for col in columns])
    update_clause = ', '.join([f'{col}=EXCLUDED.{col}' for col in update_columns])
    conflict_target = ', '.join(delta_key_columns) if delta_key_columns else pk_column

    sql = f"""
        INSERT INTO {table_name} ({col_list})
        VALUES ({val_placeholders})
        ON CONFLICT ({conflict_target})
        DO UPDATE SET {update_clause}
    """

    try:
        conn.execute(text(sql), rows)
        logger.info(f"Upsert successful for {table_name}")
    except Exception as e:
        logger.error(f"Error during upsert for {table_name}: {e}")
        raise

