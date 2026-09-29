import argparse
from scripts.commons import sf_helper
from scripts.utils import logger
from scripts.utils.constants import AWSConfigs, DataPipeline, SnowflakeConfig
from scripts.utils.configs import (
    sf_user,
    sf_password,
    sf_account,
    sf_warehouse,
    sf_database,
    sf_schema,
)
from scripts.utils.table_config_generator import (
    get_all_table_names,
    get_table_config_from_dynamo,
)

logging = logger.get_logger(__name__)


def create_external_table_sql(config: dict, pattern: str, auto_refresh: bool) -> str:
    format_mapping = {
        "csv": SnowflakeConfig.DEFINED_CSV_FORMAT,
        "parquet": SnowflakeConfig.DEFINED_PARQUET_FORMAT,
    }

    fmt = config.get(f"format", "").lower()
    if fmt not in format_mapping:
        raise ValueError(
            f"Unsupported Format '{fmt}'. Only: {list(format_mapping.keys())}"
        )

    file_format = format_mapping[fmt]
    table_name = config.get("table_name")
    schema_name = config.get("schema_name")
    config_layer = config.get("config_layer")
    stage_name = f"stage_{config_layer}"
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


def _execute_external_table(
    sf_conn, table_name: str, config: dict, pattern: str, auto_refresh: bool
):
    logging.info(f"Creating external table for {table_name}")
    ddl = create_external_table_sql(
        config=config, pattern=pattern, auto_refresh=auto_refresh
    )
    logging.info(ddl)
    sf_conn.cursor().execute(ddl)


def _get_sf_connection():
    return sf_helper.get_conn(
        user=sf_user,
        password=sf_password,
        account=sf_account,
        warehouse=sf_warehouse,
        database=sf_database,
        schema=sf_schema,
    )


def create_external_table(
    table_name: str,
    dynamo_table_config: str = AWSConfigs.DYNAMO_TABLE_CONFIG,
    pattern: str = SnowflakeConfig.PATTERN_FILE_CSV,
    auto_refresh: bool = SnowflakeConfig.EXTERNAL_TABLE_AUTO_REFRESH,
):
    sf_conn = None
    try:
        config = get_table_config_from_dynamo(
            table_name=table_name,
            config_layer=DataPipeline.LAYER_L0,
            dynamo_table_name=dynamo_table_config,
        )
        if not config:
            raise ValueError(
                f"No configuration found for {table_name} "
                f"(Layer: {DataPipeline.LAYER_L0})"
            )

        sf_conn = _get_sf_connection()
        _execute_external_table(sf_conn, table_name, config, pattern, auto_refresh)
    except Exception as e:
        logging.error(str(e))
        raise
    finally:
        if sf_conn:
            sf_conn.close()
            logging.info("Snowflake connection closed.")


def create_all_external_table(
    excel_path: str = DataPipeline.TEMP_EXCEL_PATH,
    dynamo_table_config: str = AWSConfigs.DYNAMO_TABLE_CONFIG,
    pattern: str = SnowflakeConfig.PATTERN_FILE_CSV,
    auto_refresh: bool = SnowflakeConfig.EXTERNAL_TABLE_AUTO_REFRESH,
):
    table_names = get_all_table_names(excel_path)
    try:
        sf_conn = _get_sf_connection()
        for table_name in table_names:
            config = get_table_config_from_dynamo(
                table_name=table_name,
                config_layer=DataPipeline.LAYER_L0,
                dynamo_table_name=dynamo_table_config,
            )
            if not config:
                raise ValueError(
                    f"No configuration found for {table_name} "
                    f"(Layer: {DataPipeline.LAYER_L0})"
                )

            _execute_external_table(
                sf_conn=sf_conn,
                table_name=table_name,
                config=config,
                pattern=pattern,
                auto_refresh=auto_refresh,
            )
    except Exception as e:
        logging.error(str(e))
        raise
    finally:
        if sf_conn:
            sf_conn.close()
            logging.info("Snowflake connection closed.")

    logging.info("All external tables created successfully.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Create Snowflake external tables from DynamoDB configurations"
    )
    parser.add_argument(
        "--excel-path",
        default=DataPipeline.TEMP_EXCEL_PATH,
        help="Path to the Excel file containing the table names",
    )
    parser.add_argument(
        "--dynamo-table-config",
        default=AWSConfigs.DYNAMO_TABLE_CONFIG,
        help="DynamoDB table name for table configurations",
    )
    parser.add_argument(
        "--pattern",
        default=SnowflakeConfig.PATTERN_FILE_CSV,
        help="Regex pattern for files loaded by the external tables",
    )
    parser.add_argument(
        "--auto-refresh",
        action="store_true",
        help="Enable automatic refresh for the external tables",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Create all external tables")
    group.add_argument("--table-name", help="Create an external table for one table")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.all:
        create_all_external_table(
            excel_path=args.excel_path,
            dynamo_table_config=args.dynamo_table_config,
            pattern=args.pattern,
            auto_refresh=args.auto_refresh,
        )
    else:
        create_external_table(
            table_name=args.table_name,
            dynamo_table_config=args.dynamo_table_config,
            pattern=args.pattern,
            auto_refresh=args.auto_refresh,
        )
