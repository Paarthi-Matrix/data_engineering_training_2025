import os
from .main_module import build_star_schema
from .read_csv_module import read_csv


def run_local_csv_etl() -> None:
    os.environ.setdefault("PGHOST", "localhost")
    os.environ.setdefault("PGPORT", "5432")
    os.environ.setdefault("PGDATABASE", "sales_gold")
    os.environ.setdefault("PGUSER", "postgres")
    os.environ.setdefault("PGPASSWORD", "Paarthi")

    df = read_csv()
    build_star_schema(df)


