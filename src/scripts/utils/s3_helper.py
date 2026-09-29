import boto3
import yaml
from botocore.exceptions import ClientError
from scripts.utils import logger

logging = logger.get_logger(__name__)
s3 = boto3.client("s3")


def check_file_exists(bucket, key):
    s3_client = boto3.client("s3")
    try:
        s3_client.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        if error_code in ["404", "403"]:
            return False
        raise e


def get_object(bucket: str, key: str):
    return s3.get_object(Bucket=bucket, Key=key)


def load_config(bucket: str, layer: str, table: str):
    key = f"config/{layer}/{table}.yaml"
    obj = get_object(bucket, key)
    return yaml.safe_load(obj["Body"].read())


def copy_file(bucket_source, key_source, bucket_target, key_target):
    copy_source = {"Bucket": bucket_source, "Key": key_source}
    s3.copy(copy_source, bucket_target, key_target)


def get_header(bucket: str, key: str):
    response = s3.list_objects_v2(Bucket=bucket, Prefix=key)
    target_key = None

    if "Contents" in response:
        for obj in response["Contents"]:
            obj_key = obj["Key"]
            if obj_key.endswith(".csv") and not obj_key.endswith(".crc"):
                target_key = obj_key
                break

    if not target_key:
        raise FileNotFoundError(f"File not found in s3://{bucket}/{key}")

    obj = get_object(bucket, target_key)
    header_line = next(obj["Body"].iter_lines()).decode("utf-8")
    obj["Body"].close()

    return header_line.split(",")
