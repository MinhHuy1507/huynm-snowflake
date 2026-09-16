import os
from pathlib import Path

current = Path(__file__).resolve().parent
env_file = None

while current != current.parent:
    potential_path = current / ".env"
    if potential_path.is_file():
        env_file = potential_path
        break
    current = current.parent

if env_file:
    with open(env_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip("'\"")

sf_user = os.getenv("SF_USER")
sf_password = os.getenv("SF_PASSWORD")
sf_account = os.getenv("SF_ACCOUNT")
sf_warehouse = os.getenv("SF_WAREHOUSE")
sf_database = os.getenv("SF_DATABASE")
sf_schema = os.getenv("SF_SCHEMA")

print(f"SF_USER: {sf_user}")
