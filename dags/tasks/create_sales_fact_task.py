"""Task for creating the sales fact table."""
import logging
from typing import Dict, Tuple
import pandas as pd
from uuid import uuid4
import os 

logger = logging.getLogger(__name__)

def create_sales_fact(**context) -> Dict[str, pd.DataFrame]:
    """
    Create the sales fact table from the augmented data.
    Gets data via XCom and returns fact table DataFrame.
    """
    try:
        ti = context["task_instance"]
        # Fetch base data from add_fake_data
        base_data_path = ti.xcom_pull(task_ids="task_3_add_fake_data", key="augmented_data_path")
        if not base_data_path or not os.path.exists(base_data_path):
            raise FileNotFoundError(f"Augmented data file not found: {base_data_path}")
        df = pd.read_parquet(base_data_path)

        # Fetch dimension tables from their respective tasks
        date_dim_path = ti.xcom_pull(task_ids="task_4_create_date_dim", key="date_dim_path")
        product_dim_path = ti.xcom_pull(task_ids="task_5_create_product_dim", key="product_dim_path")
        customer_dim_path = ti.xcom_pull(task_ids="task_6_create_customer_dim", key="customer_dim_path")
        if not all([date_dim_path, product_dim_path, customer_dim_path]):
            raise FileNotFoundError("One or more dimension table files not found.")
        date_dim = pd.read_parquet(date_dim_path)
        product_dim = pd.read_parquet(product_dim_path)
        customer_dim = pd.read_parquet(customer_dim_path)

        logger.info("Starting sales fact table creation...")

        # Merge dimension tables into fact table
        fact_df = df.copy()
        fact_df = fact_df.merge(product_dim, on=["stock_code", "description"], how="left", validate="many_to_one")
        fact_df = fact_df.merge(customer_dim, on=["customer_id", "country"], how="left", validate="many_to_one")
        fact_df["date"] = fact_df["invoice_date"].dt.date
        fact_df = fact_df.merge(date_dim[["date_key", "date"]], on="date", how="left", validate="many_to_one")

        # Ensure all required columns for downstream merge_and_push
        required_columns = [
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
        # Insert fact_id first
        fact_df.insert(0, "fact_id", [uuid4().hex for _ in range(len(fact_df))])
        # Select only required columns (if present)
        sales_fact = fact_df[[col for col in required_columns if col in fact_df.columns]].copy()

        logger.info(f"Created sales fact table with {len(sales_fact)} rows")

        # Save sales_fact and base_data to files
        tmp_dir = "/opt/airflow/tmp"
        os.makedirs(tmp_dir, exist_ok=True)
        sales_fact_path = os.path.join(tmp_dir, f"sales_fact_{context['ts_nodash']}.parquet")
        sales_fact.to_parquet(sales_fact_path, index=False)
        ti.xcom_push(key="sales_fact_path", value=sales_fact_path)
        return None

    except Exception as e:
        logger.error(f"Error creating sales fact table: {str(e)}")
        raise