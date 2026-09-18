# 1. Overview

Main components:

| File | Purpose |
|-|-|
| `init_snowflake.sql` | setup script: creates database/schema, storage integration to S3, and file formats |
| `init_ext_table.py` | Creates (or re-creates) all External Tables for the L0 layer based on table configs |
| `snowflake_process_stages.py` | Processes data: loads L0 data into Snowflake, validates and transforms it, and writes L1/Audit output to S3 |
| `process_rcv_to_l0.py` | Process data from rcv/ to l0/ do basic file-level and schema validation |
| `commons/sf_helper.py` | Helper functions for generating Snowflake SQL (refresh external tables, create processing scope objects, export files to stages) and creating Snowflake connections. |
| `commons/validations.py` | SQL expression generators for data validation at both levels: RCV→L0 (file validation) and L0→L1 (record validation). |
| `commons/transformations.py` | SQL expression generators for transforming L0 schema into L1 schema (type casting, column splitting, renaming, column filtering). |
| `dags/pipeline_snowflake.py` | Airflow DAG definition. Uses Python Operators to generate SQL and execute Snowflake operations. |

---

# 2. Snowflake Infrastructure Setup — `init_snowflake.sql`

This script is intended to run **once only** to provision the Snowflake infrastructure:

1. Creates `DATABASE huynm43_mp` and `SCHEMA huynm43_mp.retail` if they do not already exist.
2. Creates a **Storage Integration** named `huynm43_mp_snowflake_s3`:
   - Type: `S3`
   - Uses IAM Role: `arn:aws:iam::414061810527:role/huynm43-mp-snowflake-role`
   - Restricts access (`STORAGE_ALLOWED_LOCATIONS`) to: `l0/`, `l1/`, `audit/` within bucket `huynm43-mock-project-s3-414061810527-us-east-1-an`
   - Uses `DESC INTEGRATION` to retrieve: `STORAGE_AWS_IAM_USER_ARN`, `STORAGE_AWS_EXTERNAL_ID` for AWS IAM Trust Relationship configuration.
3. Creates two shared **File Formats**:
   - `csv_ff`: CSV, Skip header row, Supports quoted fields (`"`)
   - `parquet_ff`: PARQUET

> This script should only be executed once. Re-running it may regenerate `STORAGE_AWS_IAM_USER_ARN`, requiring updates to the AWS IAM trust relationship. Execute the SQL directly in Snowflake.

---

# 3. External Table Initialization — `init_ext_table.py`
## `create_external_table_sql(config, pattern, auto_refresh) -> str`
### Description
Generates a `CREATE OR REPLACE EXTERNAL TABLE` statement for a table based on its L0 configuration.

### Input
- `config: dict`
  - Required keys:
    - l0_format
    - table_name
    - schema_name
    - l0_stage
    - columns
- `pattern: str`
  - Regex used by Snowflake to filter files in the stage.
  - Default: `.*/[^._][^/]*\.csv$`
- `auto_refresh: bool`
  - Enables/disables `AUTO_REFRESH`.

### Output
- `str` — generated DDL statement.

### Example
- Input: config = customers_config, pattern  = '.*/[^._][^/]*\.csv$', auto_refresh=False
- Output: sql_text : str
```sql
CREATE OR REPLACE EXTERNAL TABLE retail.customers (
        id STRING AS (VALUE:c1::STRING),
        name STRING AS (VALUE:c2::STRING),
        ...,
        source_file STRING AS (METADATA$FILENAME),
        year STRING AS (SPLIT_PART(METADATA$FILENAME, '/', 4)),
        month STRING AS (SPLIT_PART(METADATA$FILENAME, '/', 5)),
        day STRING AS (SPLIT_PART(METADATA$FILENAME, '/', 6)),
    )
    PARTITION BY (year, month, day)
    LOCATION = @stage_l0/retail/customers
    PATTERN = '.*/[^._][^/]*\.csv$'
    FILE_FORMAT = parquet_ff
    AUTO_REFRESH = False;
```

