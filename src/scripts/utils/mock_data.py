import argparse
import bz2
import csv
import gzip
import json
import lzma
import random
from io import StringIO
from faker import Faker
from datetime import datetime, timedelta
import time

from scripts.utils.s3_helper import s3
from scripts.utils.constants import AWSConfigs

DELIMITERS = {
    "csv": ",",
    "tsv": "\t",
    "psv": "|",
    "scsv": ";",
}

COMPRESSION_EXTENSIONS = {
    "gzip": "gz",
    "bzip2": "bz2",
    "xz": "xz",
    "lzma": "lzma",
}


def _serialize_rows(file_format, headers, rows):
    if file_format in DELIMITERS:
        output = StringIO(newline="")
        writer = csv.writer(output, delimiter=DELIMITERS[file_format])
        writer.writerow(headers)
        writer.writerows(rows)
        return output.getvalue().encode("utf-8"), "text/csv"

    records = [dict(zip(headers, row)) for row in rows]
    if file_format == "json":
        content = json.dumps(records, ensure_ascii=False)
    elif file_format == "jsonl":
        content = "\n".join(
            json.dumps(record, ensure_ascii=False) for record in records
        )
    else:
        raise ValueError(f"Unsupported file format: {file_format}")
    return content.encode("utf-8"), "application/json"


def _compress(data, compression):
    if compression is None:
        return data
    if compression == "gzip":
        return gzip.compress(data)
    if compression == "bzip2":
        return bz2.compress(data)
    if compression in {"xz", "lzma"}:
        return lzma.compress(data)
    raise ValueError(f"Unsupported compression: {compression}")


def upload_data(bucket, key, headers, rows, file_format="csv", compression=None):
    data, content_type = _serialize_rows(file_format, headers, rows)
    data = _compress(data, compression)
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=data,
        ContentType=content_type,
        **({"ContentEncoding": "gzip"} if compression == "gzip" else {}),
    )


def upload_csv(bucket, key, headers, rows):
    """Backward-compatible CSV upload helper."""
    upload_data(bucket, key, headers, rows)


