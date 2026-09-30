import argparse
import boto3
import pandas as pd
import numpy as np
import math
from decimal import Decimal
from scripts.utils import logger
from scripts.utils.constants import AWSConfigs, DataPipeline, ExcelColumns

logging = logger.get_logger(__name__)


def get_all_table_names(excel_path: str, tables_sheet: str = "Tables"):
    df_tables_info = (
        pd.read_excel(excel_path, sheet_name=tables_sheet)
        .dropna(how="all")
        .reset_index(drop=True)
    )
    if ExcelColumns.TABLE_NAME not in df_tables_info.columns:
        raise ValueError(
            f"There is no '{ExcelColumns.TABLE_NAME}' column in sheet {tables_sheet}"
        )

    return df_tables_info[ExcelColumns.TABLE_NAME].tolist()


def extract_table_metadata(
    excel_path: str, table_name: str, config_layer: str, tables_sheet: str = "Tables"
):
    df_tables_info = (
        pd.read_excel(excel_path, sheet_name=tables_sheet)
        .dropna(how="all")
        .reset_index(drop=True)
    )
    df_columns = (
        pd.read_excel(excel_path, sheet_name=table_name)
        .dropna(how="all")
        .reset_index(drop=True)
    )

    table_row = df_tables_info.loc[
        df_tables_info[ExcelColumns.TABLE_NAME] == table_name
    ]
    if table_row.empty:
        raise ValueError(f"Table '{table_name}' does not exist in sheet {tables_sheet}")

    table_config = {}

    # PK and SK
    table_config["table_name"] = table_name
    table_config["config_layer"] = config_layer

    # Table info
    for key, value in table_row.iloc[0].items():
        if key == ExcelColumns.LAYER:
            continue
        if pd.notna(value):
            if isinstance(value, str):
                value = value.encode("utf-8").decode("unicode_escape")
            table_config[key.lower().replace(" ", "_")] = value

    layers = [
        layer.strip() for layer in str(table_row.iloc[0][ExcelColumns.LAYER]).split(",")
    ]
    for layer in layers:
        table_config[f"{layer}_layer"] = layer

    # Columns
    columns = []
    for _, row in df_columns.iterrows():
        column_name = row.get(ExcelColumns.COLUMN_NAME)
        column_type = row.get(ExcelColumns.TYPE)
        if (
            pd.isna(column_name)
            or pd.isna(column_type)
            or not str(column_name).strip()
            or not str(column_type).strip()
        ):
            continue

        col_def = {
            "name": str(column_name).strip(),
            "type": str(column_type).strip(),
        }
        if pd.notna(row.get(ExcelColumns.MAX_LENGTH)):
            col_def["max_length"] = int(row[ExcelColumns.MAX_LENGTH])
        if pd.notna(row.get(ExcelColumns.FORMAT)):
            col_def["format"] = row[ExcelColumns.FORMAT]
        if pd.notna(row.get(ExcelColumns.RANGE)):
            col_def["range"] = [
                int(x.strip()) for x in row[ExcelColumns.RANGE].strip("[]").split(",")
            ]
        if pd.notna(row.get(ExcelColumns.PRECISION)):
            col_def["precision"] = int(row[ExcelColumns.PRECISION])
        if pd.notna(row.get(ExcelColumns.SCALE)):
            col_def["scale"] = int(row[ExcelColumns.SCALE])
        columns.append(col_def)

    table_config["columns"] = columns

    # Validation rules
    validation_rules = []
    not_null_cols = df_columns.loc[
        df_columns[ExcelColumns.NOT_NULL] == True, ExcelColumns.COLUMN_NAME
    ].tolist()
    if not_null_cols:
        validation_rules.append({"rule": "not_null", "column": not_null_cols})

    for _, row in df_columns[df_columns[ExcelColumns.RANGE].notna()].iterrows():
        min_val, max_val = [
            int(x.strip()) for x in row[ExcelColumns.RANGE].strip("[]").split(",")
        ]
        validation_rules.append(
            {
                "rule": "range",
                "column": row[ExcelColumns.COLUMN_NAME],
                "min": min_val,
                "max": max_val,
            }
        )

    pk_cols = df_columns.loc[
        df_columns[ExcelColumns.PRIMARY_KEY] == True, ExcelColumns.COLUMN_NAME
    ].tolist()
    if pk_cols:
        validation_rules.append(
            {
                "rule": "duplicate",
                "primary_key": pk_cols if len(pk_cols) > 1 else pk_cols[0],
            }
        )

    unique_cols = df_columns.loc[
        df_columns[ExcelColumns.UNIQUE] == True, ExcelColumns.COLUMN_NAME
    ].tolist()
    for col in unique_cols:
        validation_rules.append({"rule": "duplicate", "column": col})

    table_config["validation"] = validation_rules

    # Transformation rules
    transformation_rules = {}
    df_transform = df_columns[df_columns[ExcelColumns.TRANSFORM_FUNCTION].notna()]
    for _, row in df_transform.iterrows():
        transform_name = row[ExcelColumns.TRANSFORM_FUNCTION]
        column_name = row[ExcelColumns.COLUMN_NAME]
        transformation_rules.setdefault(transform_name, [])

        if transform_name == "rename":
            prefix = table_name[:-1] if table_name.endswith("s") else table_name
            transformation_rules[transform_name].append(
                {"from": column_name, "to": f"{prefix}_{column_name}"}
            )
        else:
            transformation_rules[transform_name].append({"input": column_name})

    table_config["transformation"] = transformation_rules

    return table_config


