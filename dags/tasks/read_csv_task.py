import os
import logging
from typing import Dict
import pandas as pd
from airflow.models import Variable

from etl.read_csv_module import read_csv

logger = logging.getLogger(__name__)


def read_csv_data(**context) -> Dict[str, pd.DataFrame]:

    try:
        logger.info("Starting CSV read operation...")
        df = read_csv()

        # Validate required columns are present
        required_columns = {
            "invoice_no", "stock_code", "description", "quantity",
            "invoice_date", "unit_price", "customer_id", "country"
        }
        missing = required_columns - set(df.columns)
        if missing:
            raise ValueError(f"Missing required columns: {sorted(missing)}")

        # Save DataFrame to Parquet file.
        tmp_dir = "/opt/airflow/tmp"
        os.makedirs(tmp_dir, exist_ok=True)
        file_path = os.path.join(tmp_dir, f"sales_data_{context['ts_nodash']}.parquet")
        df.to_parquet(file_path, index=False)

        logger.info(f"Successfully read {len(df)} rows from CSV and saved to {file_path}")
        ti = context["task_instance"]
        ti.xcom_push(key="sales_data_path", value=file_path)
        return None

    except Exception as e:
        logger.error(f"Error reading CSV data: {str(e)}")
        raise