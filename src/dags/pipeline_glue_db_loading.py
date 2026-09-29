from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.amazon.aws.operators.glue import GlueJobOperator
from airflow.models.param import Param
from scripts.utils.configs import (
    upload_secret_to_s3,
    delete_secret_from_s3,
    pg_host,
    pg_port,
    pg_user,
    pg_database,
    pg_password,
)

from scripts.utils.track_job import (
    init_tracking_record,
    glue_job_failure_callback,
    glue_job_success_callback,
)

default_args = {
    "owner": "airflow",
    # "retries": 3,
    # "retry_delay": timedelta(minutes=5),
    "depends_on_past": False,
    "catch_up": False,
}

with DAG(
    dag_id="pipeline_load_database_with_glue",
    default_args=default_args,
    catchup=False,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    params={
        "bucket_name": Param(
            default="huynm43-mock-project-s3-414061810527-us-east-1-an",
            type="string",
            description="S3 bucket name containing the data.",
        ),
        "schema_name": Param(
            default="retail",
            type="string",
            description="Schema name for the tables. Default is 'retail'.",
        ),
        "table_name": Param(
            default="customers",
            type="string",
            enum=["customers", "products", "orders", "province"],
            description="Table name to process. Options: customers, products, orders, province. Default is customers.",
        ),
        "process_date": Param(
            default=datetime.now().strftime("%Y/%m/%d"),
            type="string",
            description="Custom date for processing in format YYYY/MM/DD. Default is today's date.",
        ),
        "region_name": Param(
            default="us-east-1",
            type="string",
            description="AWS region name. Default is us-east-1.",
        ),
        "dynamo_table_name": Param(
            default="huynm43-mp-dynamo",
            type="string",
            description="DynamoDB table name for tracking job status.",
        ),
        "sns_topic_arn": Param(
            default="arn:aws:sns:us-east-1:414061810527:huynm43-mp-sns",
            type="string",
            description="SNS topic ARN for publishing job failure notifications.",
        ),
    },
) as dag:
    bucket_name = "{{ params.bucket_name }}"
    table_name = "{{ params.table_name }}"
    schema_name = "{{ params.schema_name }}"
    process_date = "{{ params.process_date }}"
    dynamo_table_name = "{{ params.dynamo_table_name }}"
    region_name = "{{ params.region_name }}"
    sns_topic_arn = "{{ params.sns_topic_arn }}"

    secret_s3_key = "temp_secrets/pg_pass_{{ run_id }}.txt"
    secret_s3_path = f"s3://{bucket_name}/{secret_s3_key}"

    init_dynamo_tracking = PythonOperator(
        task_id="init_dynamo_tracking",
        python_callable=init_tracking_record,
        op_kwargs={
            "params": {
                "dag_id": dag.dag_id,
                "run_id": "{{ run_id }}",
                "task_id": "init_dynamo_tracking",
                "schema_name": schema_name,
                "table_name": table_name,
                "process_date": process_date,
                "bucket_name": bucket_name,
                "region_name": region_name,
                "dynamo_table_name": dynamo_table_name,
            }
        },
    )

    init_secret_to_s3 = PythonOperator(
        task_id="init_secret_to_s3",
        python_callable=upload_secret_to_s3,
        op_kwargs={
            "bucket_name": bucket_name,
            "s3_key": secret_s3_key,
            "secret_value": pg_password,
        },
    )

    load_database = GlueJobOperator(
        task_id="load_database",
        job_name="huynm43-mp-glue-load-db",
        script_args={
            "--bucket": bucket_name,
            "--schema": schema_name,
            "--table": table_name,
            "--process_date": process_date,
            "--pg_host": pg_host,
            "--pg_port": pg_port,
            "--pg_username": pg_user,
            "--pg_database": pg_database,
            "--pg_password_s3_key": secret_s3_key,
        },
        aws_conn_id="aws_default",
        region_name=region_name,
        wait_for_completion=True,
        on_failure_callback=glue_job_failure_callback,
        on_success_callback=glue_job_success_callback,
    )

    erase_secret_from_s3 = PythonOperator(
        task_id="erase_secret_from_s3",
        python_callable=delete_secret_from_s3,
        op_kwargs={
            "bucket_name": bucket_name,
            "s3_key": secret_s3_key,
        },
    )

    init_dynamo_tracking >> init_secret_to_s3 >> load_database >> erase_secret_from_s3
