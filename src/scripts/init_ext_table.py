import argparse
from scripts.utils import logger
from scripts.utils import s3_helper
from scripts.commons import sf_helper
from scripts.utils.configs import (
    sf_user,
    sf_password,
    sf_account,
    sf_warehouse,
    sf_database,
    sf_schema,
)

logging = logger.get_logger(__name__)


def create_external_table_sql(config: dict, pattern: str, auto_refresh: bool) -> str:
    format_mapping = {"csv": "csv_ff", "parquet": "parquet_ff"}

    fmt = config.get("l0_format", "").lower()
    if fmt not in format_mapping:
        raise ValueError(
            f"Unsupported Format '{fmt}'. Only: {list(format_mapping.keys())}"
        )

    file_format = format_mapping[fmt]
    table_name = config.get("table_name")
    schema_name = config.get("schema_name")
    stage_name = config.get("l0_stage")
    columns = config.get("columns", [])
    col_definitions = []

    c_index = 1
    for col in columns:
        col_name = col.get("name")
        if fmt == "csv":
            col_definitions.append(
                f"    {col_name} STRING AS (VALUE:c{c_index}::STRING)"
            )
            c_index += 1
        else:
            col_definitions.append(
                f"    {col_name} STRING AS (VALUE:{col_name}::STRING)"
            )

    col_definitions.extend(
        [
            "    source_file STRING AS (METADATA$FILENAME)",
            "    year STRING AS (SPLIT_PART(METADATA$FILENAME, '/', 4))",
            "    month STRING AS (SPLIT_PART(METADATA$FILENAME, '/', 5))",
            "    day STRING AS (SPLIT_PART(METADATA$FILENAME, '/', 6))",
        ]
    )

    columns_str = ",\n".join(col_definitions)
    auto_refresh_str = "TRUE" if auto_refresh else "FALSE"

    ddl = f"""CREATE OR REPLACE EXTERNAL TABLE {schema_name}.{table_name} (
    {columns_str}
    )
    PARTITION BY (year, month, day)
    LOCATION = @{stage_name}/{schema_name}/{table_name}/
    PATTERN = '{pattern}'
    FILE_FORMAT = {file_format}
    AUTO_REFRESH = {auto_refresh_str};"""

    return ddl


def create_all_external_table(
    bucket: str, pattern: str = r".*/[^._][^/]*\\.csv$", auto_refresh: bool = False
):
    try:
        sf_conn = sf_helper.get_conn(
            user=sf_user,
            password=sf_password,
            account=sf_account,
            warehouse=sf_warehouse,
            database=sf_database,
            schema=sf_schema,
        )

        logging.info("Create external table for customers")
        customers_config = s3_helper.load_config(
            bucket=bucket, layer="l0", table="customers"
        )
        customers_ddl = create_external_table_sql(
            config=customers_config, pattern=pattern, auto_refresh=auto_refresh
        )
        logging.info(customers_ddl)
        sf_conn.cursor().execute(customers_ddl)

        logging.info("Create external table for products")
        products_config = s3_helper.load_config(
            bucket=bucket, layer="l0", table="products"
        )
        products_ddl = create_external_table_sql(
            config=products_config, pattern=pattern, auto_refresh=auto_refresh
        )
        logging.info(products_ddl)
        sf_conn.cursor().execute(products_ddl)

        logging.info("Create external table for orders")
        orders_config = s3_helper.load_config(bucket=bucket, layer="l0", table="orders")
        orders_ddl = create_external_table_sql(
            config=orders_config, pattern=pattern, auto_refresh=auto_refresh
        )
        logging.info(orders_ddl)
        sf_conn.cursor().execute(orders_ddl)

        logging.info("Create external table for province")
        province_config = s3_helper.load_config(
            bucket=bucket, layer="l0", table="province"
        )
        province_ddl = create_external_table_sql(
            config=province_config, pattern=pattern, auto_refresh=auto_refresh
        )
        logging.info(province_ddl)
        sf_conn.cursor().execute(province_ddl)

        logging.info("All external tables created successfully.")

    except Exception as e:
        logging.error(str(e))
        raise e

    finally:
        if sf_conn:
            sf_conn.close()
            logging.info("Snowflake connection closed.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create Snowflake external tables for all configured tables"
    )
    parser.add_argument(
        "--bucket",
        default="huynm43-mock-project-s3-414061810527-us-east-1-an",
        help="S3 bucket name",
    )
    parser.add_argument(
        "--pattern",
        default=r".*/[^._][^/]*\\.csv$",
        help="Regex pattern for files loaded by the external tables",
    )
    parser.add_argument(
        "--auto-refresh",
        action="store_true",
        help="Enable automatic refresh for the external tables",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    create_all_external_table(
        bucket=args.bucket, pattern=args.pattern, auto_refresh=args.auto_refresh
    )
