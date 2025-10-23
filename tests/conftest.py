"""Test configuration and fixtures for the ETL tasks."""
import os
import pytest
import pandas as pd
from datetime import datetime

@pytest.fixture
def sample_sales_data():
    """Create a small sample DataFrame for testing."""
    return pd.DataFrame({
        "invoice_no": ["INV001", "INV002", "INV003"],
        "stock_code": ["SKU001", "SKU002", "SKU003"],
        "description": ["Product 1", "Product 2", "Product 3"],
        "quantity": [1, 2, 3],
        "invoice_date": [
            datetime(2025, 1, 1),
            datetime(2025, 1, 2),
            datetime(2025, 1, 3)
        ],
        "unit_price": [10.0, 20.0, 30.0],
        "customer_id": ["CUST1", "CUST2", "CUST3"],
        "country": ["US", "UK", "CA"]
    })

@pytest.fixture
def mock_task_instance():
    """Create a mock task instance for testing XCom pulls."""
    class MockTaskInstance:
        def __init__(self):
            self.xcom_data = {}
            
        def xcom_pull(self, task_ids, key):
            return self.xcom_data.get((task_ids, key))
            
        def set_xcom_data(self, task_ids, key, value):
            self.xcom_data[(task_ids, key)] = value
            
    return MockTaskInstance()

@pytest.fixture
def mock_context(mock_task_instance):
    """Create a mock Airflow context for testing task functions."""
    return {
        "task_instance": mock_task_instance,
        "params": {"fake_rows": 0}
    }