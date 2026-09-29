def split_customers_name(transform_rules, column_expr):
    for rule in transform_rules:
        source_col = rule["from"]
        first_col, second_col = rule["to"]

        cleaned = f"REGEXP_REPLACE(TRIM({source_col}), '[[:space:]]+', ' ')"

        column_expr[first_col] = (
            f"NULLIF(REGEXP_SUBSTR({cleaned}, '[^[:space:]]+$'), '')"
        )

        column_expr[second_col] = (
            f"NULLIF(TRIM(REGEXP_REPLACE({cleaned}, '[^[:space:]]+$', '')), '')"
        )
    return column_expr


def split_customers_address(transform_rules, column_expr):
    for rule in transform_rules:
        source_col = rule["from"]
        first_col, second_col = rule["to"]

        norm_spaces = f"REGEXP_REPLACE(TRIM({source_col}), '[[:space:]]+', ' ')"
        norm_commas = f"REGEXP_REPLACE({norm_spaces}, '(,[[:space:]]*)+', ', ')"
        cleaned = f"TRIM(REGEXP_REPLACE({norm_commas}, '(^,[[:space:]]*)|([[:space:]]*,[[:space:]]*$)', ''))"

        column_expr[first_col] = f"NULLIF({cleaned}, '')"
        column_expr[second_col] = (
            f"IFF(CONTAINS({cleaned}, ','), NULLIF(TRIM(SPLIT_PART({cleaned}, ',', -1)), ''), NULL)"
        )

    return column_expr


def rename_columns(transform_rules, column_expr):
    for rule in transform_rules:
        source_col = rule["from"]
        target_col = rule["to"]
        column_expr[target_col] = source_col
    return column_expr


def filter_columns(transform_rules, column_expr):
    for rule in transform_rules:
        output_columns = rule["output"]
    filtered_expr = {}
    for col in output_columns:
        if col in column_expr:
            filtered_expr[col] = column_expr[col]

    return filtered_expr


def transform_l0_to_l1(config, schema, obj_input, obj_output, target_config):
    CAST_MAPPING = {
        "string": "{column}",
        "integer": "TRY_CAST({column} AS INT)",
        "decimal": "TRY_CAST({column} AS {db_type})",
        "double": "TRY_TO_DOUBLE({column})",
        "date": "TRY_TO_DATE({column}{format})",
        "datetime": "TRY_TO_TIMESTAMP({column})",
        "timestamp": "TRY_TO_TIMESTAMP({column})",
        "boolean": "TRY_TO_BOOLEAN({column})",
    }

    column_expr = {}
    target_columns = target_config.get("columns", [])
    SYSTEM_COLUMNS = ["process_date", "source_file"]

    for col_meta in target_columns:
        col_name = col_meta["name"]

        if col_name in SYSTEM_COLUMNS:
            column_expr[col_name] = col_name
            continue

        col_type = col_meta.get("type", "string").lower()

        db_type_str = ""
        if col_type == "decimal":
            base_type = col_meta.get("db_type", "DECIMAL")
            precision = col_meta.get("precision", 38)
            scale = col_meta.get("scale", 4)
            db_type_str = f"{base_type}({precision}, {scale})"

        sql_template = CAST_MAPPING.get(col_type, "{column}")
        fmt = f", '{col_meta['format']}'" if "format" in col_meta else ""

        column_expr[col_name] = sql_template.format(
            column=col_name, format=fmt, db_type=db_type_str
        )

    transformations = config.get("transformation", {})
    for transform_name, transform_rules in transformations.items():
        function = TRANSFORM_FUNCTIONS.get(transform_name)
        if function:
            column_expr = function(transform_rules, column_expr)

    column_expr_list = [f"{expr} AS {col}" for col, expr in column_expr.items()]
    column_expr_str = ",\n            ".join(column_expr_list)

    transform_sql = f"""
        CREATE OR REPLACE TEMP TABLE {schema}.{obj_output} AS
        SELECT
            {column_expr_str}
        FROM {schema}.{obj_input}
        WHERE ARRAY_SIZE(validation_errors) = 0
    """

    return transform_sql


TRANSFORM_FUNCTIONS = {
    "split_name": split_customers_name,
    "split_address": split_customers_address,
    "rename": rename_columns,
    "filter_columns": filter_columns,
}
