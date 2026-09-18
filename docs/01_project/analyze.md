# **Analyze Mock Project**
## Overview
- type: batch processing
- Schedule: every day

## Data
- customers: customers' information (id, name, birthday, address, kpi).
- province: provinces' information (province id, province name...).
- products: products' information.
- orders: transactions/orders' information.

# Layer:
```
rcv/{schema_name}/{table_name}/yyyy/mm/dd/{table_name}.csv
l0/{schema_name}/{table_name}/yyyy/mm/dd/{table_name}.csv
quarantine/{schema_name}/{table_name}/yyyy/mm/dd/{table_name}.csv
l1/{schema_name}/{table_name}/yyyy/mm/dd/{table_name}.parquet
audit/{schema_name}/{table_name}/yyyy/mm/dd/{table_name}.parquet
```

- layer: rcv, l0, quarantine, l1, audit
    - rcv: Landing layer that receives raw input data from source systems.
    - l0: Processing layer where data from the RCV layer undergoes initial validation and transformation.
    - quarantine: Storage layer for files that are empty, unreadable, corrupted, or otherwise fail file-level validation (schema drift).
    - l1: Curated layer where data from the L0 layer undergoes business validation and transformations.
    - audit: Storage layer for records that fail record-level validation, such as null values, duplicate keys, invalid data types, or business rule violations.
- schema_name: business definition. Final Decision: "retail".
- table_name: customers, orders, products, province.

## Database Load
- Requirement: The solution must demonstrate all three loading strategies: Upsert, Full Load (Truncate and Insert), and Append-Only.
- Expected mapping from raw data:
    - Upsert: customers, products
        - customers: Upsert is required because customers information may change over time, and only the latest state needs to be retained.
        - products: Similar to customers data, products attributes may be updated, so the latest version should be maintained through upsert operations.
    - Full Load (Truncate and Insert): province
        - province: Reference data with infrequent changes. A full refresh using truncate and insert is a simple and appropriate approach.
    - Append-Only: orders
        - orders: Append-only is used to preserve the history of order records over time, enabling tracking and analysis of changes and business events.

## Process & Validation
- RCV → L0
    - Validation:
        - Verify that the source file exists.
        - Verify that the file is not empty. Empty files are moved to the Quarantine layer.
        - Verify that the file can be read successfully. Unreadable or corrupted files are moved to the Quarantine layer.
        - Detect schema drift by comparing the incoming file schema against the expected schema definition. Files with schema mismatches are moved to the Quarantine layer.
    - Transformation:
        - Add metadata columns such as process_date and source_file to support data lineage, auditing, and troubleshooting.

- L0 → L1
    - Validation:
        - Perform record-level validation based on business and data quality rules.
        - Examples include null checks for mandatory columns, data type validation, duplicate detection, and other configurable validation rules.
        - Invalid records are redirected to the Audit layer.
    - Transformation:
        - Apply business transformations, such as splitting customer_name into first_name and last_name.
        - Standardize and enrich data where required.
        - Cast datatype for every columns.
        - Convert the output format from CSV to Parquet for optimized storage and downstream processing.

- L1 → RDS PostgreSQL
    - Loading:
        - Apply the appropriate loading strategy based on the target table:
            - Upsert for customers and products tables.
            - Full Load (Truncate and Insert) for the province table.
            - Append-Only for the orders table.
        - Ensure data is loaded into PostgreSQL according to the business requirements and target table characteristics.


## Tables và Schemas
- Cấu trúc lưu trữ
```
rcv
└── retail
    ├── customers
    |   └── yyyy
    |       └── mm
    |           └── dd
    |               └── customers.csv
    ├── province
    ├── products
    └── orders

quarantine
└── retail
    ├── customers
    |   └── yyyy
    |       └── mm
    |           └── dd
    |               └── customers.csv
    ├── province
    ├── products
    └── orders

l0
└── retail
    ├── customers
    |   └── yyyy
    |       └── mm
    |           └── dd
    |               └── customers.csv
    ├── province
    ├── products
    └── orders

audit
└── retail
    ├── customers
    |   └── yyyy
    |       └── mm
    |           └── dd
    |               └── customers.parquet
    ├── province
    ├── products
    └── orders

l1
└── retail
    ├── customers
    |   └── yyyy
    |       └── mm
    |           └── dd
    |               └── customers.parquet
    ├── province
    ├── products
    └── orders

```

### RCV
- customers
```
id, name, birthday, address, kpi
```
- province
```
id, name
```
- products
```
id, name, unit_price
```
- orders
```
id, customer_id, product_id, quantity, price, order_date
```

### L0
- customers
```
id, name, birthday, address, kpi, process_date, source_file
```
- province
```
id, name, process_date, source_file
```
- products
```
id, name, unit_price, process_date, source_file
```
- orders
```
id, customer_id, product_id, quantity, price, order_date, process_date, source_file
```

### L1
- customers
```
customer_id, first_name, last_name, birthday, address, address_province, kpi, process_date, source_file
```

- province
```
province_id, province_name, process_date, source_file
```

- products
```
product_id, product_name, unit_price, process_date, source_file
```

- orders
```
orders_id, customer_id, product_id, quantity, unit_price, total_amount, order_date, process_date, source_file
```

### Quarantine
- After file-level validation fails (rcv to l0), file is coppied from rcv to l0.  


### Audit
- From L0 to L1, records which fail business validation (not null, duplicate, datatype, ...) are written to audit.
- Each table gonna have _source_index, error_type, error_rule, error_column, error_message for data tracking
- customers
```
_source_index,id,name,birthday,address,kpi,process_date,source_file,error_type,error_rule,error_column,error_message
```
- products, orders, province: same.

## Tech Stack & Deployment Environment==
- Python: Core language for data processing and pipeline development.
- YAML: Configuration-driven validation, transformation, and metadata management.
- AWS Services
    - EC2: Hosts Apache Airflow for workflow orchestration.
    - Amazon S3: Stores data layers (rcv/, l0/, quarantine/, audit/, l1/), DAGs, and configurations.
    - AWS Lambda: Performs file-level validation and lightweight data processing.
    - Amazon RDS PostgreSQL: Serves as the final data warehouse/storage layer.
    - Amazon DynamoDB: Tracks pipeline execution status and audit metadata.
    - Amazon SNS: Sends alerts when pipeline stages fail.
    - AWS Secrets Manager: Manages database credentials and sensitive configuration.
    - Amazon CloudWatch: Monitors logs, metrics, and pipeline health.
    - Network Architecture
        - VPC
        - Public Subnet: EC2 (Airflow).
        - Private Subnet: RDS PostgreSQL.
        - S3 Gateway Endpoint for private access to S3 resources.

## More
- Idempotency:
    - Each processing stage is designed to be idempotent, ensuring that rerunning the same pipeline with the same input produces identical results without creating duplicates or inconsistencies.

- Large Data Processing:
    - The solution is designed to handle large datasets efficiently through partitioned storage on S3, Parquet format optimization, and scalable processing services such as AWS Lambda and AWS Glue.