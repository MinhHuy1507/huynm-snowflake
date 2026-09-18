# Validation and Transformation Functions from rcv/ to l0/

## 1. validate_file

### Purpose
- Used to validate the input file:
    - Whether the file exists.
    - Whether the file has the correct format.
    - Whether the file is readable.
    - Whether the file is empty.
    - Whether the file contains only a header row.
- If the file is valid, the data is successfully loaded.
- If the file is invalid, an error message is returned and the file is moved to quarantine/ in specific scenarios.

### Input
- A file path in rcv following the format:

`rcv/schema_name/table_name/yyyy/mm/dd/table_name.csv`

### Output
- Success: Data is successfully loaded.
- Failure: Returns an error message and writes the file to quarantine/ in specific scenarios using the format:

`quarantine/schema_name/table_name/yyyy/mm/dd/table_name.csv`

### Scenarios

| Scenario | Expected Result |
|----------|----------------|
| File does not exist | Message `File not found - (file_path)` |
| File size = 0 bytes | Message `File empty - (file_path)` and write file to quarantine/ |
| File is corrupt or unreadable | Message `File is not readable - (file_path)` and write file to quarantine/ |
| File contains only header | Message `File contains only header without data - (file_path)` and write file to quarantine/ |
| File is valid and contains data | Data is successfully loaded |

---

## 2. validate_schema

### Purpose
- Used to compare the schema of the processing data against the predefined schema:
    - New column added.
    - Missing column.
    - Both added and missing columns.
    - Incorrect column order.
- If schema is valid, no action is performed.
- If schema is invalid, an error message is returned and the file is written to quarantine/.

### Input
- Predefined table schema.
- Schema of the processing dataset.

### Output
- Success: Processing data matches the predefined schema.
- Failure: Returns an error message and writes the file to quarantine/ using the format:

`quarantine/schema_name/table_name/yyyy/mm/dd/table_name.csv`

### Scenarios

| Scenario | Expected Result |
|----------|----------------|
| New column added | Message `Schema mismatch. Expected {expected columns}, got {actual columns}` |
| Missing column | Message `Schema mismatch. Expected {expected columns}, got {actual columns}` |
| Both added and missing columns | Message `Schema mismatch. Expected {expected columns}, got {actual columns}` |
| Incorrect column order | Message `Schema mismatch. Expected {expected columns}, got {actual columns}` |

---

# Validation and Transformation Functions from l0/ to l1/

## 1. validate_not_null

### Purpose
- Checks whether a column contains NULL values.
- Generates a validation condition used to determine whether each record satisfies the NOT NULL rule.

### Input
- Processing dataset.
- Column to validate.

### Output
- Returns a validation condition representing the result for each record.
- Validation condition returns:
    - TRUE → Record satisfies rule.
    - FALSE → Record violates rule.

### Scenarios

| Scenario | Expected Result |
|----------|----------------|
| Record contains valid value | Validation result = TRUE |
| Record contains NULL | Validation result = FALSE |
| Dataset contains multiple records | Validation result generated for each record |

### Example

| id | validation_result |
|----|-------------------|
| 1 | TRUE |
| NULL | FALSE |
| 3 | TRUE |
| 4 | TRUE |
| NULL | FALSE |

---

## 2. validate_unique

### Purpose
- Checks whether one or more columns contain duplicate values.
- Generates a validation condition used to determine whether each record satisfies the uniqueness rule.
- NULL values are ignored.

### Input
- Processing dataset.
- Column(s) to validate.

### Output
- Returns a validation condition representing the result for each record.
- Validation condition returns:
    - TRUE → Record satisfies rule.
    - FALSE → Record violates rule.

### Scenarios

| Scenario | Expected Result |
|----------|----------------|
| Record contains valid value | Validation result = TRUE |
| Record contains invalid value | Validation result = FALSE |
| Dataset contains multiple records | Validation result generated for each record |

### Example

| id | name | validation_result |
|----|------|------------------|
| 1 | Huy | TRUE |
| NULL | NULL | TRUE |
| 3 | A | FALSE |
| 3 | A | FALSE |
| 3 | Huy | TRUE |

Explanation:
- Records with duplicate `(id, name)` combinations are marked as FALSE.
- Records containing NULL values are ignored.

---

## 3. validate_range

### Purpose
- Checks whether a column value falls within a predefined range.
- Generates a validation condition used to determine whether each record satisfies the rule.
- NULL values are ignored.

### Input
- Processing dataset.
- Column to validate.
- Minimum allowed value.
- Maximum allowed value.

### Output
- Returns a validation condition representing the result for each record.
- Validation condition returns:
    - TRUE → Record satisfies rule.
    - FALSE → Record violates rule.

### Example

Range: min = 0, max = 100

| kpi | validation_result |
|------|------------------|
| -1.0 | FALSE |
| 0 | TRUE |
| 90.0 | TRUE |
| 101.0 | FALSE |
| NULL | TRUE |

Explanation:
- Values within `[0,100]` return TRUE.
- Values outside the range return FALSE.
- NULL values return TRUE.

---

## 4. validate_datatype

