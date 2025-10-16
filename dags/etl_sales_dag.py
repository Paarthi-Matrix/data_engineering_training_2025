from datetime import datetime
import os

from airflow import DAG
from airflow.operators.python import PythonOperator

from etl.transform import run_local_csv_etl


default_args = {
    "owner": "airflow",
    "depends_on_past": False,
    "retries": 0,
}


with DAG(
    dag_id="sales_etl_local_csv",
    start_date=datetime(2025, 1, 1),
    schedule_interval=None,
    catchup=False,
    default_args=default_args,
    tags=["sales", "etl"],
) as dag:

    run_etl = PythonOperator(
        task_id="run_local_csv_etl",
        python_callable=run_local_csv_etl,
    )

    run_etl


