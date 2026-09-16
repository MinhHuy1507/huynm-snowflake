from scripts.utils import logger, s3_helper
from itertools import islice

logging = logger.get_logger(__name__)


class ValidationError(Exception):
    pass


# RCV to L0
# Validate file exists, file format, file readable, file not empty
def validate_file(context):
    bucket = context["bucket"]
    key_source = context["key_source"]
    key_quarantine = context["key_quarantine"]
    file_path = f"s3://{bucket}/{key_source}"
    logging.info(f"Validating file: {file_path}")

    # File exists
    if not s3_helper.check_file_exists(bucket, key_source):
        msg = f"File not found - {file_path}"
        logging.error(msg)
        raise ValidationError(msg)

    # File readable, file not empty
    try:
        response = s3_helper.get_object(bucket, key_source)
        iterator = response["Body"].iter_lines()

        first_line = next(iterator, None)
        if not first_line:
            raise ValidationError(f"File empty - {file_path}")

        header_line = first_line.decode("utf-8").strip()
        if not header_line:
            raise ValidationError(f"File empty - {file_path}")

        first_data_line = next(
            (l.decode("utf-8").strip() for l in islice(iterator, 10) if l.strip()), None
        )
        if not first_data_line:
            raise ValidationError(
                f"File contains only header without data - {file_path}"
            )
        context["header_line"] = header_line

    except ValidationError as ve:
        s3_helper.copy_file(bucket, key_source, bucket, key_quarantine)
        logging.error(str(ve))
        raise ve

    except Exception as e:
        s3_helper.copy_file(bucket, key_source, bucket, key_quarantine)
        error_msg = f"File is not readable - {file_path}"
        logging.error(f"{error_msg} | Internal Error: {str(e)}")
        raise ValidationError(error_msg)


def validate_schema(context):
    config = context["config"]
    actual = context["header_line"].split(",")
    expected = [column["name"] for column in config["columns"]]

    if actual != expected:
        s3_helper.copy_file(
            context["bucket"],
            context["key_source"],
            context["bucket"],
            context["key_quarantine"],
        )
        raise ValidationError(f"Schema mismatch. Expected {expected}, got {actual}")


def validate_rcv_to_l0(context):
    config = context["config"]
    for function, required in config["validation"].items():
        if required:
            function_map = VALIDATE_FUNCTIONS[function]
            function_map(context)


# L0 to L1
def validate_not_null(column):
    if isinstance(column, str):
        column = [column]

    expr = []
    for col in column:
        expr_col = (
            f"CASE WHEN NULLIF(TRIM({col}::STRING), '') IS NULL "
            f"THEN 'not_null({col})' END"
        )
        expr.append(expr_col)
    return expr


def validate_unique(column):
    if isinstance(column, str):
        column = [column]

    partition_expr = ", ".join(f"NULLIF(TRIM({col}::STRING), '')" for col in column)
    all_columns_present = " AND ".join(
        f"NULLIF(TRIM({col}::STRING), '') IS NOT NULL" for col in column
    )
    expr = [f"""CASE WHEN {all_columns_present}
        AND COUNT(*) OVER(PARTITION BY {partition_expr}) > 1
        THEN 'unique({','.join(column)})' END"""]
    return expr


def validate_range(column, min, max):
    if isinstance(column, str):
        column = [column]

    expr = []
    for col in column:
        expr_col = (
            f"CASE WHEN NULLIF(TRIM({col}::STRING), '') IS NOT NULL "
            f"AND TRY_TO_DOUBLE({col}) NOT BETWEEN {min} AND {max} "
            f"THEN 'range({col})' END"
        )
        expr.append(expr_col)
    return expr


def validate_duplicate(column=None, primary_key=None, all_columns=None):
    subset = primary_key if primary_key is not None else column
    if subset is None or subset == []:
        subset = all_columns
    if isinstance(subset, str):
        subset = [subset]
    if not subset:
        raise ValueError("validate_duplicate requires at least one column")

    partition_expr = ", ".join(subset)
    expr = (
        f"CASE WHEN ROW_NUMBER() OVER (PARTITION BY {partition_expr} "
        f"ORDER BY NULL) > 1 "
        f"THEN 'duplicate({','.join(subset)})' END"
    )
    return [expr]


def validate_datatype(config):
    expr = []
    TYPE_MAPPING = {
        "integer": "TRY_TO_NUMBER({column})",
        "decimal": "TRY_TO_DECIMAL({column})",
        "date": "TRY_TO_DATE({column}{format})",
        "timestamp": "TRY_TO_TIMESTAMP({column})",
        "boolean": "TRY_TO_BOOLEAN({column})",
    }
    for column in config["columns"]:
        col_name = column["name"]
        col_type = column["type"]

        sql_template = TYPE_MAPPING.get(col_type)
        if not sql_template:
            continue

        fmt = ""
        if "format" in column:
            fmt = f", '{column['format']}'"

        cast_expr = sql_template.format(column=col_name, format=fmt)
        expr_col = (
            f"CASE WHEN NULLIF(TRIM({col_name}::STRING), '') IS NOT NULL "
            f"AND {cast_expr} IS NULL THEN 'datatype({col_name})' END"
        )
        expr.append(expr_col)

    return expr


VALIDATE_FUNCTIONS = {
    "validate_file": validate_file,
    "validate_schema": validate_schema,
    "not_null": validate_not_null,
    "unique": validate_unique,
    "range": validate_range,
    "duplicate": validate_duplicate,
}


def validate_l0_to_l1(config, schema, view_input, view_output):
    all_columns = [column["name"] for column in config["columns"]]
    exprs = validate_duplicate(all_columns=all_columns)
    exprs.extend(validate_datatype(config))

    for validation in config["validation"]:
        rule = validation["rule"]
        params = {k: v for k, v in validation.items() if k != "rule"}
        function_map = VALIDATE_FUNCTIONS[rule]

        if rule == "duplicate":
            if params.get("primary_key") is None:
                continue
            params["all_columns"] = all_columns

        expr_return = function_map(**params)
        exprs.extend(expr_return)

    exprs_str = ",\n".join(exprs)

    validate_sql = f"""
        CREATE OR REPLACE TEMP TABLE {schema}.{view_output} AS
        SELECT
            *,
            ARRAY_CONSTRUCT_COMPACT({exprs_str}) AS validation_errors
        FROM {schema}.{view_input}
    """

    return validate_sql


def get_result_validation(schema, view_input, view_output, isvalid):
    filter_sql = f"""
        CREATE OR REPLACE TEMP TABLE {schema}.{view_output} AS
        SELECT * FROM {schema}.{view_input}
        WHERE ARRAY_SIZE(validation_errors) {'= 0' if isvalid else '> 0'}
    """
    return filter_sql
