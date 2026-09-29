import pytest
import re

from scripts.commons.validations import (
    validate_not_null,
    validate_unique,
    validate_range,
    validate_datatype,
    validate_duplicate,
)


def normalize_sql(sql: str) -> str:
    sql = " ".join(sql.split())
    sql = re.sub(r"\s*\(\s*", "(", sql)
    sql = re.sub(r"\s*\)\s*", ")", sql)
    sql = re.sub(r"\s*,\s*", ",", sql)
    return sql.strip()


# validate_not_null


@pytest.mark.parametrize(
    "column, expected",
    [
        (
            "id",
            [
                "CASE WHEN NULLIF(TRIM(id::STRING), '') IS NULL "
                "THEN 'not_null(id)' END"
            ],
        ),
        (
            ["id", "name"],
            [
                "CASE WHEN NULLIF(TRIM(id::STRING), '') IS NULL "
                "THEN 'not_null(id)' END",
                "CASE WHEN NULLIF(TRIM(name::STRING), '') IS NULL "
                "THEN 'not_null(name)' END",
            ],
        ),
    ],
)
def test_validate_not_null(column, expected):
    assert validate_not_null(column) == expected


# validate_unique


def test_validate_unique_single_column():
    result = validate_unique("id")

    expected = """
        CASE WHEN NULLIF(TRIM(id::STRING), '') IS NOT NULL
        AND COUNT(*) OVER(
            PARTITION BY NULLIF(TRIM(id::STRING), '')
        ) > 1
        THEN 'unique(id)' END
    """

    assert len(result) == 1
    assert normalize_sql(result[0]) == normalize_sql(expected)


def test_validate_unique_multiple_columns():
    result = validate_unique(["id", "name"])

    expected = """
        CASE WHEN NULLIF(TRIM(id::STRING), '') IS NOT NULL
        AND NULLIF(TRIM(name::STRING), '') IS NOT NULL
        AND COUNT(*) OVER(
            PARTITION BY
                NULLIF(TRIM(id::STRING), ''),
                NULLIF(TRIM(name::STRING), '')
        ) > 1
        THEN 'unique(id,name)' END
    """

    assert len(result) == 1
    assert normalize_sql(result[0]) == normalize_sql(expected)


# validate_range


@pytest.mark.parametrize(
    "column, minimum, maximum, expected",
    [
        (
            "kpi",
            0,
            100,
            [
                "CASE WHEN NULLIF(TRIM(kpi::STRING), '') IS NOT NULL "
                "AND TRY_TO_DOUBLE(kpi) NOT BETWEEN 0 AND 100 "
                "THEN 'range(kpi)' END"
            ],
        ),
        (
            ["age", "score"],
            0,
            10,
            [
                "CASE WHEN NULLIF(TRIM(age::STRING), '') IS NOT NULL "
                "AND TRY_TO_DOUBLE(age) NOT BETWEEN 0 AND 10 "
                "THEN 'range(age)' END",
                "CASE WHEN NULLIF(TRIM(score::STRING), '') IS NOT NULL "
                "AND TRY_TO_DOUBLE(score) NOT BETWEEN 0 AND 10 "
                "THEN 'range(score)' END",
            ],
        ),
    ],
)
def test_validate_range(column, minimum, maximum, expected):
    result = validate_range(
        column=column,
        min=minimum,
        max=maximum,
    )

    assert result == expected


# validate_duplicate


def test_validate_duplicate_with_column():
    result = validate_duplicate(column="id")

    expected = """
        CASE WHEN ROW_NUMBER() OVER (
            PARTITION BY id
            ORDER BY NULL
        ) > 1
        THEN 'duplicate(id)' END
    """

    assert len(result) == 1
    assert normalize_sql(result[0]) == normalize_sql(expected)


def test_validate_duplicate_with_multiple_columns():
    result = validate_duplicate(column=["id", "name"])

    expected = """
        CASE WHEN ROW_NUMBER() OVER (
            PARTITION BY id, name
            ORDER BY NULL
        ) > 1
        THEN 'duplicate(id,name)' END
    """

    assert len(result) == 1
    assert normalize_sql(result[0]) == normalize_sql(expected)


def test_validate_duplicate_with_primary_key():
    result = validate_duplicate(
        column=["name"],
        primary_key=["id"],
    )

    expected = """
        CASE WHEN ROW_NUMBER() OVER (
            PARTITION BY id
            ORDER BY NULL
        ) > 1
        THEN 'duplicate(id)' END
    """

    assert len(result) == 1
    assert normalize_sql(result[0]) == normalize_sql(expected)


