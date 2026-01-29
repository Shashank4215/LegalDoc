"""
Apply the SQL schema file to the configured PostgreSQL database using psycopg2.

This is a psql-free alternative (useful on systems where `psql` isn't installed).
"""

from __future__ import annotations

from pathlib import Path
import sys

from config import CONFIG
from .db_manager_v2 import DatabaseManagerV2


def main() -> int:
    schema_path = Path(__file__).with_name("schema_minimal.sql")
    if not schema_path.exists():
        print(f"ERROR: schema file not found: {schema_path}")
        return 1

    sql = schema_path.read_text(encoding="utf-8")
    if not sql.strip():
        print("ERROR: schema file is empty")
        return 1

    db_cfg = CONFIG["database"]
    with DatabaseManagerV2(**db_cfg) as db:
        with db.connection.cursor() as cursor:
            cursor.execute(sql)
        db.connection.commit()

    print(f"Applied schema: {schema_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


