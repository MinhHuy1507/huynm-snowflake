import argparse
from datetime import datetime

from scripts.commons import validations
from scripts.utils import logger, s3_helper

logging = logger.get_logger(__name__)


def process_rcv_to_l0(schema, table, bucket, process_date):
    logging.info(f"Start processing table {table} from rcv/ to l0/")
    try:
        config = s3_helper.load_config(bucket=bucket, layer="rcv", table=table)
        key_rcv = f"{config.get('rcv_layer')}/{schema}/{table}/{process_date}/{table}.{config.get('rcv_format')}"
        key_l0 = f"{config.get('l0_layer')}/{schema}/{table}/{process_date}/{table}.{config.get('l0_format')}"
        key_quarantine = f"{config.get('quarantine_layer')}/{schema}/{table}/{process_date}/{table}.{config.get('rcv_format')}"

        context = {
            "bucket": bucket,
            "key_source": key_rcv,
            "key_quarantine": key_quarantine,
            "config": config,
        }

        logging.info(f"Validating table {table} from {context['key_source']}")
        validations.validate_rcv_to_l0(context)

        s3_helper.copy_file(
            bucket_source=bucket,
            key_source=key_rcv,
            bucket_target=bucket,
            key_target=key_l0,
        )
        logging.info(f"\nCompleted process from rcv to l0, table {table}")
    except Exception as e:
        error_message = f"FAILED_AT_[rcv_to_l0]: {str(e)}"
        logging.error(error_message)
        raise Exception(error_message)


# Test
def test(event, context):
    table = event.get("table")
    process_date = event.get("process_date")
    schema = event.get("schema")
    bucket = event.get("bucket")
    process_rcv_to_l0(schema, table, bucket, process_date)


def parse_args():
    parser = argparse.ArgumentParser(description="Run the data transformation pipeline")
    parser.add_argument(
        "--bucket",
        default="huynm43-mock-project-s3-414061810527-us-east-1-an",
        help="S3 bucket name",
    )
    parser.add_argument("--schema", default="retail", help="Schema name")
    parser.add_argument(
        "--table",
        nargs="?",
        default="customers",
        help="Table to transform (customers, products, orders, province)",
    )
    parser.add_argument(
        "--process-date",
        default=datetime.now().strftime("%Y/%m/%d"),
        help="Date partition to process (default: current date)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    mock_event = {
        "bucket": args.bucket,
        "schema": args.schema,
        "table": args.table,
        "process_date": args.process_date,
    }
    mock_context = {}

    test(mock_event, mock_context)
