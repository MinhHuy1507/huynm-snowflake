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
        table_process_scope = f"{table}_{run_id}"

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
        logging.error(str(e))
        raise e
    finally:
        if sf_conn:
            sf_conn.close()
            logging.info("Snowflake connection closed.")


def process_l0_to_l1(bucket, schema, table, process_date, run_id):
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
        config = s3_helper.load_config(bucket=bucket, layer="l0", table=table)
        config_target = s3_helper.load_config(bucket=bucket, layer="l1", table=table)

        stage_l1 = config["l1_stage"]
        stage_audit = config["audit_stage"]

        table_process_scope = f"{table}_{run_id}"
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
            config["l1_format"],
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
            config["audit_format"],
            is_valid=False,
        )
        logging.info(write_audit_sql)
        sf_conn.cursor().execute(write_audit_sql)

        logging.info(f"\nCompleted process from l0 to l1, table {table}")

    except Exception as e:
        logging.error(str(e))
        raise e
    finally:
        if sf_conn:
            sf_conn.close()
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
    parser.add_argument(
        "--run-id",
        default="run_001",
        help="Run ID",
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
        bucket=args.bucket,
        schema=args.schema,
        table=args.table,
        process_date=args.process_date,
        run_id=args.run_id,
    )
