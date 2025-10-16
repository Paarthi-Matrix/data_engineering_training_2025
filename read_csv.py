import os
import random
from faker import Faker
import pandas as pd
from dotenv import load_dotenv

load_dotenv()
fake = Faker()
csv_path = os.getenv('CSV_PATH')
fake_rows = os.getenv('FAKE_ROWS')


def read_csv():
    if not csv_path or not os.path.exists(csv_path):
        raise FileNotFoundError(f" CSV file not found or invalid path: {csv_path}")

    df = pd.read_csv(csv_path, encoding="latin1")
    print(df.dtypes)
    rename_map = {
        "InvoiceNo": "invoice_no",
        "StockCode": "stock_code",
        "Description": "description",
        "Quantity": "quantity",
        "InvoiceDate": "invoice_date",
        "UnitPrice": "unit_price",
        "CustomerID": "customer_id",
        "Country": "country"
    }
    df.rename(columns=rename_map, inplace=True)
    df = df.astype({
        "invoice_no": "string",
        "stock_code": "string",
        "description": "string",
        "customer_id": "string"
    })
    df["invoice_date"] = pd.to_datetime(df["invoice_date"])
    print(df.head(5))
    return append_fake_date(df)


def append_fake_date(df):
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

    # Combine original and fake data
    combined_df = pd.concat([df, fake_df], ignore_index=True)
    print(f"Added {fake_rows} fake rows. Total rows now: {len(combined_df):,}")
    print(combined_df.tail(10))
    return combined_df


