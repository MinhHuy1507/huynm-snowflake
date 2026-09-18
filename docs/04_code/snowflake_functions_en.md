# Snowflake Validation and Transformation Functions (L0 to L1)
# Validation
## 1. validate_not_null
### Overview
- Generates a SQL expression to validate that a column value is not null or empty.

### Input
- `column: str | list`
- Supports validation of one or multiple columns.

### Output
- SQL text expression (`str`)

### Logic
```sql
CASE WHEN NULLIF(TRIM({col}::STRING), '') IS NULL
     THEN 'not_null({col})'
END
```

### Covered Scenarios
- `col = ''` (empty string) → `'not_null({col})'`
- `col = ' '` (whitespace only) → `'not_null({col})'`
- `col = NULL` → `'not_null({col})'`
- `col = 'Huy'` → Pass


## 2. validate_unique
### Input
- `column: str | list`
- Supports validation of one or multiple columns.

### Output
- SQL text expression (`str`)

### Covered Scenarios
- Example: validating `id`
- `id = ''`, `' '`, or `NULL` → No violation and no result returned. Null validation should be handled by `validate_not_null` if configured; otherwise, it passes.
- Duplicate `id` values → All records with duplicated values are flagged as `'unique(id)'`.

### Logic
```python
partition_expr = ", ".join(
    f"NULLIF(TRIM({col}::STRING), '')"
    for col in column
)

all_columns_present = " AND ".join(
    f"NULLIF(TRIM({col}::STRING), '') IS NOT NULL"
    for col in column
)

expr = [f"""
CASE WHEN {all_columns_present}
    AND COUNT(*) OVER(PARTITION BY {partition_expr}) > 1
    THEN 'unique({','.join(column)})'
END
"""]
```

- Supports composite key uniqueness validation across multiple columns.


## 3. validate_range
### Input
- `column: str | list`
- `min: float`
- `max: float`
### Output
- SQL text expression (`str`)
### Covered Scenarios
- `record = ''`, `' '`, or `NULL` → Pass
- `record > max` or `record < min` → `'range(col)'`

### Logic
```sql
CASE WHEN NULLIF(TRIM({col}::STRING), '') IS NOT NULL
    AND TRY_TO_DOUBLE({col}) NOT BETWEEN {min} AND {max}
THEN 'range({col})'
END
```

## 4. validate_datatype
### Input
- `table_config: dict`

### Output
- SQL text expression (`str`)

### Covered Scenarios
- `record = ''`, `' '`, or `NULL` → Pass
- Value matches the configured datatype → Pass
- Value does not match the configured datatype → `TRY_TO_*` returns `NULL` → `'datatype(col)'`

### Logic
```python
TYPE_MAPPING = {
    "integer": "TRY_TO_NUMBER({column})",
    "decimal": "TRY_TO_DECIMAL({column})",
    "date": "TRY_TO_DATE({column}{format})",
    "timestamp": "TRY_TO_TIMESTAMP({column})",
    "boolean": "TRY_TO_BOOLEAN({column})",
}
```

```python
expr_col = (
    f"CASE WHEN NULLIF(TRIM({col_name}::STRING), '') IS NOT NULL "
    f"AND {cast_expr} IS NULL THEN 'datatype({col_name})' END"
)
```

- Reads column datatypes from `table_config.yaml`.
- Maps each datatype to the corresponding Snowflake `TRY_TO_*` function.
- Snowflake returns `NULL` when the value cannot be converted to the target datatype.

## 5. validate_duplicate
### Input
- `column: str | list | None`
- `primary_key: str | list | None`
- `all_columns: list | None`

### Output
- SQL text expression (`str`)

### Covered Scenarios
- Duplicate values based on configured columns.
- First occurrence passes validation.
- Records from the second occurrence onward are flagged as `'duplicate(column_name)'`.
- Supports duplicate validation on:
  - Single column
  - Multiple columns (composite key)
  - Primary key
  - Entire record (`all_columns`) when no column is specified

### Logic
```python
subset = primary_key if primary_key is not None else column

if subset is None or subset == []:
    subset = all_columns

if isinstance(subset, str):
    subset = [subset]
```

```python
expr = [f"""
CASE
    WHEN ROW_NUMBER() OVER (
        PARTITION BY {", ".join(subset)}
        ORDER BY NULL
    ) > 1
    THEN 'duplicate({",".join(subset)})'
END
"""]
```