### Purpose
- Checks whether a column contains values matching the required data type.
- Generates a validation condition used to determine whether each record satisfies the rule.
- NULL values are ignored.

### Input
- Processing dataset.
- Column to validate.
- Expected data type.

### Output
- Returns a validation condition representing the result for each record.
- Validation condition returns:
    - TRUE → Record satisfies rule.
    - FALSE → Record violates rule.

### Example

Datatype: `float`

| kpi | validation_result |
|------|------------------|
| -1.0 | TRUE |
| huy | FALSE |
| 90.0 | TRUE |
| NULL | TRUE |

Explanation:
- Float values and NULL return TRUE.
- Other values return FALSE.

---

## 5. split_customers_name

### Purpose
- Standardizes customer names into two columns:
    - first_name: last word of the full name.
    - last_name: remaining part before first_name.

Example:

`Ngo Minh Huy`

becomes:

- first_name = Huy
- last_name = Ngo Minh

### Input
- Processing dataset.
- name column.

### Output

| Column | Description |
|----------|-------------|
| first_name | Last word of the full name |
| last_name | All words before first_name |

### Scenarios

| Scenario | Expected Result |
|----------|----------------|
| NULL value | first_name and last_name are NULL |
| Single-word name | first_name contains value, last_name = NULL |
| Two-word name | first_name is last word, last_name is first word |
| Multi-word name | first_name is last word, last_name is remaining words |
| Multiple consecutive spaces | Spaces normalized before splitting |
| Dataset contains N records | Output still contains N records |
| Other columns unchanged | Only output columns are added/updated |

### Example

| name | first_name | last_name |
|--------|-----------|------------|
| NULL | NULL | NULL |
| Huy | Huy | NULL |
| Ngo Huy | Huy | Ngo |
| Ngo Minh Huy | Huy | Ngo Minh |
| Ngo Minh     Huy | Huy | Ngo Minh |

---

## 6. split_customers_address

### Purpose
- Standardizes the customers.address column into:
    - address: cleaned address value.
    - address_province: extracted province.

Rule:

`<house number> <street name>, <province/city>`

Example:

Input:

`123 Nguyen Ai Quoc, Ho Chi Minh`

Output:
- address = `123 Nguyen Ai Quoc, Ho Chi Minh`
- address_province = `Ho Chi Minh`

### Input
- Processing dataset.
- address column.

### Output

| Column | Description |
|----------|-------------|
| address | Cleaned address |
| address_province | Extracted province |

### Scenarios

| Scenario | Expected Result |
|----------|----------------|
| NULL value | address and address_province are NULL |
| Address without comma | address cleaned, address_province = NULL |
| Address contains only one word | address cleaned, address_province = NULL |
| Address contains province at the end | province extracted |
| Multiple commas | last non-empty component becomes province |
| Leading/trailing commas | extra commas removed |
| Multiple consecutive spaces | spaces normalized |
| Empty province after cleanup | address_province = NULL |
| Dataset contains N records | Output still contains N records |
| Other columns unchanged | Only output columns are updated |

### Example

| Input Address | Output Address | Output Province |
|-------------|---------------|----------------|
| NULL | NULL | NULL |
| Ho Chi Minh | Ho Chi Minh | NULL |
| 123 Nguyen Ai Quoc | 123 Nguyen Ai Quoc | NULL |
| 123 Nguyen Ai Quoc, Ho Chi Minh | 123 Nguyen Ai Quoc, Ho Chi Minh | Ho Chi Minh |
| 123 Nguyen Ai Quoc, District 1, Ho Chi Minh | 123 Nguyen Ai Quoc, District 1, Ho Chi Minh | Ho Chi Minh |
| ,123 Nguyen Ai Quoc, Ho Chi Minh, | 123 Nguyen Ai Quoc, Ho Chi Minh | Ho Chi Minh |
| 123 Nguyen Ai Quoc, , Ho Chi Minh | 123 Nguyen Ai Quoc, Ho Chi Minh | Ho Chi Minh |

---

## 7. rename_columns

### Purpose
- Standardizes column names according to predefined rules.

### Input
- Processing dataset.
- Source column name.
- Target column name.

### Output
- Columns are renamed according to configuration.

### Scenarios

| Scenario | Expected Result |
|----------|----------------|
| Source column exists | Column is renamed |
| Rename one column | Only specified column changes |
| Rename multiple columns | All mappings are applied |
| Dataset contains N records | Output still contains N records |
| Data values unchanged | Only column names change |
| Record order unchanged | Record order preserved |
| Columns not mapped | Remain unchanged |
| Source columns do not exist | Message `Columns not found: (columns input)` |

### Example

Input:

| id | name |
|----|------|
| 1 | Huy |

Output:

| customer_id | customer_name |
|-------------|---------------|
| 1 | Huy |

---

## 8. filter_columns

### Purpose
- Selects only required columns from the dataset:
    - Removes unnecessary columns.
    - Standardizes output schema.
    - Reduces storage and processing volume.

### Input
- Processing dataset.
- Columns to keep.

### Output
- Contains only columns defined in table configuration.

### Scenarios

