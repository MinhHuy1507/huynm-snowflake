import argparse
from datetime import datetime
from scripts.commons import validations, transformations
from scripts.utils import logger
from scripts.utils.configs import (
    sf_user,
    sf_password,
    sf_account,
    sf_warehouse,
    sf_database,
    sf_schema,
)
from scripts.commons import sf_helper
from scripts.utils.table_config_generator import get_table_config_from_dynamo
from scripts.utils.constants import AWSConfigs, DataPipeline, ErrorMessages

logging = logger.get_logger(__name__)


def load_snowflake(schema, table, process_date, run_id):
    try:
        logging.info(
            f"Loading table {table} from l0/ to snowflake permanent table {schema}.{table}"
        )
        sf_conn = sf_helper.get_conn(
            user=sf_user,
            password=sf_password,
            account=sf_account,
            warehouse=sf_warehouse,
            database=sf_database,
            schema=sf_schema,
        )
        str_date = str(process_date).replace("/", "_")
        table_process_scope = f"{table}__{str_date}__{run_id}"

        logging.info(f"Refreshing external table for {table}")
        refresh_ext_sql = sf_helper.refresh_external_table(schema, table, process_date)
        logging.info(refresh_ext_sql)
        sf_conn.cursor().execute(refresh_ext_sql)

        logging.info(f"Scoping input temp table to partition {process_date}")
        process_tmp_table_sql = sf_helper.create_process_scope(
            schema, table, process_date, table_process_scope, is_temporary=False
        )
        logging.info(process_tmp_table_sql)
        sf_conn.cursor().execute(process_tmp_table_sql)
    except Exception as e:
        error_message = f"{ErrorMessages.EXCEPTION_MESSAGE_FOR_REGEX}_[{DataPipeline.PROCESS_L0_TO_L1}]: {str(e)}"
        logging.error(error_message)
        raise Exception(error_message)
    finally:
        if sf_conn:
            sf_conn.close()
            logging.info("Snowflake connection closed.")


def process_l0_to_l1(schema, table, process_date, run_id, dynamo_table_config):
    try:
        logging.info(
            f"Start processing (validate and transform) table {table} from l0/ to l1/"
        )
        sf_conn = sf_helper.get_conn(
            user=sf_user,
            password=sf_password,
            account=sf_account,
            warehouse=sf_warehouse,
            database=sf_database,
            schema=sf_schema,
        )

        # Get table configurations from DynamoDB
        config = get_table_config_from_dynamo(
            table_name=table,
            config_layer=DataPipeline.LAYER_L0,
            dynamo_table_name=dynamo_table_config,
        )

        config_target = get_table_config_from_dynamo(
            table_name=table,
            config_layer=DataPipeline.LAYER_L1,
            dynamo_table_name=dynamo_table_config,
        )

        stage_l1 = f"stage_{config_target['l1_layer']}"
        stage_audit = f"stage_{config_target['audit_layer']}"

        str_date = str(process_date).replace("/", "_")
        table_process_scope = f"{table}__{str_date}__{run_id}"
        validation = f"validation_{table}"
        transformation = f"transformation_{table}"

        logging.info(f"Validating table {table}")
        sql_validate = validations.validate_l0_to_l1(
            config, schema, table_process_scope, validation
        )
        logging.info(sql_validate)
        sf_conn.cursor().execute(sql_validate)

        logging.info(f"Transforming table {table}")
        sql_transform = transformations.transform_l0_to_l1(
            config, schema, validation, transformation, config_target
        )
        logging.info(sql_transform)
        sf_conn.cursor().execute(sql_transform)

        logging.info(f"Writing valid records to l1/{schema}/{table}/{process_date}/")
        write_l1_sql = sf_helper.write_file(
            stage_l1,
            schema,
            table,
            process_date,
            transformation,
            config_target["format"],
        )
        logging.info(write_l1_sql)
        sf_conn.cursor().execute(write_l1_sql)

        logging.info(
            f"Writing invalid records to audit/{schema}/{table}/{process_date}/"
        )
        write_audit_sql = sf_helper.write_file(
            stage_audit,
            schema,
            table,
            process_date,
            validation,
            config_target["format"],
            is_valid=False,
        )
        logging.info(write_audit_sql)
        sf_conn.cursor().execute(write_audit_sql)

        logging.info(f"\nCompleted process from l0 to l1, table {table}")

    except Exception as e:
        error_message = f"{ErrorMessages.EXCEPTION_MESSAGE_FOR_REGEX}_[{DataPipeline.PROCESS_L0_TO_L1}]: {str(e)}"
        logging.error(error_message)
        raise Exception(error_message)
    finally:
        if sf_conn:
            sf_conn.close()
            logging.info("Snowflake connection closed.")


# Test
def parse_args():
    parser = argparse.ArgumentParser(description="Run Snowflake l0 to l1 processing")
    parser.add_argument(
        "--bucket",
        default=AWSConfigs.DEFAULT_BUCKET,
        help="S3 bucket name",
    )
    parser.add_argument(
        "--schema",
        default=AWSConfigs.DEFAULT_SCHEMA,
        help="Snowflake schema name",
    )
    parser.add_argument(
        "--table",
        default=AWSConfigs.DEFAULT_TABLE,
        help="Table name",
    )
    parser.add_argument(
        "--process-date",
        default=AWSConfigs.DEFAULT_PROCESS_DATE,
        help="Processing partition date in YYYY/MM/DD format",
    )
    parser.add_argument(
        "--run-id",
        default=AWSConfigs.DEFAULT_RUN_ID,
        help="Run ID",
    )
    parser.add_argument(
        "--dynamo-table-config",
        default=AWSConfigs.DYNAMO_TABLE_CONFIG,
        help="DynamoDB table name for table configurations",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    load_snowflake(
        schema=args.schema,
        table=args.table,
        process_date=args.process_date,
        run_id=args.run_id,
    )
    process_l0_to_l1(
        schema=args.schema,
        table=args.table,
        process_date=args.process_date,
        run_id=args.run_id,
        dynamo_table_config=args.dynamo_table_config,
    )