## 6. validate_l0_to_l1
### Overview
- Helper function that reads the table configuration (e.g., `customers_config`).
- Iterates through validation rules defined in the table YAML.
- Executes the corresponding validation functions.
- Generates a SQL view using `ARRAY_CONSTRUCT_COMPACT` to aggregate all validation errors.

### Input
- `table_config: dict`
- `schema: str`
- `obj_input: str`
- `obj_output: str`

Example:

```python
(
    customers_config,
    "retail",
    "vw_customers",
    "vw_validation_customers"
)
```

### Output
- SQL text (`str`)

### Logic
- Read validation rules in table config and create 1 sql expression, combine errors by using ARRAY_CONSTRUCT_COMPACT.
- ex: customers need validating datatype birthday and unique id
    - execute validate_datatype, output:
    ```sql
    CASE WHEN NULLIF(TRIM(birthday::STRING), '') IS NOT NULL 
        AND {TRY_TO_DATE(birthday, "YYYY-MM-dd")} IS NULL THEN 'datatype(birthday)' END
    ```
    - Read other rules and execute validate_unique. Output:
    ```sql
    CASE WHEN NULLIF(TRIM(id::STRING), '') IS NOT NULL
        AND COUNT(*) OVER(PARTITION BY NULLIF(TRIM(id::STRING), '')) > 1 THEN 'unique(id)' END
    ```
    - Combine all errors by ARRAY_CONSTRUCT_COMPACT and create 
    ```sql
    CREATE OR REPLACE TEMP TABLE retail.vw_validation_customers AS
    SELECT
        *,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN NULLIF(TRIM(birthday::STRING), '') IS NOT NULL 
                AND {TRY_TO_DATE(birthday, "YYYY-MM-dd")} IS NULL THEN 'datatype(birthday)' END,
            CASE WHEN NULLIF(TRIM(id::STRING), '') IS NOT NULL
                AND COUNT(*) OVER(PARTITION BY NULLIF(TRIM(id::STRING), '')) > 1 THEN 'unique(id)' END
        ) AS validation_errors
    FROM retail.vw_customers
    ```

### Covered Scenarios
- `birthday='2026-08-08'`, `id='C01'` (unique) → Pass
- `birthday='2026/08/08'`, `id='C02'` (unique) → `['datatype(birthday)']`
- `birthday='2026/08/08'`, `id='C03'` (duplicate) → `['datatype(birthday)', 'unique(id)']`


# Transformation
## 1. split_customers_name
### Input
- `transform_rules: dict`

Example:

```python
{
    "from": "name",
    "to": ["first_name", "last_name"]
}
```

- `column_expression: dict`

Example:

```python
{
    "id": "id",
    "name": "name",
    ...
}
```

This object is passed from `transform_l0_to_l1` and is used to build the final transformation query.

Example:

```sql
SELECT
    id AS customer_id,
    expression(first_name) AS first_name,
    expression(last_name) AS last_name
FROM ...
```

### Output

```python
column_expression = {
    "first_name":
        "NULLIF(REGEXP_SUBSTR(TRIM(name), '[^[:space:]]+$'), '')",

    "last_name":
        "NULLIF(TRIM(REGEXP_REPLACE(TRIM(name), '[^[:space:]]+$', '')), '')"
}
```

### Covered Scenarios
- `name=''`, `' '`, or `NULL` → `first_name = NULL`, `last_name = NULL`
- `name='Huy'` → `first_name='Huy'`, `last_name=NULL`
- `name='Ngo Minh Huy'` → `first_name='Huy'`, `last_name='Ngo Minh'`


## 2. split_customers_address

### Input
- `transform_rules: dict`

Example:

```python
{
    "from": "address",
    "to": ["address", "address_province"]
}
```

- `column_expression: dict`

### Output

```python
column_expression = {
    "address":
        "NULLIF(TRIM(REGEXP_REPLACE(address, ',\\\\s*[^,]+$', '')), '')",

    "address_province":
        "NULLIF(TRIM(SPLIT_PART(address, ',', -1)), '')"
}
```

### Covered Scenarios
- Case 1: `address = NULL`
  - `address = NULL`
  - `address_province = NULL`

- Case 2:
  - `"123 Nguyen Ai Quoc, Ho Chi Minh"`
  - `address = "123 Nguyen Ai Quoc"`
  - `address_province = "Ho Chi Minh"`