# Dynamo
def sanitize_for_dynamo(obj):
    if isinstance(obj, (str, int, bool)):
        return obj

    if isinstance(obj, list):
        cleaned_list = []
        for item in obj:
            val = sanitize_for_dynamo(item)
            if val is not None:
                cleaned_list.append(val)
        return cleaned_list

    if isinstance(obj, dict):
        cleaned_dict = {}
        for k, v in obj.items():
            val = sanitize_for_dynamo(v)
            if val is not None:
                cleaned_dict[k] = val
        return cleaned_dict

    if pd.isna(obj):
        return None

    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return Decimal(str(obj))

    if isinstance(obj, (np.integer, np.floating)):
        val = obj.item()
        if isinstance(val, float):
            if math.isnan(val) or math.isinf(val):
                return None
            return Decimal(str(val))
        return val

    return obj


def put_item_to_dynamo(table_config: dict, dynamo_table_name: str):
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(dynamo_table_name)

    safe_config = sanitize_for_dynamo(table_config)

    table.put_item(Item=safe_config)
    logging.info(
        f"Loaded to DynamoDB successfully - Table: {safe_config['table_name']} | Layer: {safe_config['config_layer']}"
    )


def replace_decimals(obj):
    if isinstance(obj, list):
        return [replace_decimals(i) for i in obj]
    elif isinstance(obj, dict):
        return {k: replace_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        else:
            return float(obj)
    return obj


def get_table_config_from_dynamo(
    table_name: str, config_layer: str, dynamo_table_name: str
) -> dict:
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(dynamo_table_name)
    try:
        response = table.get_item(
            Key={"table_name": table_name, "config_layer": config_layer}
        )
        item = response.get("Item")
        if item:
            clean_item = replace_decimals(item)

            logging.info(
                f"Retrieved config successfully for {table_name} (Layer: {config_layer})"
            )
            return clean_item
        else:
            logging.warning(
                f"No configuration found for {table_name} (Layer: {config_layer})"
            )
            return None

    except Exception as e:
        logging.error(f"Error fetching data from DynamoDB: {str(e)}")
        raise


def sync_single_table(
    excel_path: str, table_name: str, config_layer: str, dynamo_table_name: str
):
    logging.info(f"Building table config: {table_name}")
    table_config = extract_table_metadata(excel_path, table_name, config_layer)
    put_item_to_dynamo(table_config, dynamo_table_name)


def sync_all_tables(excel_path: str, config_layer: str, dynamo_table_name: str):
    logging.info("Scanning all tables in the Excel file...")
    all_tables = get_all_table_names(excel_path)

    for table_name in all_tables:
        sync_single_table(excel_path, table_name, config_layer, dynamo_table_name)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Sync Excel metadata configuration to DynamoDB and retrieve configs."
    )

    parser.add_argument(
        "--excel-path",
        default=DataPipeline.TEMP_EXCEL_PATH,
        help="Path to the source Excel file.",
    )
    parser.add_argument(
        "--dynamo-table",
        default=AWSConfigs.DYNAMO_TABLE_CONFIG,
        help="Target DynamoDB table name for storing or retrieving configurations.",
    )
    parser.add_argument(
        "--layer",
        default=DataPipeline.LAYER_L0,
        help="Configuration layer used as the Sort Key (e.g., l0, l1, l2).",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--all",
        action="store_true",
        help="Update configurations for all tables found in the 'Tables' sheet.",
    )
    group.add_argument(
        "--table-name",
        type=str,
        help="Specify a single table name to update (e.g., customers).",
    )
    group.add_argument(
        "--get-config",
        type=str,
        metavar="TABLE_NAME",
        help="Retrieve and print the configuration of a specific table from DynamoDB (e.g., --get-config customers).",
    )

    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()

    if args.get_config:
        config = get_table_config_from_dynamo(
            table_name=args.get_config,
            config_layer=args.layer,
            dynamo_table_name=args.dynamo_table,
        )
        if config:
            print(config)

    elif args.all:
        sync_all_tables(
            excel_path=args.excel_path,
            config_layer=args.layer,
            dynamo_table_name=args.dynamo_table,
        )

    elif args.table_name:
        sync_single_table(
            excel_path=args.excel_path,
            table_name=args.table_name,
            config_layer=args.layer,
            dynamo_table_name=args.dynamo_table,
        )
