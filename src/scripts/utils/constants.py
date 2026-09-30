from datetime import datetime


class ExcelColumns:
    TABLE_NAME = "Table Name"
    LAYER = "Layer"
    COLUMN_NAME = "Column Name"
    TYPE = "Type"
    MAX_LENGTH = "Max Length"
    FORMAT = "Format"
    RANGE = "Range"
    PRECISION = "Precision"
    SCALE = "Scale"
    NOT_NULL = "Not Null"
    PRIMARY_KEY = "Primary Key"
    UNIQUE = "Unique"
    TRANSFORM_FUNCTION = "Transform Function"


class AWSConfigs:
    DEFAULT_BUCKET = "huynm43-mock-project-s3-414061810527-us-east-1-an"
    DYNAMO_TABLE_CONFIG = "huynm43-mp-table-config"
    DYNAMO_TABLE_TRACKING = "huynm43-mp-dynamo"
    DEFAULT_REGION = "us-east-1"
    DEFAULT_TABLE = "customers"
    SUPPORTED_TABLES = ["customers", "products", "orders", "province"]
    DEFAULT_SCHEMA = "retail"
    DEFAULT_PROCESS_DATE = datetime.now().strftime("%Y/%m/%d")
    DEFAULT_RUN_ID = "run_001"
    SNS_TOPIC_ARN = "arn:aws:sns:us-east-1:414061810527:huynm43-mp-sns"
    GLUE_LOAD_DB_JOB = "huynm43-mp-glue-load-db"


class DataPipeline:
    SYSTEM_COLUMNS = ["process_date", "source_file"]
    DATE_FORMAT = "%Y/%m/%d"

    LAYER_RCV = "rcv"
    LAYER_L0 = "l0"
    LAYER_L1 = "l1"
    LAYER_QUARANTINE = "quarantine"
    LAYER_AUDIT = "audit"

    PROCESS_RCV_TO_L0 = "rcv_to_l0"
    PROCESS_L0_TO_L1 = "l0_to_l1"
    PROCESS_L1_TO_DB = "l1_to_db"

    TEMP_EXCEL_PATH = "../excel/RCV_L0_Tables_Definitions.xlsx"
    ERROR_CODE = ["404", "403"]

    ENCODING = "utf-8"


class TrackJob:
    STATUS_SUCCESS = "SUCCESS"
    STATUS_FAILED = "FAILED"
    STATUS_RUNNING = "RUNNING"
    INIT_STAGE = "INIT"
    REGEX_PATTERN = r"FAILED_AT_\[(.*?)\]"
    GLUE_ID_REGEX_PATERN = r"Job (jr_[a-zA-Z0-9]+)"


class SnowflakeConfig:
    DEFINED_CSV_FORMAT = "csv_ff"
    DEFINED_TSV_FORMAT = "tsv_ff"
    DEFINED_PSV_FORMAT = "psv_ff"
    DEFINED_SCSV_FORMAT = "scsv_ff"
    DEFINED_PARQUET_FORMAT = "parquet_ff"
    DEFINED_JSON_FORMAT = "json_ff"

    PATTERN_FILE = None
    EXTERNAL_TABLE_AUTO_REFRESH = False


class TransformFunction:
    OUTPUT_SPLIT_CUSTOMERS_NAME = ["first_name", "last_name"]
    OUTPUT_SPLIT_CUSTOMERS_ADDRESS = ["address", "address_province"]


class ErrorMessages:
    FILE_NOT_FOUND = "File not found"
    FILE_EMPTY = "File empty"
    FILE_CONTAINS_ONLY_HEADER = "File contains only header without data"
    FILE_NOT_READABLE = "File is not readable"
    SCHEMA_MISMATCH = "Schema mismatch"
    EXCEPTION_MESSAGE_FOR_REGEX = "FAILED_AT"


COMPRESSION_EXTENSIONS = {
    "gzip": "gz",
    "bzip2": "bz2",
    "xz": "xz",
    "lzma": "lzma",
}