- Case 3:
  - `"123 Nguyen Ai Quoc"`
  - `address = "123 Nguyen Ai Quoc"`
  - `address_province = NULL`

- Case 4:
  - `"Ho Chi Minh"`
  - `address = "Ho Chi Minh"`
  - `address_province = NULL`

- Case 5:
  - `",123 Nguyen Ai Quoc, Ho Chi Minh,"`
  - `address = "123 Nguyen Ai Quoc"`
  - `address_province = "Ho Chi Minh"`


## 3. rename_columns

### Input
- `transform_rules: dict`

Example:

```python
{
    "from": "id",
    "to": "customer_id"
}
```

- `column_expression: dict`

### Output

```python
column_expression = {
    "customer_id": "id"
}
```

### Covered Scenarios
- Rename column `id` to `customer_id`.


## 4. filter_columns

### Input
- `transform_rules: dict`

Example:

```python
{
    "output": [
        "customer_id",
        "first_name",
        "last_name",
        "birthday",
        "address",
        "address_province",
        "kpi",
        "process_date",
        "source_file"
    ]
}
```

- `column_expression: dict`

### Output
- Returns only the final selected columns and expressions.


## 5. transform_l0_to_l1

### Overview
- Helper function.
- Reads the table configuration (e.g., `customers_config`).
- Iterates through transformation rules defined in the table YAML.
- Executes the corresponding transformation functions.
- Generates a transformation view that combines all configured transformations.

### Input
- `table_config: dict`
- `schema: str`
- `obj_input: str`
- `obj_output: str`
- `columns: list`

Example:

```python
(
    customers_config,
    "retail",
    "vw_customers",
    "vw_transformation_customers",
    columns=[...]
)
```

### Output
- SQL text (`str`)

### Logic

### Step 1: Initialize column expressions

```python
column_expression = {
    "id": "id",
    "name": "name",
    "birthday": "birthday",
    ...
}
```

### Step 2: Cast datatypes

Read datatypes from configuration and apply datatype mappings.

```python
CAST_MAPPING = {
    "string": "{column}",
    "integer": "CAST({column} AS INT)",
    "decimal": "CAST({column} AS DECIMAL(38,4))",
    "date": "TRY_TO_DATE({column}{format})",
    "datetime": "TRY_TO_TIMESTAMP({column})",
    "timestamp": "TRY_TO_TIMESTAMP({column})",
    "boolean": "CAST({column} AS BOOLEAN)"
}
```

Example result:

```python
column_expression = {
    "id": "id",
    "name": "name",
    "birthday": "TRY_TO_DATE(birthday, 'YYYY-MM-DD')",
    ...
}
```

### Step 3: Apply transformation rules

```python
column_expression = {
    "customer_id": "id",
    "first_name":
        "NULLIF(REGEXP_SUBSTR(TRIM(name), '[^[:space:]]+$'), '')",
    "last_name":
        "NULLIF(TRIM(REGEXP_REPLACE(TRIM(name), '[^[:space:]]+$', '')), '')",
    "birthday":
        "TRY_TO_DATE(birthday, 'YYYY-MM-DD')",
    "address":
        "NULLIF(TRIM(REGEXP_REPLACE(address, ',\\\\s*[^,]+$', '')), '')",
    "address_province":
        "NULLIF(TRIM(SPLIT_PART(address, ',', -1)), '')",
    "kpi":
        "CAST(kpi AS DECIMAL(38,4))"
}
```

### Step 4: Generate the transformation temp table

```sql
CREATE OR REPLACE TEMP TABLE retail.vw_transformation_customers AS
SELECT
    id AS customer_id,
    NULLIF(REGEXP_SUBSTR(TRIM(name), '[^[:space:]]+$'), '') AS first_name,
    NULLIF(TRIM(REGEXP_REPLACE(TRIM(name), '[^[:space:]]+$', '')), '') AS last_name,
    TRY_TO_DATE(birthday, 'YYYY-MM-DD') AS birthday,
    NULLIF(TRIM(REGEXP_REPLACE(address, ',\\s*[^,]+$', '')), '') AS address,
    NULLIF(TRIM(SPLIT_PART(address, ',', -1)), '') AS address_province,
    CAST(kpi AS DECIMAL(38,4)) AS kpi
FROM retail.vw_validation_valid_customers;
```