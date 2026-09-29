# **Mock Project**
Xây dựng batch data pipeline xử lý dữ liệu bán hàng theo ngày.

## Yêu cầu
- Chuẩn bị file customer.csv gồm:
```
id,name,birthday,address,kpi
```

- Đọc CSV và xuất Parquet gồm:
```
id,first_name,last_name,birthday,address,address_province,kpi
```

- birthday phải là kiểu date.
- kpi phải là kiểu decimal.
- Tách name thành first_name, last_name.
- Tách tỉnh/thành phố từ address.
## Data layer
```
RCV/{schema_name}/{table_name}/yyyy/mm/dd/{table_name}.csv
L0/{schema_name}/{table_name}/yyyy/mm/dd/{table_name}.csv
L1/{schema_name}/{table_name}/yyyy/mm/dd/{table_name}.parquet
```
- Tự thiết kế thêm 3–4 bảng, gồm cả master data và transaction data, ví dụ:

- Province
- City
- Product
- Transaction

## Database load
Phải triển khai đủ ba cơ chế:

- Upsert
- Insert-only
- Replace all bằng truncate-insert

Tự lựa chọn cơ chế phù hợp cho từng bảng.

## Technical requirements
- Sử dụng Python.
- Sử dụng Apache Airflow để orchestration.
- Có validation và xử lý dữ liệu lỗi.
- Có logging và audit số lượng record.
- Pipeline chạy theo process_date.
- Có thể retry và chạy lại an toàn.
- Không hard-code path, schema, table, column, data type, load strategy hoặc database connection.
- Các thông tin cấu hình phải được quản lý bằng YAML, JSON, environment variable, Airflow Variable hoặc Airflow Connection.

## Deliverables
- Source code
- Airflow DAG
- Config
- Sample input
- Parquet output
- Database DDL
- Unit test
- README
- Sơ đồ data flow và kiến trúc đề xuất