### Logic
- Only supports:
  - `csv` → `csv_ff`
  - `parquet` → `parquet_ff`
- Any other format raises `ValueError`.
- csv mapping columns: columns are mapped by **position**

```sql
VALUE:c1
VALUE:c2
VALUE:c3
```

- parquet mapping columns: columns are mapped by **column name**:

```sql
VALUE:{column_name}
```

- All raw columns are stored as `STRING`. Actual business-type casting occurs later during L0→L1 transformation.
- Four metadata columns are always added:

```sql
-- The values of `year/month/day` are extracted from `METADATA$FILENAME`.
source_file = METADATA$FILENAME
year
month
day
```

- Location:

```sql
@{stage_name}/{schema_name}/{table_name}/
```

---

# 4. Snowflake Helper Functions — `sf_helper.py`

## 4.1. `get_conn(user, password, account, warehouse, database, schema)`

A thin wrapper around:

```python
snowflake.connector.connect(...)
```

Returns a Snowflake connection object.

## 4.2. `refresh_external_table(schema_name, ext_name, process_date) -> str`

Generates:

```sql
ALTER EXTERNAL TABLE {schema_name}.{ext_name}
REFRESH '{process_date}';
```

Purpose: Force Snowflake to refresh metadata for a specific partition path before querying newly uploaded files.

---

## 4.3. `create_process_scope(schema_name, table_name, process_date, object_name, is_temporary=False) -> str`

### Description

Creates a snapshot object containing data from a **single partition date**, and appends a processing timestamp column.

### Input
- schema_name: str
- table_name: str
- process_date: str. Required format: YYYY/MM/DD
- object_name: str. 
- is_temporary: bool
  - `True` → TEMP TABLE
  - `False` → Permanent TABLE

### Output
- sql text: str

### Example
- Input: schema_name=retail, table_name=customers, process_date="2026/09/17", object_name="customers_runId", is_temporary=False
- Output: sql_text : str
```sql
    CREATE OR REPLACE TABLE retail.customers_runId AS
    SELECT *,
        CAST(CURRENT_TIMESTAMP() AS TIMESTAMP_NTZ) AS process_date
    FROM retail.customers
    WHERE year = '{partition_date:%Y}'
        AND month = '{partition_date:%m}'
        AND day = '{partition_date:%d}'
```

## 4.4. `write_file(stage, schema_name, table_name, process_date, object_name, format, is_valid=True) -> str`
- Generates a `COPY INTO` statement to export data from Snowflake back to S3.
- Supports writing both valid and invalid records through the `is_valid=True/False` parameter.

---

# 5. Orchestration by Processing Date — `snowflake_process_stages.py`
## 5.1. `load_snowflake(schema, table, process_date, run_id)`
### Description
- Loads data from the L0 External Table into a date-partition snapshot object.

### Workflow

1. Open Snowflake connection.
2. Generate:

```python
table_process_scope = f"{table}_{run_id}"
```

3. Refresh external table.
4. Create processing scope table.
5. Close connection in `finally`.

---

## 5.2. `process_l0_to_l1(bucket, schema, table, process_date, run_id)`

### Description
- Performs validation and transformation from L0 to L1 while separating invalid records into Audit.

### Workflow
1. Load:
   - L0 configuration (`config`)
   - L1 configuration (`config_target`)
2. Retrieve:
   - `stage_l1`
   - `stage_audit`
3. Create object names:

```python
table_process_scope = f"{table}_{run_id}"
validation = f"validation_{table}"
transformation = f"transformation_{table}"
```

4. Validate:

```python
validate_l0_to_l1(...)
```

Creates:

```sql
TEMP TABLE validation_{table}
```

5. Transform:

```python
transform_l0_to_l1(...)
```

Creates:

```sql
TEMP TABLE transformation_{table}
```

6. Write L1 output
7. Write Audit output
8. Close connection.


# 6. DAG Triggered by Airflow - `pipeline_snowflake_stages.py`
- Initializes the pipeline using PythonOperators to generate SQL and execute Snowflake operations.
