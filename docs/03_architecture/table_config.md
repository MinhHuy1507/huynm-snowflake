# Table Configuration

Table configuration files define how each table is received, validated, transformed, and loaded into Snowflake. They are stored under the `config` directory and are organized by data layer:

```text
config/
	rcv/   # Received data
	l0/    # Validated and standardized data
	l1/    # Curated data loaded into the database
```

Each table has its own YAML file, for example `customers.yaml`. The same table can have a different configuration in each layer because each layer has a different purpose.

## Configuration by Layer

### RCV layer

The RCV configuration describes the raw data received from the source system. It defines the table identity, the storage layers and file formats, the incoming columns, and basic checks that must pass before processing.

Example: `config/rcv/customers.yaml`

```yaml
table_name: customers
schema_name: retail

rcv_layer: rcv
l0_layer: l0
quarantine_layer: quarantine

rcv_format: csv
l0_format: csv
quarantine_format: csv
```

The main fields are:

- `table_name`: The source table name.
- `schema_name`: The business schema or domain, such as `retail`.
- `rcv_layer`, `l0_layer`, `quarantine_layer`: The locations used for received, processed, and rejected data.
- `rcv_format`, `l0_format`, `quarantine_format`: The file format used in each location.

The `columns` section defines the expected source structure. For `customers`, `id`, `name`, and `address` are strings, `birthday` is a date using the `YYYY-MM-DD` format, and `kpi` is a decimal value.

The complete column configuration is:

```yaml
columns:
	- name: id
		type: string
	- name: name
		type: string
	- name: birthday
		type: date
		format: YYYY-MM-DD
	- name: address
		type: string
	- name: kpi
		type: decimal
```

The `validation` section enables file-level and schema-level checks:

```yaml
validation:
	validate_file: true
	validate_schema: true
```

If the input file or its structure is invalid, the data should not continue as normal input. It can be sent to the quarantine layer for investigation.

### L0 layer

The L0 configuration describes data after it has passed the initial checks. This layer applies data quality rules and simple transformations while keeping the data close to its source form.

Example: `config/l0/customers.yaml`

```yaml
l0_layer: l0
l1_layer: l1
audit_layer: audit

l0_format: csv
l1_format: parquet
audit_format: parquet
```

The L0 configuration also defines the stages used to access the data, such as `stage_l0`, `stage_l1`, and `stage_audit`.

The L0 columns are still close to the source columns. Technical columns such as `process_date` and `source_file` are included because they are needed for traceability:

```yaml
columns:
	- name: id
		type: string
	- name: name
		type: string
	- name: birthday
		type: date
		format: YYYY-MM-DD
	- name: address
		type: string
	- name: kpi
		type: decimal
	- name: process_date
		type: timestamp
	- name: source_file
		type: string
```

For `customers`, the validation rules require the important fields and technical fields (`process_date` and `source_file`) to be present. The `kpi` value must be between 0 and 100, and `id` must be unique:

```yaml
validation:
	- rule: not_null
		column: [id, name, birthday, address, kpi, source_file, process_date]
	- rule: range
		column: kpi
		min: 0
		max: 100
	- rule: duplicate
		primary_key: id
```

The transformation section prepares the data for L1. The complete transformation configuration for `customers` is:

```yaml
transformation:
	split_name:
		- from: name
			to: [first_name, last_name]
	split_address:
		- from: address
			to: [address, address_province]
	rename:
		- from: id
			to: customer_id
	filter_columns:
		- output: [customer_id, first_name, last_name, birthday, address, address_province, kpi, process_date, source_file]
```

The transformations work as follows:

- `split_name`: Reads the source `name` column and creates `first_name` and `last_name`. For example, a full name is divided into its first-name and last-name parts.
- `split_address`: Reads `address` and creates the standardized `address` and `address_province` columns. The address value is kept while the province is extracted into a separate column.
- `rename`: Changes the source key `id` to the business name `customer_id`. This makes the key name consistent with the L1 table.
- `filter_columns`: Keeps only the columns required by L1 and removes any temporary or unlisted columns. The output order is also defined here.

After transformation, the L0 output has these columns:

```text
customer_id, first_name, last_name, birthday, address,
address_province, kpi, process_date, source_file
```

The names in this output must match the columns expected by the L1 configuration.

### L1 layer

The L1 configuration describes the curated table used by downstream applications and reporting. It contains the final column names, database types, constraints, and loading strategy.

Example: `config/l1/customers.yaml`

```yaml
schema_name: retail
table_name: customers
l1_layer: l1
l1_format: parquet
```

In this layer, each column can include database-specific metadata. For example, `customer_id` is a `VARCHAR` with a maximum length of 20 and is the primary key. `first_name`, `last_name`, `birthday`, `address`, `address_province`, `kpi`, `process_date`, and `source_file` are marked as required where appropriate. The `kpi` range is also defined as 0 to 100.

The complete L1 column configuration is:

```yaml
columns:
	- name: customer_id
		type: string
		db_type: VARCHAR
		max_length: 20
		primary_key: true

	- name: first_name
		type: string
		db_type: VARCHAR
		max_length: 100
		not_null: true

	- name: last_name
		type: string
		db_type: VARCHAR
		max_length: 100
		not_null: true

	- name: birthday
		type: date
		db_type: DATE
		not_null: true

	- name: address
		type: string
		db_type: VARCHAR
		max_length: 100
		not_null: true

	- name: address_province
		type: string
		db_type: VARCHAR
		max_length: 100
		not_null: true

	- name: kpi
		type: double
		db_type: DOUBLE
		not_null: true
		range: [0, 100]

	- name: process_date
		type: timestamp
		db_type: TIMESTAMP
		not_null: true

	- name: source_file
		type: string
		db_type: VARCHAR
		max_length: 255
		not_null: true
```

The `load_database` section controls how the final table is updated:

```yaml
load_database:
	load_strategy: upsert
	primary_key: customer_id
```

`upsert` inserts new records and updates existing records identified by `customer_id`.
