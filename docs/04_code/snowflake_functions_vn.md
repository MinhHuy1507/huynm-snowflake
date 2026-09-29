# **Các hàm validate và transform của Snowflake từ l0 sang l1**
# Validation
## **1. validate_not_null**
### Overview
- Hàm tạo sql expression để validate not null
### Input
- column: str | list
- Có thể xử lý 1 và n columns cùng lúc
### Output
- sql text expression: str
### Logic
```sql
CASE WHEN NULLIF(TRIM({col}::STRING), '') IS NULL THEN 'not_null({col})' END
```
### Các trường hợp
- col='' (empty) -> 'not_null({col})'
- col=' ' (only space) -> 'not_null({col})'
- col= Null -> 'not_null({col})'
- col='Huy' -> pass

## **2. validate_unique**
### Input
- column: str | list
- Có thể xử lý 1 và n columns cùng lúc
### Output
- sql text expression: str

### Các trường hợp
- Ví dụ validate id
- id='' hoặc ' ' hoặc Null -> Không vi phạm và không trả kết quả gì (null sẽ do validate_not_null xử lý nếu được định nghĩa; nếu không thì được chấp nhận).
- Nếu id bị trùng -> toàn bộ records có giá trị trùng bị đánh dấu 'unique(id)'.

### Logic
```python
partition_expr = ", ".join(f"NULLIF(TRIM({col}::STRING), '')" for col in column)
all_columns_present = " AND ".join(
    f"NULLIF(TRIM({col}::STRING), '') IS NOT NULL" for col in column
)
expr = [f"""CASE WHEN {all_columns_present}
    AND COUNT(*) OVER(PARTITION BY {partition_expr}) > 1
    THEN 'unique({','.join(column)})' END"""]
```
- Nếu cần validate unique trên nhiều cột (composite keys), vẫn hoạt động

## **3. validate_range**
### Input
- column: str | list
- min: float
- max: float
### Output
- sql text expression: str
### Các trường hợp
- record='' or ' ' or Null -> pass
- record > max or < min -> 'range(col)'
### Logic
```sql
CASE WHEN NULLIF(TRIM({col}::STRING), '') IS NOT NULL
    AND TRY_TO_DOUBLE({col}) NOT BETWEEN {min} AND {max} THEN 'range({col})' END"
```

## **4. validate_datatype**
### Input
- table_config: dict
### Output
- sql text expression: str
### Các trường hợp
- record='' or ' ' or Null -> pass
- record cùng type
- record khác type -> Try_to_* null -> 'datatype(col)'
### Logic
```python
TYPE_MAPPING = {
    "integer": "TRY_TO_NUMBER({column})",
    "decimal": "TRY_TO_DECIMAL({column})",
    "date": "TRY_TO_DATE({column}{format})",
    "timestamp": "TRY_TO_TIMESTAMP({column})",
    "boolean": "TRY_TO_BOOLEAN({column})",
}

expr_col = (
    f"CASE WHEN NULLIF(TRIM({col_name}::STRING), '') IS NOT NULL "
    f"AND {cast_expr} IS NULL THEN 'datatype({col_name})' END"
)
```
- Đọc kiểu dữ liệu của cột từ table_config.yaml và ánh xạ sang hàm TRY_TO_* trong Snowflake. Hàm này sẽ trả về NULL nếu giá trị không đúng kiểu.


## **5. validate_l0_to_l1**
### Overview
- Hàm sẽ đọc table config (customers_config), duyệt qua các luật validate có trong table.yaml, gọi thực hiện các hàm validate tương ứng.
- Tạo 1 sql text tạo view, dùng hàm ARRAY_CONSTRUCT_COMPACT, để tổng hợp tất cả lỗi validate.

### Input
- table_config: dict
- schema: str
- view_input: str
- view_output: str
- ex: (customers_config, "retail", "vw_customers", "vw_validation_customers")

### Output
- sql text: str

