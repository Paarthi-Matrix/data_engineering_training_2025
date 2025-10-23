import logging
from typing import Dict
import pandas as pd
import os

logger = logging.getLogger(__name__)


def clean_data(**context) -> Dict[str, pd.DataFrame]:

    try:
        ti = context["task_instance"]
        file_path = ti.xcom_pull(task_ids="task_1_read_csv", key="sales_data_path")
        logger.info(f"Retrieved file path from XCom: {file_path}")
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"Sales data file not found: {file_path}")

        logger.info(f"Loading sales data from {file_path}")
        df = pd.read_parquet(file_path)

        logger.info("Starting data cleaning process...")
        df = df.copy()

        # customer_id - convert to string and handle nulls
        df["customer_id"] = clean_customer_id_series(df["customer_id"])

        # Remove rows with missing critical data
        critical_columns = ["invoice_no", "stock_code", "quantity", "invoice_date"]
        initial_rows = len(df)
        df = df.dropna(subset=critical_columns)
        rows_dropped = initial_rows - len(df)

        if rows_dropped > 0:
            logger.warning(f"Dropped {rows_dropped} rows with missing critical data")

        logger.info(f"Data cleaning completed. {len(df)} rows remaining")

        tmp_dir = os.getenv("TEMP_DIR")
        os.makedirs(tmp_dir, exist_ok=True)
        cleaned_path = os.path.join(tmp_dir, f"cleaned_data_{context['ts_nodash']}.parquet")
        df.to_parquet(cleaned_path, index=False)
        ti.xcom_push(key="cleaned_data_path", value=cleaned_path)
        return None

    except Exception as e:
        logger.error(f"Error during data cleaning: {str(e)}")
        raise


def clean_customer_id_series(s: pd.Series) -> pd.Series:
    """Clean customer IDs by converting to consistent string format."""
    s_str = s.astype("string")
    s_num = pd.to_numeric(s_str, errors="coerce")
    mask_num = s_num.notna()
    result = s_str.copy()
    result.loc[mask_num] = s_num.loc[mask_num].astype("Int64").astype("string")
    result = result.replace({"": pd.NA})
    return result