| Scenario | Expected Result |
|----------|----------------|
| Selected columns exist | Output contains only the configured columns |
| Dataset contains columns not included in the output schema | Those columns are removed |
| Dataset contains N records | Output still contains N records |
| Data values remain unchanged | Values in the retained columns are preserved |
| Output column order is defined | Output column order must match the configured output schema |
| Filter columns do not exist in the dataset | Message `Columns not found: (columns filter)` |

## 9. cast_datatype

### Purpose
- Converts a column to the target data type defined in the table configuration.
- Standardizes data types before loading data into downstream layers or databases.
- Supports optional date format definitions for date-based columns.

### Input
- Processing dataset.
- Column to be converted.
- Column configuration containing:
    - Data type (`type`)
    - Optional date format (`format`)

### Output
- Returns the converted column using the target data type.
- If the data type is unsupported, returns an error message.

### Supported Data Types

| Config Type | Output Type |
| ----------- | ----------- |
| string | String |
| int | Integer |
| integer | Integer |
| decimal | Decimal |
| double | Double |
| date | Date |
| datetime | Datetime |
| timestamp | Timestamp |

### Scenarios

| Scenario | Expected Result |
| -------- | --------------- |
| Column type is in the supported data types above | Values are converted to the matching data type |
| Value cannot be converted to target datatype | Output value becomes NULL |
| Input contains NULL values | NULL values remain NULL |
| Dataset contains N records | Output still contains N records |
| Data type is not supported | Message `Unsupported type: {type} in column {column}` |

### Examples

#### Example 1: Integer Conversion

Input:

| id |
|----|
| 1 |
| 2 |
| abc |
| NULL |

Configuration:

```yaml
type: int
```

Output:

| id |
|----|
| 1 |
| 2 |
| NULL |
| NULL |

#### Example 2: Date Conversion with Defined Format

Input:

| birthday |
|----------|
| 2026-09-09 |
| 2026-01-15 |
| invalid |
| NULL |

Configuration:

```yaml
type: date
format: YYYY-MM-DD
```

Output:

| birthday |
|----------|
| 2026-09-09 |
| 2026-01-15 |
| NULL |
| NULL |

#### Example 3: Datetime Conversion

Input:

| created_at |
|------------|
| 2026-09-09 10:15:00 |
| 2026-09-10 08:30:00 |
| invalid |

Configuration:

```yaml
type: datetime
```

Output:

| created_at |
|------------|
| 2026-09-09 10:15:00 |
| 2026-09-10 08:30:00 |
| NULL |

#### Example 4: Unsupported Datatype

Configuration:

```yaml
type: binary
```

Output:

```text
Unsupported type: binary in column customer_id
```

# Functions from l0/ to l1/
## 1. create_table

### Purpose
- Creates a database table based on the table configuration.
- Ensures the system can automatically initialize tables for data storage.
- Supports defining:
    - Column names
    - Data types
    - Constraints

### Input
- Table schema definition, including:
    - Column name
    - Data type
    - Constraints

### Output
- Table is created in the database.

### Scenarios

| Scenario | Expected Result |
| -------- | --------------- |
| Table does not exist | Table is created based on the defined schema |
| Table already exists | No action is performed |
| Schema contains unsupported database definition | System error message is returned |

---

## 2. append_only

### Purpose
- Loads data from the l1/ layer on S3 into the database using the append-only method.
- Append-only means inserting new records into an existing table without modifying or removing existing data.

### Input
- Data read from l1.

### Output
- Data is loaded into the database using append-only mode.
- System errors are captured and returned when they occur.

### Scenarios

| Scenario | Expected Result |
| -------- | --------------- |
| Table does not exist | Error Message `There is no table (table_name)` |
| Table exists but contains no data | Data is inserted successfully |
| Table already contains data | New data is appended without overwriting existing records |
| New data contains keys that already exist in the table | Database constraint violation is returned |

---

## 3. truncate_and_insert

### Purpose
- Loads data from the l1/ layer on S3 into the database using the truncate-and-insert method.
- Truncate and insert means removing all existing data from the target table while preserving the schema, indexes, and constraints, then inserting the new dataset.

### Input
- Data read from l1.

### Output
- Data is loaded into the database using the truncate-and-insert method.
- Errors are captured and returned.

### Scenarios

| Scenario | Expected Result |
| -------- | --------------- |
| Table does not exist | Error Message `There is no table (table_name)` |
| Table exists but contains no data | Data is inserted successfully |
| Table already contains data | Existing records are removed and replaced with the new dataset |

---

## 4. upsert

### Purpose
- Loads data from the l1/ layer on S3 into the database using the upsert method.
- Upsert updates existing records and inserts new records based on a unique identifier such as a Primary Key or Business Key.

### Input
- Data read from l1.

### Output
- Data is loaded into the database using the upsert method.
- Errors are captured and returned.

### Scenarios

| Scenario | Expected Result |
| -------- | --------------- |
| Table does not exist | Error Message `There is no table (table_name)` |
| Table exists but contains no data | Data is inserted successfully |
| Table already contains data | Records with matching keys are updated, and records with new keys are inserted |