### Logic
- Tương ứng với các luật validate trong config, các hàm sẽ được gọi thực hiện để tạo ra 1 sql expression, tổng hợp lại bằng ARRAY_CONSTRUCT_COMPACT.
- ex: customers cần validate datatype birthday và unique id
    - Gọi hàm thực hiện validate_datatype, output:
    ```sql
    CASE WHEN NULLIF(TRIM(birthday::STRING), '') IS NOT NULL 
        AND {TRY_TO_DATE(birthday, "YYYY-MM-dd")} IS NULL THEN 'datatype(birthday)' END
    ```
    - Duyệt các validate rule còn lại, gọi hàm validate_unique, output:
    ```sql
    CASE WHEN NULLIF(TRIM(id::STRING), '') IS NOT NULL
        AND COUNT(*) OVER(PARTITION BY NULLIF(TRIM(id::STRING), '')) > 1 THEN 'unique(id)' END
    ```
    - Tổng hợp bằng ARRAY_CONSTRUCT_COMPACT và tạo view
    ```sql
    CREATE OR REPLACE VIEW retail.vw_validation_customers AS
    SELECT
        *,
        ARRAY_CONSTRUCT_COMPACT(
            CASE WHEN NULLIF(TRIM(birthday::STRING), '') IS NOT NULL 
                AND {TRY_TO_DATE(birthday, "YYYY-MM-dd")} IS NULL THEN 'datatype(birthday)' END,
            CASE WHEN NULLIF(TRIM(id::STRING), '') IS NOT NULL
                AND COUNT(*) OVER(PARTITION BY NULLIF(TRIM(id::STRING), '')) > 1 THEN 'unique(id)' END
        ) AS validation_errors
    FROM retail.vw_customers
    ```
### Các trường hợp
- birthday='2026-08-08', id = 'C01' (id không trùng) -> pass
- birthday='2026/08/08', id = 'C02' (id không trùng) -> ['datatype(birthday)']
- birthday='2026/08/08', id = 'C03' (id bị trùng) -> ['datatype(birthday)', 'unique(id)']

# Transformation
## **1. split_customers_name**
### Input
- transform_rules: dict. ex: {"from": "name", "to": ["first_name", "last_name"]}
- column_expression: dict. ex: {"id": "id", "name": "name", ... {col}: {col_expression}}
    - Được truyền vào bởi hàm transform_l0_to_l1 để phục vụ việc tổng hợp các phép biến đổi. Ví dụ:
    ```sql
    -- column_expression = {"customer_id": "id", "first_name": "expression(first_name)", "last_name": "expression(last)name)"}
    SELECT
        id AS customer_id,
        expression(first_name) AS first_name,
        expression(last_name) AS last_name
    FROM ...
    ```
### Output
- column_expression: dict
- ex:
```python
column_expression= {
    "first_name": "NULLIF(REGEXP_SUBSTR(TRIM(name), '[^[:space:]]+$'), '')",
    "last_name": "NULLIF(TRIM(REGEXP_REPLACE(TRIM(name), '[^[:space:]]+$', '')), '')"
}
```

### Các trường hợp
- name = '' or ' ' or Null -> first_name = last_name = Null
- name = 'Huy' -> first_name = 'Huy', last_name = Null
- name = 'Ngo Minh Huy' -> first_name = 'Huy', last_name = 'Ngo Minh'

## **2. split_customers_address**
### Input
- transform_rules: dict. ex: {"from": "address", "to": ["address", "address_province"]}
- column_expression: dict.

### Output
- column_expression: dict
- ex:
```python
column_expression= {
    "address": "NULLIF(TRIM(REGEXP_REPLACE(address, ',\\\\s*[^,]+$', '')), '')",
    "address_province": "NULLIF(TRIM(SPLIT_PART(address, ',', -1)), '')"
}
```

### Các trường hợp
- case 1: address=None -> address = address_province = None
- case 2: address="123 Nguyen Ai Quoc, Ho Chi Minh" -> address = "123 Nguyen Ai Quoc, Ho Chi Minh", address_province ="Ho Chi Minh"
- case 3: address="123 Nguyen Ai Quoc" -> address = "123 Nguyen Ai Quoc", address_province=None
- case 4: address="Ho Chi Minh" -> address = "Ho Chi Minh", address_province = None
- case 5: address=",123 Nguyen Ai Quoc, Ho Chi Minh," -> address = "123 Nguyen Ai Quoc, Ho Chi Minh", address_province ="Ho Chi Minh"