def test_validate_duplicate_primary_key_has_priority():
    result = validate_duplicate(
        column=["name"],
        primary_key=["id", "email"],
        all_columns=["id", "name", "email"],
    )

    expected = """
        CASE WHEN ROW_NUMBER() OVER (
            PARTITION BY id, email
            ORDER BY NULL
        ) > 1
        THEN 'duplicate(id,email)' END
    """

    assert normalize_sql(result[0]) == normalize_sql(expected)


def test_validate_duplicate_empty_primary_key_uses_all_columns():
    result = validate_duplicate(
        column=["id"],
        primary_key=[],
        all_columns=["id", "name"],
    )

    expected = """
        CASE WHEN ROW_NUMBER() OVER (
            PARTITION BY id, name
            ORDER BY NULL
        ) > 1
        THEN 'duplicate(id,name)' END
    """

    assert normalize_sql(result[0]) == normalize_sql(expected)


def test_validate_duplicate_uses_all_columns():
    result = validate_duplicate(
        all_columns=["id", "name"],
    )

    expected = """
        CASE WHEN ROW_NUMBER() OVER (
            PARTITION BY id, name
            ORDER BY NULL
        ) > 1
        THEN 'duplicate(id,name)' END
    """

    assert normalize_sql(result[0]) == normalize_sql(expected)


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"column": None},
        {"column": []},
        {"column": None, "primary_key": None, "all_columns": []},
    ],
)
def test_validate_duplicate_without_columns_raises_error(kwargs):
    with pytest.raises(
        ValueError,
        match="validate_duplicate requires at least one column",
    ):
        validate_duplicate(**kwargs)


# validate_datatype


@pytest.mark.parametrize(
    "column_config, expected_cast",
    [
        (
            {"name": "age", "type": "integer"},
            "TRY_TO_NUMBER(age)",
        ),
        (
            {"name": "price", "type": "decimal"},
            "TRY_TO_DECIMAL(price)",
        ),
        (
            {"name": "created_date", "type": "date"},
            "TRY_TO_DATE(created_date)",
        ),
        (
            {
                "name": "birthday",
                "type": "date",
                "format": "YYYY-MM-DD",
            },
            "TRY_TO_DATE(birthday, 'YYYY-MM-DD')",
        ),
        (
            {"name": "created_at", "type": "timestamp"},
            "TRY_TO_TIMESTAMP(created_at)",
        ),
        (
            {"name": "is_active", "type": "boolean"},
            "TRY_TO_BOOLEAN(is_active)",
        ),
    ],
)
def test_validate_datatype_supported_types(
    column_config,
    expected_cast,
):
    config = {
        "columns": [column_config],
    }

    result = validate_datatype(config)

    column_name = column_config["name"]

    expected = (
        f"CASE WHEN NULLIF(TRIM({column_name}::STRING), '') IS NOT NULL "
        f"AND {expected_cast} IS NULL "
        f"THEN 'datatype({column_name})' END"
    )

    assert result == [expected]


def test_validate_datatype_multiple_columns():
    config = {
        "columns": [
            {
                "name": "age",
                "type": "integer",
            },
            {
                "name": "birthday",
                "type": "date",
                "format": "YYYY-MM-DD",
            },
            {
                "name": "is_active",
                "type": "boolean",
            },
        ]
    }

    result = validate_datatype(config)

    expected = [
        "CASE WHEN NULLIF(TRIM(age::STRING), '') IS NOT NULL "
        "AND TRY_TO_NUMBER(age) IS NULL "
        "THEN 'datatype(age)' END",
        "CASE WHEN NULLIF(TRIM(birthday::STRING), '') IS NOT NULL "
        "AND TRY_TO_DATE(birthday, 'YYYY-MM-DD') IS NULL "
        "THEN 'datatype(birthday)' END",
        "CASE WHEN NULLIF(TRIM(is_active::STRING), '') IS NOT NULL "
        "AND TRY_TO_BOOLEAN(is_active) IS NULL "
        "THEN 'datatype(is_active)' END",
    ]

    assert result == expected


def test_validate_datatype_unsupported_type_is_ignored():
    config = {
        "columns": [
            {
                "name": "description",
                "type": "string",
            }
        ]
    }

    result = validate_datatype(config)

    assert result == []


def test_validate_datatype_mixed_supported_and_unsupported():
    config = {
        "columns": [
            {
                "name": "description",
                "type": "string",
            },
            {
                "name": "age",
                "type": "integer",
            },
        ]
    }

    result = validate_datatype(config)

    expected = [
        "CASE WHEN NULLIF(TRIM(age::STRING), '') IS NOT NULL "
        "AND TRY_TO_NUMBER(age) IS NULL "
        "THEN 'datatype(age)' END"
    ]

    assert result == expected


def test_validate_datatype_empty_columns():
    config = {
        "columns": [],
    }

    assert validate_datatype(config) == []


def test_validate_datatype_missing_columns_key():
    with pytest.raises(KeyError):
        validate_datatype({})
