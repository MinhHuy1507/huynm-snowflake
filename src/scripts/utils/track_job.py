import boto3
import re
from datetime import datetime
from utils.logger import get_logger
import json

logging = get_logger(__name__)


# Dump Function PutItem to Dynamo when DAG starts
def init_tracking_record(**kwargs):
    params = kwargs.get("params", {})
    dag_id = params.get("dag_id")
    run_id = params.get("run_id")
    task_id = params.get("task_id")
    schema_name = params.get("schema_name")
    table_name = params.get("table_name")
    process_date = params.get("process_date")
    bucket_name = params.get("bucket_name")
    region_name = params.get("region_name")
    dynamo_table_name = params.get("dynamo_table_name")
    source_file = (
        f"s3://{bucket_name}/rcv/{schema_name}/{table_name}/{process_date}/{table_name}"
    )
    start_time = datetime.now().isoformat()

    dynamodb = boto3.resource("dynamodb", region_name=region_name)
    table = dynamodb.Table(dynamo_table_name)

    table.put_item(
        Item={
            "dag_id": dag_id,
            "run_id": run_id,
            "task_id": task_id,
            "schema_name": schema_name,
            "table_name": table_name,
            "process_date": process_date,
            "source_file": source_file,
            "status": "RUNNING",
            "stage_name": "INIT",
            "start_time": start_time,
            "end_time": None,
            "error_message": None,
        }
    )
    logging.info(f"Initialized tracking for {table_name} at {run_id}")


# Attribute need updating: task_id, status, stage_name, end_time, error_message
# Publish error message to SNS topic
def sns_publish(
    sns_topic_arn,
    run_id,
    task_id,
    bucket_name,
    schema_name,
    table_name,
    process_date,
    stage_name,
    error_message,
    end_time,
    region_name,
):
    try:
        sns_client = boto3.client("sns", region_name=region_name)
        source_file = f"s3://{bucket_name}/rcv/{schema_name}/{table_name}/{process_date}/{table_name}"

        sns_message = {
            "run_id": run_id,
            "task_id": task_id,
            "schema_name": schema_name,
            "table_name": table_name,
            "process_date": process_date,
            "source_file": source_file,
            "status": "FAILED",
            "stage_name": stage_name,
            "error_message": error_message,
            "end_time": end_time,
        }

        response = sns_client.publish(
            TopicArn=sns_topic_arn,
            Subject=f"Airflow Task FAILED: {run_id} - {task_id} - {table_name}",
            Message=json.dumps(sns_message, indent=2, ensure_ascii=False),
        )
        logging.info(
            f"Successfully sent SNS message. MessageId: {response.get('MessageId')}"
        )

    except Exception as e:
        logging.error(f"Failed to send SNS message: {e}", exc_info=True)


# Callback funtion for Glue job
# Callback function to update DynamoDB when the task fails
def glue_job_failure_callback(context):
    ti = context.get("task_instance")
    run_id = context.get("run_id")
    task_id = ti.task_id

    # param injected from task
    params = context.get("params", {})
    bucket_name = params.get("bucket_name")
    schema_name = params.get("schema_name")
    table_name = params.get("table_name")
    process_date = params.get("process_date")
    region_name = params.get("region_name", "us-east-1")
    dynamo_table_name = params.get("dynamo_table_name")
    sns_topic_arn = params.get("sns_topic_arn")

    end_time = datetime.now().isoformat()

    error_obj = context.get("exception")
    airflow_error_str = str(error_obj) if error_obj else "Unknown Error"
    stage_name = "UNKNOWN_STAGE"
    final_error_message = airflow_error_str

    # Get Glue RunId from Airflow error message using regex
    run_id_match = re.search(r"Job (jr_[a-zA-Z0-9]+)", airflow_error_str)

    if run_id_match:
        glue_run_id = run_id_match.group(1)
        glue_job_name = getattr(ti.task, "job_name", "UNKNOWN_JOB")
        try:
            glue_client = boto3.client("glue", region_name=region_name)
            response = glue_client.get_job_run(JobName=glue_job_name, RunId=glue_run_id)

            glue_internal_error = response["JobRun"].get("ErrorMessage", "")

            if glue_internal_error:
                final_error_message = glue_internal_error

                stage_match = re.search(r"FAILED_AT_\[(.*?)\]", glue_internal_error)
                if stage_match:
                    stage_name = stage_match.group(1)

        except Exception as e:
            logging.error(f"Cannot fetch Glue job run details: {e}")

    try:
        dynamodb = boto3.resource("dynamodb", region_name=region_name)
        table = dynamodb.Table(dynamo_table_name)

        table.update_item(
            Key={"table_name": table_name, "run_id": run_id},
            UpdateExpression="SET #st = :status, task_id = :task, stage_name = :stage, error_message = :err, end_time = :end",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":status": "FAILED",
                ":task": task_id,
                ":stage": stage_name,
                ":err": final_error_message,
                ":end": end_time,
            },
        )
        logging.info(f"Updated DynamoDB for table {table_name}, stage: {stage_name}")

    except Exception as e:
        logging.error(f"Failed to update DynamoDB: {e}", exc_info=True)

    sns_publish(
        sns_topic_arn=sns_topic_arn,
        run_id=run_id,
        task_id=task_id,
        bucket_name=bucket_name,
        schema_name=schema_name,
        table_name=table_name,
        process_date=process_date,
        stage_name=stage_name,
        error_message=final_error_message,
        end_time=end_time,
        region_name=region_name,
    )


