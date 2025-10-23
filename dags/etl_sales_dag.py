from datetime import datetime

from airflow import DAG
from airflow.operators.python import PythonOperator

from tasks.read_csv_task import read_csv_data
from tasks.clean_data_task import clean_data
from tasks.add_fake_data_task import add_fake_data
from tasks.create_sales_fact_task import create_sales_fact
from tasks.create_dims_task import create_date_dim, create_product_dim, create_customer_dim
from tasks.merge_push_task import merge_and_push


# Default settings
default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 1,
}

with DAG(
    dag_id="sales_etl_local_csv",
    description="ETL pipeline for sales data with parallel dimension processing",
    start_date=datetime(2025, 1, 1),
    schedule_interval=None,  # Manual trigger only
    catchup=False,
    default_args=default_args,
    tags=["sales", "etl"],
    doc_md="""
    # Sales ETL Pipeline
    
    This DAG processes sales data through the following steps:
    1. Read and validate CSV data
    2. Clean and prepare data
    3. Add synthetic data (if configured)
    4. Create dimensions and fact tables
    5. Load data into the data warehouse
    
    ## Parallel Processing
    - The dimensions tables are built in parallel
    
    ## Configuration
    - Set FAKE_ROWS env var to add synthetic data
    - Database connection uses standard Postgres env vars
    """,
) as dag:
    
    # Task 1: Read CSV Data
    task_1_read_csv = PythonOperator(
        task_id="task_1_read_csv",
        python_callable=read_csv_data,
        doc_md="Read and validate CSV data from configured source.",
    )
    
    # Task 2: Clean Data
    task_2_clean_data = PythonOperator(
        task_id="task_2_clean_data",
        python_callable=clean_data,
        doc_md="Clean and prepare data for processing.",
    )
    
    # Task 3: Add Fake Data
    task_3_add_fake_data = PythonOperator(
        task_id="task_3_add_fake_data",
        python_callable=add_fake_data,
        doc_md="Optionally add synthetic data using Faker.",
    )

    # Tasks 4-6: Create Dimension Tables
    task_4_create_date_dim = PythonOperator(
        task_id="task_4_create_date_dim",
        python_callable=create_date_dim,
        doc_md="Create date dimension table.",
    )

    task_5_create_product_dim = PythonOperator(
        task_id="task_5_create_product_dim",
        python_callable=create_product_dim,
        doc_md="Create product dimension table.",
    )

    task_6_create_customer_dim = PythonOperator(
        task_id="task_6_create_customer_dim",
        python_callable=create_customer_dim,
        doc_md="Create customer dimension table.",
    )

    # Task 7: Create Sales Fact (runs after all dimensions)
    task_7_create_sales_fact = PythonOperator(
        task_id="task_7_create_sales_fact",
        python_callable=create_sales_fact,
        doc_md="Create initial sales fact table.",
    )

    # Task 8: Final Merge and Database Push
    task_8_merge_and_push = PythonOperator(
        task_id="task_8_merge_and_push",
        python_callable=merge_and_push,
        doc_md="Merge dimensions into fact table and load to database.",
    )

    task_1_read_csv >> task_2_clean_data >> task_3_add_fake_data
    task_3_add_fake_data >> [
        task_4_create_date_dim,
        task_5_create_product_dim,
        task_6_create_customer_dim
    ] >> task_7_create_sales_fact >> task_8_merge_and_push
