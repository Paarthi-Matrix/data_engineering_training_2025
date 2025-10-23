"""Unit tests for the ETL task functions."""
import pytest
import pandas as pd
from datetime import datetime

from dags.tasks.read_csv_task import read_csv_data
from dags.tasks.clean_data_task import clean_data, clean_customer_id_series
from dags.tasks.add_fake_data_task import add_fake_data
from dags.tasks.create_sales_fact_task import create_sales_fact
from dags.tasks.create_dims_task import (
    create_date_dim,
    create_product_dim,
    create_customer_dim
)

def test_clean_customer_id_series():
    """Test customer ID cleaning function."""
    input_series = pd.Series(["12345", "", "67890", None])
    result = clean_customer_id_series(input_series)
    
    assert result.isna().sum() == 2  # Empty string and None should be NA
    assert result.iloc[0] == "12345"
    assert result.iloc[2] == "67890"

def test_read_csv_data_validates_columns(monkeypatch, sample_sales_data):
    """Test CSV reading validates required columns."""
    def mock_read_csv():
        return sample_sales_data.drop(columns=["invoice_no"])
    
    monkeypatch.setattr("dags.tasks.read_csv_task.read_csv", mock_read_csv)
    
    with pytest.raises(ValueError) as exc:
        read_csv_data()
    assert "Missing required columns" in str(exc.value)

def test_clean_data_removes_nulls(mock_context, sample_sales_data):
    """Test data cleaning removes rows with nulls in critical columns."""
    # Add some null values
    df = sample_sales_data.copy()
    df.loc[0, "invoice_no"] = None
    
    mock_context["task_instance"].set_xcom_data("task_1_read_csv", "sales_data", df)
    
    result = clean_data(**mock_context)
    cleaned_df = result["cleaned_data"]
    
    assert len(cleaned_df) == len(df) - 1  # One row should be removed
    assert cleaned_df["invoice_no"].isna().sum() == 0

def test_add_fake_data_respects_param(mock_context, sample_sales_data):
    """Test fake data generation respects fake_rows parameter."""
    mock_context["task_instance"].set_xcom_data(
        "task_2_clean_data", "cleaned_data", sample_sales_data
    )
    
    # Test with fake_rows = 0
    result = add_fake_data(**mock_context)
    assert len(result["augmented_data"]) == len(sample_sales_data)
    
    # Test with fake_rows = 2
    mock_context["params"]["fake_rows"] = 2
    result = add_fake_data(**mock_context)
    assert len(result["augmented_data"]) == len(sample_sales_data) + 2

def test_create_sales_fact_generates_unique_ids(mock_context, sample_sales_data):
    """Test sales fact creation generates unique IDs."""
    mock_context["task_instance"].set_xcom_data(
        "task_3_add_fake_data", "augmented_data", sample_sales_data
    )
    
    result = create_sales_fact(**mock_context)
    fact_df = result["sales_fact"]
    
    assert "fact_id" in fact_df.columns
    assert fact_df["fact_id"].nunique() == len(fact_df)

def test_dimension_table_creation(mock_context, sample_sales_data):
    """Test dimension table creation functions."""
    mock_context["task_instance"].set_xcom_data(
        "task_4_create_sales_fact", "base_data", sample_sales_data
    )
    
    # Test date dimension
    date_result = create_date_dim(**mock_context)
    date_dim = date_result["date_dim"]
    assert "date_key" in date_dim.columns
    assert "year" in date_dim.columns
    assert len(date_dim) == sample_sales_data["invoice_date"].dt.date.nunique()
    
    # Test product dimension
    product_result = create_product_dim(**mock_context)
    product_dim = product_result["product_dim"]
    assert "product_id" in product_dim.columns
    assert len(product_dim) == sample_sales_data[["stock_code", "description"]].drop_duplicates().shape[0]
    
    # Test customer dimension
    customer_result = create_customer_dim(**mock_context)
    customer_dim = customer_result["customer_dim"]
    assert "customer_sk" in customer_dim.columns
    assert len(customer_dim) == sample_sales_data[["customer_id", "country"]].drop_duplicates().shape[0]