def generate_mock_data(
    bucket,
    schema,
    process_date,
    record_count=100_000,
    file_format="csv",
    compression=None,
):
    if file_format not in (*DELIMITERS, "json", "jsonl"):
        raise ValueError(f"Unsupported file format: {file_format}")
    if compression not in (None, *COMPRESSION_EXTENSIONS):
        raise ValueError(f"Unsupported compression: {compression}")

    start = time.perf_counter()
    fake = Faker("vi_VN")

    def s3_key(table):
        extension = file_format
        if compression:
            extension = f"{extension}.{COMPRESSION_EXTENSIONS[compression]}"
        return f"rcv/{schema}/{table}/{process_date}/{table}.{extension}"

    def upload(table, headers, rows):
        upload_data(
            bucket,
            s3_key(table),
            headers,
            rows,
            file_format=file_format,
            compression=compression,
        )

    orders_count = record_count
    customer_count = max(1000, int(orders_count**0.55))
    product_count = int(customer_count * 1.5)

    # Provinces in Vietnam
    PROVINCES = [
        "Ha Noi",
        "Hai Phong",
        "Quang Ninh",
        "Lang Son",
        "Cao Bang",
        "Tuyen Quang",
        "Lao Cai",
        "Thai Nguyen",
        "Phu Tho",
        "Bac Ninh",
        "Hung Yen",
        "Ninh Binh",
        "Thanh Hoa",
        "Nghe An",
        "Ha Tinh",
        "Quang Tri",
        "Hue",
        "Da Nang",
        "Quang Ngai",
        "Gia Lai",
        "Dak Lak",
        "Khanh Hoa",
        "Lam Dong",
        "Dong Nai",
        "Tay Ninh",
        "Ho Chi Minh",
        "Dong Thap",
        "An Giang",
        "Vinh Long",
        "Can Tho",
        "Ca Mau",
        "Kien Giang",
        "Son La",
        "Dien Bien",
    ]

    print("Creating Province data")
    province_rows = [[f"PROV_{i}", name] for i, name in enumerate(PROVINCES, 1)]
    upload("province", ["id", "name"], province_rows)

    print(f"Province: {time.perf_counter() - start:.3f}s")

    # Products
    start = time.perf_counter()
    print("Creating Products data...")
    POOL_SIZE = 1000
    product_name_pool = [fake.catch_phrase() for _ in range(POOL_SIZE)]
    product_prices = {}
    product_ids = []

    product_rows = []
    for i in range(1, product_count + 1):
        product_id = f"PROD_{i}"
        price = round(random.uniform(10.0, 5000.0), 2)

        product_ids.append(product_id)
        product_prices[product_id] = price
        product_rows.append(
            [product_id, f"{random.choice(product_name_pool)}_{i}", price]
        )
    upload("products", ["id", "name", "unit_price"], product_rows)

    print(f"Products: {time.perf_counter() - start:.3f}s")

    # Customers
    start = time.perf_counter()
    print(f"Creating data for {customer_count} Customers...")
    NAME_POOL_SIZE = 2000
    STREET_POOL_SIZE = 2000

    last_name_pool = [fake.last_name() for _ in range(300)]
    middle_name_pool = [fake.middle_name() for _ in range(1000)]
    first_name_pool = [fake.first_name() for _ in range(NAME_POOL_SIZE)]
    street_pool = [fake.street_name() for _ in range(STREET_POOL_SIZE)]
    customer_ids = []

    start_birth = datetime(1945, 1, 1)
    end_birth = datetime(2008, 12, 31)
    birth_range_days = (end_birth - start_birth).days

    customer_rows = []
    for i in range(1, customer_count + 1):
        is_error = random.random() < 0.1
        cust_id = f"CUST_{i}"
        customer_ids.append(cust_id)

        name = (
            ""
            if is_error
            else (
                f"{random.choice(last_name_pool)} {random.choice(middle_name_pool)} "
                f"{random.choice(first_name_pool)}"
            )
        )
        birthday_dt = start_birth + timedelta(days=random.randint(0, birth_range_days))
        birthday = birthday_dt.strftime(
            "%d-%m-%Y" if is_error and random.choice([True, False]) else "%Y-%m-%d"
        )
        address = f"{random.choice(street_pool)}, {random.choice(PROVINCES)}"
        kpi = (
            round(random.uniform(101, 200), 2)
            if is_error
            else round(random.uniform(0, 100), 2)
        )
        customer_rows.append([cust_id, name, birthday, address, kpi])
    upload(
        "customers",
        ["id", "name", "birthday", "address", "kpi"],
        customer_rows,
    )

    print(f"Customers: {time.perf_counter() - start:.3f}s")

    # Orders
    start = time.perf_counter()
    print(f"Creating {orders_count:,} Orders...")
    base_ts = int(datetime.now().timestamp())

    date_pool = [
        datetime.fromtimestamp(base_ts - random.randint(0, 100)).strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        for _ in range(1_000)
    ]

    order_rows = []
    for i in range(1, orders_count + 1):
        is_error = random.random() < 0.1
        customer_id = (
            ""
            if is_error and random.choice([True, False])
            else random.choice(customer_ids)
        )
        product_id = random.choice(product_ids)
        quantity = random.randint(-5, 0) if is_error else random.randint(1, 10)
        order_rows.append(
            [
                f"ORD_{i}",
                customer_id,
                product_id,
                quantity,
                product_prices[product_id],
                random.choice(date_pool),
            ]
        )
        if i % 100_000 == 0:
            print(f"  -> Created {i:,} Order rows.")
    upload(
        "orders",
        ["id", "customer_id", "product_id", "quantity", "price", "order_date"],
        order_rows,
    )
    print(f"Orders: {time.perf_counter() - start:.3f}s")

    print(f"\n=> COMPLETED! Created data for {record_count:,} records!")


def parse_args():
    parser = argparse.ArgumentParser(description="Generate mock retail data in S3")
    parser.add_argument(
        "--bucket",
        default=AWSConfigs.DEFAULT_BUCKET,
        help="S3 bucket name",
    )
    parser.add_argument("--schema", default="retail", help="Schema name")
    parser.add_argument(
        "--process-date",
        default=datetime.now().strftime("%Y/%m/%d"),
        help="Date partition in YYYY/MM/DD format",
    )
    parser.add_argument(
        "--record-count",
        type=int,
        default=100_000,
        help="Number of order records to generate",
    )
    parser.add_argument(
        "--format",
        dest="file_format",
        choices=(*DELIMITERS, "json", "jsonl"),
        default="csv",
        help="Output format (default: csv)",
    )
    parser.add_argument(
        "--compression",
        choices=tuple(COMPRESSION_EXTENSIONS),
        default=None,
        help="Compression method (default: none)",
    )
    return parser.parse_args()


# Test
if __name__ == "__main__":
    args = parse_args()
    generate_mock_data(
        bucket=args.bucket,
        schema=args.schema,
        process_date=args.process_date,
        record_count=args.record_count,
        file_format=args.file_format,
        compression=args.compression,
    )
