import argparse
from datetime import datetime
from scripts.commons import validations, transformations
from scripts.utils import logger, s3_helper
from scripts.utils.configs import (
    sf_user,
    sf_password,
    sf_account,
    sf_warehouse,
    sf_database,
    sf_schema,
)
from scripts.commons import sf_helper

logging = logger.get_logger(__name__)


def l0_to_l1(schema, table, bucket, process_date, sf_conn):
    logging.info(f"Start processing table {table} from l0/ to l1/")
    config = s3_helper.load_config(bucket=bucket, layer="l0", table=table)
    config_target = s3_helper.load_config(bucket=bucket, layer="l1", table=table)

    stage_l1 = config["l1_stage"]
    stage_audit = config["audit_stage"]

    tmp_table_process = f"tmp_{table}"
    validation = f"validation_{table}"
    transformation = f"transformation_{table}"

    logging.info(f"Refreshing external table for {table}")
    refresh_ext_sql = sf_helper.refresh_external_table(schema, table, process_date)
    logging.info(refresh_ext_sql)
    sf_conn.cursor().execute(refresh_ext_sql)

    logging.info(f"Scoping input temp table to partition {process_date}")
    process_tmp_table_sql = sf_helper.create_process_scope(
        schema, table, process_date, tmp_table_process
    )
    logging.info(process_tmp_table_sql)
    sf_conn.cursor().execute(process_tmp_table_sql)

    logging.info(f"Validating table {table}")
    sql_validate = validations.validate_l0_to_l1(
        config, schema, tmp_table_process, validation
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
        config["l1_format"],
    )
    logging.info(write_l1_sql)
    sf_conn.cursor().execute(write_l1_sql)

    logging.info(f"Writing invalid records to audit/{schema}/{table}/{process_date}/")
    write_audit_sql = sf_helper.write_file(
        stage_audit,
        schema,
        table,
        process_date,
        validation,
        config["audit_format"],
        is_valid=False,
    )
    logging.info(write_audit_sql)
    sf_conn.cursor().execute(write_audit_sql)

    logging.info(f"\nCompleted process from l0 to l1, table {table}")


def process_l0_to_l1(bucket, schema, table, process_date):
    try:
        conn = sf_helper.get_conn(
            user=sf_user,
            password=sf_password,
            account=sf_account,
            warehouse=sf_warehouse,
            database=sf_database,
            schema=sf_schema,
        )
        l0_to_l1(schema, table, bucket, process_date, conn)
    except Exception as e:
        error_message = f"FAILED_AT_[l0_to_l1]: {str(e)}"
        logging.error(error_message)
        raise Exception(error_message)
    finally:
        if conn:
            conn.close()
            logging.info("Snowflake connection closed.")


# Test
def parse_args():
    parser = argparse.ArgumentParser(description="Run Snowflake l0 to l1 processing")
    parser.add_argument(
        "--bucket",
        default="huynm43-mock-project-s3-414061810527-us-east-1-an",
        help="S3 bucket name",
    )
    parser.add_argument(
        "--schema",
        default="retail",
        help="Snowflake schema name",
    )
    parser.add_argument(
        "--table",
        default="customers",
        help="Table name",
    )
    parser.add_argument(
        "--process-date",
        default=datetime.now().strftime("%Y/%m/%d"),
        help="Processing partition date in YYYY/MM/DD format",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    process_l0_to_l1(
        bucket=args.bucket,
        schema=args.schema,
        table=args.table,
        process_date=args.process_date,
    )
