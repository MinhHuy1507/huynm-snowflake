import os
from pathlib import Path
import boto3

current = Path(__file__).resolve().parent
env_file = None

while current != current.parent:
    potential_path = current / ".env"
    if potential_path.is_file():
        env_file = potential_path
        break
    current = current.parent

if env_file:
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip("'\"")

sf_user = os.getenv("SF_USER")
sf_password = os.getenv("SF_PASSWORD")
sf_account = os.getenv("SF_ACCOUNT")
sf_warehouse = os.getenv("SF_WAREHOUSE")
sf_database = os.getenv("SF_DATABASE")
sf_schema = os.getenv("SF_SCHEMA")

print(f"SF_USER: {sf_user}")


pg_host = os.environ.get("POSTGRES_HOST")
pg_port = os.environ.get("POSTGRES_PORT")
pg_user = os.environ.get("POSTGRES_USER")
pg_database = os.environ.get("POSTGRES_DB")
pg_password = os.environ.get("POSTGRES_PASSWORD")
pg_conn = (
    f"postgresql+psycopg2://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"
)


def upload_secret_to_s3(bucket_name, s3_key, secret_value):
    s3 = boto3.client("s3")
    s3.put_object(Bucket=bucket_name, Key=s3_key, Body=secret_value)
    logging.info(f"Uploaded secret to s3://{bucket_name}/{s3_key}")


def delete_secret_from_s3(bucket_name, s3_key):
    s3 = boto3.client("s3")
    s3.delete_object(Bucket=bucket_name, Key=s3_key)
    logging.info(f"Deleted secret from s3://{bucket_name}/{s3_key}")
