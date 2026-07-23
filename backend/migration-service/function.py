"""migration-service — applies schema.sql and seeds reference data.

There is no Alembic in this scaffold, so schema lives in schema.sql next to
this file and is applied by invoking the service once after each deploy:

    curl -X POST http://localhost:3001/api/migration-service

Keeping the DDL in a .sql file rather than a Python list means it is readable
by anyone reviewing the repo, runnable directly against psql, and diffable in
review. schema.sql ships inside the deployment package because Terraform zips
the whole service folder.

Every statement in schema.sql is idempotent, so rerunning is safe.
"""

import logging
import os
from pathlib import Path

from _shared.auth import hash_password
from _shared.db import cursor, split_statements
from _shared.http import ApiError, response, with_http_errors

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SCHEMA_FILE = Path(__file__).parent / "schema.sql"

SEED_DEPARTMENTS = ("Engineering", "Product", "Operations", "Finance")


def _apply_schema(cur):
    """Execute schema.sql, one statement at a time.

    The driver is pg8000 (see _shared/db.py), a pure-Python driver that sends
    statements over the extended query protocol — one statement per execute.
    Handing it the whole multi-statement file in a single `cur.execute(sql)`
    call fails, so the file is split on statement boundaries first via
    `split_statements` (the same helper `execute_script` uses).

    Every statement runs on the caller's cursor, inside the caller's single
    transaction, so a failure halfway through still rolls the entire migration
    back rather than leaving the database half-built.
    """
    sql = SCHEMA_FILE.read_text(encoding="utf-8")
    statements = split_statements(sql)
    for statement in statements:
        cur.execute(statement)
    return len(statements)


def _seed(cur):
    """Insert reference departments and the bootstrap admin, only if absent."""
    for name in SEED_DEPARTMENTS:
        cur.execute(
            "INSERT INTO departments (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
            (name,),
        )

    cur.execute("SELECT 1 FROM users WHERE role = 'ADMIN' LIMIT 1")
    if cur.fetchone():
        return False

    email = os.getenv("SEED_ADMIN_EMAIL", "admin@acme.example")
    password = os.getenv("SEED_ADMIN_PASSWORD", "ChangeMe!123")
    cur.execute(
        """
        INSERT INTO users (email, full_name, password_hash, role)
        VALUES (%s, %s, %s, 'ADMIN')
        ON CONFLICT (email) DO NOTHING
        """,
        (email, "Platform Administrator", hash_password(password)),
    )
    logger.info("Seeded bootstrap admin %s", email)
    return True


@with_http_errors
def handler(event=None, context=None):
    if not SCHEMA_FILE.exists():
        raise ApiError(f"schema.sql not found at {SCHEMA_FILE}")

    with cursor(commit=True) as cur:
        objects = _apply_schema(cur)
        seeded = _seed(cur)

    logger.info("Migration applied: %s objects", objects)
    return response(200, {
        "objects_applied": objects,
        "departments_seeded": len(SEED_DEPARTMENTS),
        "admin_seeded": seeded,
    })


if __name__ == "__main__":
    print(handler())
