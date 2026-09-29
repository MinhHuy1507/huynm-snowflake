from unittest.mock import Mock, patch

import pytest

from scripts.commons.transformations import (
    split_customers_name,
    split_customers_address,
    rename_columns,
    filter_columns,
    transform_l0_to_l1,
)

TRANSFORMATION_MODULE = "scripts.commons.transformations"


def test_split_customers_name():
    column_expr = {}

    rules = [
        {
            "from": "customer_name",
            "to": ["first_name", "last_name"],
        }
    ]

    result = split_customers_name(rules, column_expr)

    assert "first_name" in result
    assert "last_name" in result
    assert "customer_name" in result["first_name"]
    assert "customer_name" in result["last_name"]


def test_split_customers_address():
    column_expr = {}

    rules = [
        {
            "from": "address",
            "to": ["full_address", "province"],
        }
    ]

    result = split_customers_address(rules, column_expr)

    assert "full_address" in result
    assert "province" in result
    assert "address" in result["full_address"]
    assert "address" in result["province"]


def test_rename_columns():
    column_expr = {}

    rules = [
        {
            "from": "cust_name",
            "to": "customer_name",
        }
    ]

    result = rename_columns(rules, column_expr)

    assert result == {
        "customer_name": "cust_name",
    }


def test_filter_columns():
    column_expr = {
        "customer_id": "customer_id",
        "customer_name": "customer_name",
        "extra_col": "extra_col",
    }

    rules = [
        {
            "output": ["customer_id", "customer_name"],
        }
    ]

    result = filter_columns(rules, column_expr)

    assert result == {
        "customer_id": "customer_id",
        "customer_name": "customer_name",
    }


def test_transform_l0_to_l1_calls_enabled_transformations():
    config = {
        "transformation": {
            "rename": [{"from": "a", "to": "b"}],
            "split_name": [{"from": "name", "to": ["first", "last"]}],
        }
    }

    target_config = {
        "columns": [
            {"name": "customer_id", "type": "integer"},
            {"name": "process_date"},
        ]
    }

    with patch(
        f"{TRANSFORMATION_MODULE}.TRANSFORM_FUNCTIONS",
        {
            "rename": Mock(return_value={"rename": "expr"}),
            "split_name": Mock(return_value={"split": "expr"}),
        },
    ) as mock_functions:

        transform_l0_to_l1(
            config=config,
            schema="TEST_SCHEMA",
            obj_input="L0_CUSTOMERS",
            obj_output="L1_CUSTOMERS",
            target_config=target_config,
        )

        mock_functions["rename"].assert_called_once()
        mock_functions["split_name"].assert_called_once()


def test_transform_l0_to_l1_returns_sql():
    config = {"transformation": {}}

    target_config = {
        "columns": [
            {"name": "customer_id", "type": "integer"},
            {"name": "customer_name", "type": "string"},
            {"name": "process_date"},
        ]
    }

    sql = transform_l0_to_l1(
        config=config,
        schema="TEST_SCHEMA",
        obj_input="L0_CUSTOMERS",
        obj_output="L1_CUSTOMERS",
        target_config=target_config,
    )

    assert "CREATE OR REPLACE TEMP TABLE TEST_SCHEMA.L1_CUSTOMERS" in sql
    assert "FROM TEST_SCHEMA.L0_CUSTOMERS" in sql
    assert "ARRAY_SIZE(validation_errors) = 0" in sql
