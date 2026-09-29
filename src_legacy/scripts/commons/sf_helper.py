from datetime import datetime
import snowflake.connector
from scripts.utils import logger

logging = logger.get_logger(__name__)


def refresh_external_table(schema_name, ext_name, process_date):
    sql_text = (
        f"ALTER EXTERNAL TABLE {schema_name}.{ext_name} REFRESH '{process_date}';"
    )
    return sql_text


def create_process_scope(
    schema_name: str,
    table_name: str,
    process_date: str,
    object_name: str,
    is_temporary: bool = False,
):
    try:
        partition_date = datetime.strptime(process_date, "%Y/%m/%d")
    except ValueError as exc:
        raise ValueError("process_date must use YYYY/MM/DD format") from exc

    table_type = "TEMP TABLE" if is_temporary else "TABLE"

    return f"""
    CREATE OR REPLACE {table_type} {schema_name}.{object_name} AS
    SELECT *,
        CAST(CURRENT_TIMESTAMP() AS TIMESTAMP_NTZ) AS process_date
    FROM {schema_name}.{table_name}
    WHERE year = '{partition_date:%Y}'
        AND month = '{partition_date:%m}'
        AND day = '{partition_date:%d}'
    """.strip()


def write_file(
    stage,
    schema_name,
    table_name,
    process_date,
    object_name,
    format,
    is_valid: bool = True,
):
    format_map = {
        "csv": "csv_ff",
        "parquet": "parquet_ff",
    }
    file_name = f"{table_name}.{format}"
    condition = f"WHERE ARRAY_SIZE(validation_errors) > 0" if not is_valid else ""

    sql = f"""
    COPY INTO @{stage}/{schema_name}/{table_name}/{process_date}/{file_name}
    FROM (
        SELECT * FROM {schema_name}.{object_name}
        {condition}
    )
    FILE_FORMAT = {schema_name}.{format_map.get(format)}
    SINGLE = TRUE
    OVERWRITE = TRUE
    HEADER = TRUE
    """

    return sql


def get_conn(user, password, account, warehouse, database, schema):
    return snowflake.connector.connect(
        user=user,
        password=password,
        account=account,
        warehouse=warehouse,
        database=database,
        schema=schema,
    )
