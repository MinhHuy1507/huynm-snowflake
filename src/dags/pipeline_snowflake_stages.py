from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.models.param import Param

from scripts.utils.track_job import (
    init_tracking_record,
    python_job_success_callback,
    python_job_failure_callback,
)

from scripts.process_rcv_to_l0 import process_rcv_to_l0
from scripts.snowflake_process_stages import load_snowflake, process_l0_to_l1

default_args = {
    "owner": "airflow",
    # "retries": 3,
    # "retry_delay": timedelta(minutes=5),
    "depends_on_past": False,
    "catch_up": False,
}

with DAG(
    dag_id="pipeline_snowflake_stages",
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
    run_id = "{{ run_id }}"

    init_dynamo_tracking = PythonOperator(
        task_id="init_dynamo_tracking",
        python_callable=init_tracking_record,
        op_kwargs={
            "params": {
                "dag_id": dag.dag_id,
                "run_id": run_id,
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

    processing_rcv_l0_l1 = PythonOperator(
        task_id="processing_rcv_l0_l1",
        python_callable=process_rcv_to_l0,
        op_kwargs={
            "schema": schema_name,
            "table": table_name,
            "bucket": bucket_name,
            "process_date": process_date,
        },
        on_failure_callback=python_job_failure_callback,
        on_success_callback=python_job_success_callback,
    )

    loading_l0_to_snowflake = PythonOperator(
        task_id="loading_l0_to_snowflake",
        python_callable=load_snowflake,
        op_kwargs={
            "schema": schema_name,
            "table": table_name,
            "process_date": process_date,
            "run_id": run_id,
        },
        on_failure_callback=python_job_failure_callback,
        on_success_callback=python_job_success_callback,
    )

    processing_to_l1 = PythonOperator(
        task_id="processing_to_l1",
        python_callable=process_l0_to_l1,
        op_kwargs={
            "schema": schema_name,
            "table": table_name,
            "bucket": bucket_name,
            "process_date": process_date,
            "run_id": run_id,
        },
        on_failure_callback=python_job_failure_callback,
        on_success_callback=python_job_success_callback,
    )

    (
        init_dynamo_tracking
        >> processing_rcv_l0_l1
        >> loading_l0_to_snowflake
        >> processing_to_l1
    )