## **3. rename_columns**
### Input
- transform_rules: dict. ex: {"from": "id", "to": "customer_id"}
- column_expression: dict.

### Output
- column_expression: dict
```python
column_expression= {
    "customer_id": "id"
}
```

### Các trường hợp
- case: cột id -> customer_id

## **4. filter_columns**
### Input
- transform_rules: dict. ex: {"output": [customer_id, first_name, last_name, birthday, address, address_province, kpi, process_date, source_file]}
- column_expression: dict.

### Output
- column_expression: dict
- Lọc ra những column và expression cuối cùng

## **5. transform_l0_to_l1**
### Overview
- Đây là 1 hàm helper.
- Hàm sẽ đọc table config (customers_config), duyệt qua các luật transform có trong table.yaml, gọi thực hiện các hàm transform tương ứng.
- Tạo 1 sql text tạo view tổng hợp các transform

### Input
- table_config: dict
- schema: str
- view_input: str
- view_output: str
- columns: list (được lấy từ file đang xử lý)
- ex: (customers_config, "retail", "vw_customers", "vw_validation_customers", columns = [....])

### Output
- sql text: str

### Logic
- Tương ứng với các luật transform trong config, các hàm sẽ được gọi thực hiện để tổng hợp column_expression.
- ex: customers cần cast datatype, split_name, split_address, rename_columns, filter_columns.
- B1: Đưa các cột hiện tại vào column_expression
```python
column_expression = {
    "id": "id",
    "name": "name",
    "birthday": "birthday",
    ...
}
```
- B2: Cast datatype cho các cột, đọc config và mapping datatype, đưa expression vào 
```python
CAST_MAPPING = {
    "string": "{column}",
    "integer": "CAST({column} AS INT)",
    "decimal": "CAST({column} AS DECIMAL(38, 4))",
    "date": "TRY_TO_DATE({column}{format})",
    "datetime": "TRY_TO_TIMESTAMP({column})",
    "timestamp": "TRY_TO_TIMESTAMP({column})",
    "boolean": "CAST({column} AS BOOLEAN)",
}
# column expression sẽ trở thành
column_expression = {
    "id": "id",
    "name": "name",
    "birthday": "TRY_TO_DATE(birthday, 'YYYY-MM-dd')",
    ...
}
```
- B3: Duyệt các luật transform còn lại, có được column_expr cuối cùng
```python
column_expression = {
    "customer_id": "id",
    "first_name": "NULLIF(REGEXP_SUBSTR(TRIM(name), '[^[:space:]]+$'), '')",
    "last_name": "NULLIF(TRIM(REGEXP_REPLACE(TRIM(name), '[^[:space:]]+$', '')), '')",
    "birthday": "TRY_TO_DATE(birthday, 'YYYY-MM-dd')",
    "address": "NULLIF(TRIM(REGEXP_REPLACE(address, ',\\\\s*[^,]+$', '')), '')",
    "address_province": "NULLIF(TRIM(SPLIT_PART(address, ',', -1)), '')",
    "kpi": "CAST(kpi AS DECIMAL(38, 4))"
}
```
- Bước 4: Tạo sql text, tạo view transform
```sql
CREATE OR REPLACE VIEW retail.vw_transformation_customers AS
SELECT
    id as customer_id,
    NULLIF(REGEXP_SUBSTR(TRIM(name), '[^[:space:]]+$'), '') as first_name,
    NULLIF(TRIM(REGEXP_REPLACE(TRIM(name), '[^[:space:]]+$', '')), '') as last_name,
    TRY_TO_DATE(birthday, 'YYYY-MM-dd') as birthday,
    NULLIF(TRIM(REGEXP_REPLACE(address, ',\\\\s*[^,]+$', '')), '') as address,
    NULLIF(TRIM(SPLIT_PART(address, ',', -1)), '') as address_province,
    CAST(kpi AS DECIMAL(38, 4)) as kpi
FROM retail.vw_validation_valid_customers
```