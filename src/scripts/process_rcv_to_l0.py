import argparse
from scripts.commons import validations
from scripts.utils import logger, s3_helper
from scripts.utils.table_config_generator import get_table_config_from_dynamo
from scripts.utils.constants import AWSConfigs, DataPipeline, ErrorMessages

logging = logger.get_logger(__name__)


def process_rcv_to_l0(schema, table, bucket, process_date, dynamo_table_config):
    logging.info(f"Start processing table {table} from rcv/ to l0/")
    try:
        config = get_table_config_from_dynamo(
            table_name=table,
            config_layer=DataPipeline.LAYER_L0,
            dynamo_table_name=dynamo_table_config,
        )
        logging.info(config)
        key_rcv = f"{config.get('rcv_layer')}/{schema}/{table}/{process_date}/{table}.{config.get('format')}"
        key_l0 = f"{config.get('l0_layer')}/{schema}/{table}/{process_date}/{table}.{config.get('format')}"
        key_quarantine = f"{config.get('quarantine_layer')}/{schema}/{table}/{process_date}/{table}.{config.get('format')}"

        context = {
            "bucket": bucket,
            "key_source": key_rcv,
            "key_quarantine": key_quarantine,
            "config": config,
        }

        logging.info(f"Validating table {table} from {context['key_source']}")

        validations.validate_file(context)
        validations.validate_schema(context)

        s3_helper.copy_file(
            bucket_source=bucket,
            key_source=key_rcv,
            bucket_target=bucket,
            key_target=key_l0,
        )
        logging.info(f"\nCompleted process from rcv to l0, table {table}")
    except Exception as e:
        error_message = f"{ErrorMessages.EXCEPTION_MESSAGE_FOR_REGEX}_[{DataPipeline.PROCESS_RCV_TO_L0}]: {str(e)}"
        logging.error(error_message)
        raise Exception(error_message)


# Test
def test(event, context):
    table = event.get("table")
    process_date = event.get("process_date")
    schema = event.get("schema")
    bucket = event.get("bucket")
    dynamo_table_config = event.get("dynamo_table_config")
    process_rcv_to_l0(schema, table, bucket, process_date, dynamo_table_config)


def parse_args():
    parser = argparse.ArgumentParser(description="Run the data transformation pipeline")
    parser.add_argument(
        "--bucket",
        default=AWSConfigs.DEFAULT_BUCKET,
        help="S3 bucket name",
    )
    parser.add_argument(
        "--schema", default=AWSConfigs.DEFAULT_SCHEMA, help="Schema name"
    )
    parser.add_argument(
        "--table",
        nargs="?",
        default=AWSConfigs.DEFAULT_TABLE,
        help="Table to transform (customers, products, orders, province)",
    )
    parser.add_argument(
        "--process-date",
        default=AWSConfigs.DEFAULT_PROCESS_DATE,
        help="Date partition to process (default: current date)",
    )
    parser.add_argument(
        "--dynamo-table-config",
        default=AWSConfigs.DYNAMO_TABLE_CONFIG,
        help="DynamoDB table name for table configurations",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    mock_event = {
        "bucket": args.bucket,
        "schema": args.schema,
        "table": args.table,
        "process_date": args.process_date,
        "dynamo_table_config": args.dynamo_table_config,
    }
    mock_context = {}

    test(mock_event, mock_context)
