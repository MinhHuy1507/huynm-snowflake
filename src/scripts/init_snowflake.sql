USE ROLE ACCOUNTADMIN;

CREATE DATABASE IF NOT EXISTS huynm43_mp;

CREATE SCHEMA IF NOT EXISTS huynm43_mp.retail;

USE DATABASE huynm43_mp;

USE SCHEMA retail;

-- Create storage integration
CREATE OR REPLACE STORAGE INTEGRATION huynm43_mp_snowflake_s3
TYPE = EXTERNAL_STAGE
STORAGE_PROVIDER = 'S3'
ENABLED = TRUE
STORAGE_AWS_ROLE_ARN = 'arn:aws:iam::414061810527:role/huynm43-mp-snowflake-role'
STORAGE_ALLOWED_LOCATIONS = (
    's3://huynm43-mock-project-s3-414061810527-us-east-1-an/l0/',
    's3://huynm43-mock-project-s3-414061810527-us-east-1-an/l1/',
    's3://huynm43-mock-project-s3-414061810527-us-east-1-an/audit/'
);

DESC INTEGRATION huynm43_mp_snowflake_s3;

-- Create file format
CREATE OR REPLACE FILE FORMAT csv_ff
TYPE = CSV
SKIP_HEADER = 1
FIELD_OPTIONALLY_ENCLOSED_BY='"';

CREATE OR REPLACE FILE FORMAT parquet_ff
TYPE = PARQUET;