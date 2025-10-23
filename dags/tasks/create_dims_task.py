import logging
from typing import Dict
import pandas as pd
from uuid import uuid4
import os

logger = logging.getLogger(__name__)


def create_date_dim(**context) -> Dict[str, pd.DataFrame]:
    """Create date dimension table."""
    try:
        ti = context["task_instance"]
        augmented_data_path = ti.xcom_pull(task_ids="task_3_add_fake_data", key="augmented_data_path")
        if not augmented_data_path or not os.path.exists(augmented_data_path):
            raise FileNotFoundError(f"Base data file not found: {augmented_data_path}")
        base_df = pd.read_parquet(augmented_data_path)

        logger.info("Creating date dimension table...")

        # Extract unique dates and create dimension
        date_dim = pd.DataFrame({"date": base_df["invoice_date"].dt.date}).drop_duplicates()
        date_ts = pd.to_datetime(date_dim["date"])

        # Add date attributes
        date_dim["year"] = date_ts.dt.year
        date_dim["month"] = date_ts.dt.month
        date_dim["day"] = date_ts.dt.day

        # Add surrogate key
        date_dim.insert(0, "date_key", [uuid4().hex for _ in range(len(date_dim))])

        logger.info(f"Created date dimension with {len(date_dim)} rows")
        tmp_dir = os.getenv("TEMP_DIR")
        os.makedirs(tmp_dir, exist_ok=True)
        date_dim_path = os.path.join(tmp_dir, f"date_dim_{context['ts_nodash']}.parquet")
        date_dim.to_parquet(date_dim_path, index=False)
        ti.xcom_push(key="date_dim_path", value=date_dim_path)
        return None

    except Exception as e:
        logger.error(f"Error creating date dimension: {str(e)}")
        raise


def create_product_dim(**context) -> Dict[str, pd.DataFrame]:
    """Create product dimension table."""
    try:
        ti = context["task_instance"]
        augmented_data_path = ti.xcom_pull(task_ids="task_3_add_fake_data", key="augmented_data_path")
        if not augmented_data_path or not os.path.exists(augmented_data_path):
            raise FileNotFoundError(f"Base data file not found: {augmented_data_path}")
        base_df = pd.read_parquet(augmented_data_path)

        logger.info("Creating product dimension table...")

        # Extract unique products
        product_dim = (
            base_df[["stock_code", "description"]]
            .drop_duplicates()
        )

        # Add surrogate key
        product_dim.insert(0, "product_id", [uuid4().hex for _ in range(len(product_dim))])

        logger.info(f"Created product dimension with {len(product_dim)} rows")
        tmp_dir = os.getenv("TEMP_DIR")
        os.makedirs(tmp_dir, exist_ok=True)
        product_dim_path = os.path.join(tmp_dir, f"product_dim_{context['ts_nodash']}.parquet")
        product_dim.to_parquet(product_dim_path, index=False)
        ti.xcom_push(key="product_dim_path", value=product_dim_path)
        return None

    except Exception as e:
        logger.error(f"Error creating product dimension: {str(e)}")
        raise


def create_customer_dim(**context) -> Dict[str, pd.DataFrame]:
    """Create customer dimension table."""
    try:
        ti = context["task_instance"]
        augmented_data_path = ti.xcom_pull(task_ids="task_3_add_fake_data", key="augmented_data_path")
        if not augmented_data_path or not os.path.exists(augmented_data_path):
            raise FileNotFoundError(f"Base data file not found: {augmented_data_path}")
        base_df = pd.read_parquet(augmented_data_path)

        logger.info("Creating customer dimension table...")

        # Extract unique customers
        customer_dim = (
            base_df[["customer_id", "country"]]
            .dropna(subset=["customer_id"])
            .drop_duplicates()
        )

        # Add surrogate key
        customer_dim.insert(0, "customer_sk", [uuid4().hex for _ in range(len(customer_dim))])

        logger.info(f"Created customer dimension with {len(customer_dim)} rows")
        tmp_dir = os.getenv("TEMP_DIR")
        os.makedirs(tmp_dir, exist_ok=True)
        customer_dim_path = os.path.join(tmp_dir, f"customer_dim_{context['ts_nodash']}.parquet")
        customer_dim.to_parquet(customer_dim_path, index=False)
        ti.xcom_push(key="customer_dim_path", value=customer_dim_path)
        return None

    except Exception as e:
        logger.error(f"Error creating customer dimension: {str(e)}")
        raise