# Callback function to update DynamoDB when the task succeeds
def glue_job_success_callback(context):
    ti = context["task_instance"]
    task_id = ti.task_id
    run_id = context.get("run_id")

    # param injected from task
    params = context.get("params")
    table_name = params.get("table_name")
    region_name = params.get("region_name", "us-east-1")
    dynamo_table_name = params.get("dynamo_table_name")

    end_time = datetime.now().isoformat()

    try:
        dynamodb = boto3.resource("dynamodb", region_name=region_name)
        table = dynamodb.Table(dynamo_table_name)

        table.update_item(
            Key={"table_name": table_name, "run_id": run_id},
            UpdateExpression="SET #st = :status, task_id = :task, stage_name = :stage, end_time = :end",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":status": "SUCCESS",
                ":task": task_id,
                ":stage": f"{task_id}_completed",
                ":end": end_time,
            },
        )
        logging.info(f"Successfully tracked SUCCESS for {table_name}, task {task_id}")
    except Exception as e:
        logging.error(f"Failed to update DynamoDB on success: {e}")


# callback function to update DynamoDB when a PythonOperator task fails
def python_job_failure_callback(context):
    ti = context.get("task_instance")
    run_id = context.get("run_id")
    task_id = ti.task_id

    # param injected from task
    params = context.get("params", {})
    bucket_name = params.get("bucket_name")
    schema_name = params.get("schema_name")
    table_name = params.get("table_name")
    process_date = params.get("process_date")
    region_name = params.get("region_name", "us-east-1")
    dynamo_table_name = params.get("dynamo_table_name")
    sns_topic_arn = params.get("sns_topic_arn")

    end_time = datetime.now().isoformat()

    error_obj = context.get("exception")
    final_error_message = str(error_obj) if error_obj else "Unknown Python Error"

    stage_name = task_id

    try:
        dynamodb = boto3.resource("dynamodb", region_name=region_name)
        table = dynamodb.Table(dynamo_table_name)

        table.update_item(
            Key={"table_name": table_name, "run_id": run_id},
            UpdateExpression="SET #st = :status, task_id = :task, stage_name = :stage, error_message = :err, end_time = :end",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":status": "FAILED",
                ":task": task_id,
                ":stage": stage_name,
                ":err": final_error_message,
                ":end": end_time,
            },
        )
        logging.info(f"Updated DynamoDB for table {table_name}, stage: {stage_name}")

    except Exception as e:
        logging.error(f"Failed to update DynamoDB: {e}", exc_info=True)

    sns_publish(
        sns_topic_arn=sns_topic_arn,
        run_id=run_id,
        task_id=task_id,
        bucket_name=bucket_name,
        schema_name=schema_name,
        table_name=table_name,
        process_date=process_date,
        stage_name=stage_name,
        error_message=final_error_message,
        end_time=end_time,
        region_name=region_name,
    )


def python_job_success_callback(context):
    ti = context.get("task_instance")
    task_id = ti.task_id
    run_id = context.get("run_id")

    params = context.get("params", {})
    table_name = params.get("table_name")
    region_name = params.get("region_name", "us-east-1")
    dynamo_table_name = params.get("dynamo_table_name")

    end_time = datetime.now().isoformat()

    try:
        dynamodb = boto3.resource("dynamodb", region_name=region_name)
        table = dynamodb.Table(dynamo_table_name)

        table.update_item(
            Key={"table_name": table_name, "run_id": run_id},
            UpdateExpression="SET #st = :status, task_id = :task, stage_name = :stage, end_time = :end",
            ExpressionAttributeNames={"#st": "status"},
            ExpressionAttributeValues={
                ":status": "SUCCESS",
                ":task": task_id,
                ":stage": f"{task_id}_completed",
                ":end": end_time,
            },
        )
        logging.info(f"Successfully tracked SUCCESS for {table_name}, task {task_id}")
    except Exception as e:
        logging.error(f"Failed to update DynamoDB on success: {e}")
