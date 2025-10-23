import logging
from typing import Dict
import pandas as pd
from faker import Faker
import random
import os

logger = logging.getLogger(__name__)
fake = Faker()


def add_fake_data(**context) -> Dict[str, pd.DataFrame]:
    try:
        ti = context["task_instance"]
        file_path = ti.xcom_pull(task_ids="task_2_clean_data", key="cleaned_data_path")
        if not file_path or not os.path.exists(file_path):
            raise FileNotFoundError(f"Cleaned data file not found: {file_path}")
        df = pd.read_parquet(file_path)

        logger.info("Starting synthetic data generation...")
        fake_rows = os.getenv("FAKE_ROWS")

        if not fake_rows:
            logger.info("No synthetic data requested, proceeding with original data")
            ti.xcom_push(key="augmented_data_path", value=file_path)
            return None

        countries = list(df["country"].unique())
        fake_data = []

        for _ in range(int(fake_rows)):
            fake_data.append({
                "invoice_no": str(random.randint(600000, 700000)),
                "stock_code": fake.bothify(text="#####?", letters="ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
                "description": fake.catch_phrase().upper(),
                "quantity": random.randint(1, 20),
                "invoice_date": fake.date_time_between(start_date="-2y", end_date="now"),
                "unit_price": round(random.uniform(1.0, 100.0), 2),
                "customer_id": str(random.randint(15000, 20000)),
                "country": random.choice(countries) if countries else fake.country()
            })

        fake_df = pd.DataFrame(fake_data)
        combined_df = pd.concat([df, fake_df], ignore_index=True)

        # Save augmented data to file
        tmp_dir = os.getenv("TEMP_DIR")
        os.makedirs(tmp_dir, exist_ok=True)
        augmented_path = os.path.join(tmp_dir, f"augmented_data_{context['ts_nodash']}.parquet")
        combined_df.to_parquet(augmented_path, index=False)
        logger.info(f"Added {len(fake_data)} synthetic records. Total rows: {len(combined_df)}. Saved to {augmented_path}")
        ti.xcom_push(key="augmented_data_path", value=augmented_path)
        return None

    except Exception as e:
        logger.error(f"Error generating synthetic data: {str(e)}")
        raise Exception
