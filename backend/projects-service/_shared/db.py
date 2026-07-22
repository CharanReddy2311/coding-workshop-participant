"""PostgreSQL access shared by every Lambda service.

Uses pg8000, a pure-Python PostgreSQL driver, rather than psycopg.

The reason is packaging. infra/lambda.tf sets build_in_docker = false, so
Terraform builds each deployment package with whatever `pip` is on the host
PATH. psycopg[binary] ships a compiled extension tagged to a specific Python
version, so if the host pip belongs to a different interpreter than the Lambda
runtime (python3.13, per infra/locals.tf) the package installs cleanly and then
fails at import with "no pq wrapper available". pg8000 has no compiled code, so
it is immune to that entire class of problem.

pg8000 uses paramstyle "format", so %s placeholders work exactly as before.

The connection is created lazily at module scope so a warm Lambda container
reuses it. There is no RDS Proxy in this stack, so opening a connection per
invocation is a real failure mode once concurrency rises.
"""

import logging
import os
import ssl
from contextlib import contextmanager

import pg8000.dbapi

from .http import ApiError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

_connection = None

# `table` is interpolated into SQL in exists(), so it is whitelisted rather
# than parameterised.
_REFERENCEABLE_TABLES = {
    "users",
    "departments",
    "teams",
    "projects",
    "deliverables",
    "allocations",
    "budget_items",
    "expenses",
}

# SQLSTATE codes worth distinguishing from a generic failure.
UNIQUE_VIOLATION = "23505"
FOREIGN_KEY_VIOLATION = "23503"
CHECK_VIOLATION = "23514"


def is_local() -> bool:
    return os.getenv("IS_LOCAL", "false").strip().lower() == "true"


def _connect_kwargs() -> dict:
    """Build connection parameters from the injected environment variables.

    Local PostgreSQL runs without TLS; Aurora requires it. Getting this branch
    wrong is the classic "works locally, 500s in the cloud" failure.
    """
    kwargs = {
        "host": os.getenv("POSTGRES_HOST", "localhost"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "user": os.getenv("POSTGRES_USER", "test"),
        "password": os.getenv("POSTGRES_PASS", "test"),
        "database": os.getenv("POSTGRES_NAME", "test"),
        "timeout": 15,
    }

    if not is_local():
        # Encrypt without verifying the server certificate, which is what
        # libpq's sslmode=require does. Aurora's CA is not in the Lambda trust
        # store, so full verification would need the RDS bundle shipped in the
        # package. Encryption in transit is the requirement here.
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
        kwargs["ssl_context"] = context

    return kwargs


def _connection_is_healthy(connection) -> bool:
    """Verify the cached connection is still usable before reusing it."""
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cached PostgreSQL connection failed health check: %s", exc)
        return False


def get_connection():
    """Return a live connection, reconnecting if the cached one has died."""
    global _connection
    if _connection is not None:
        if _connection_is_healthy(_connection):
            return _connection
        logger.warning("Reconnecting PostgreSQL after health-check failure (local=%s)", is_local())
        reset_connection()

    try:
        _connection = pg8000.dbapi.connect(**_connect_kwargs())
        _connection.autocommit = False
        logger.info("Opened PostgreSQL connection (local=%s)", is_local())
    except Exception as exc:  # noqa: BLE001
        _connection = None
        logger.error("Database connection failed: %s", exc)
        raise ApiError("Database is unavailable", code="database_unavailable")
    return _connection


def reset_connection():
    """Drop the cached connection so the next call reconnects."""
    global _connection
    try:
        if _connection is not None:
            _connection.close()
    except Exception:  # noqa: BLE001
        pass
    _connection = None


@contextmanager
def cursor(commit=False):
    """Yield a cursor, committing or rolling back on exit.

    A dead connection is discarded rather than cached, so the next invocation
    of a warm container reconnects instead of failing repeatedly.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        yield cur
        if commit:
            conn.commit()
        else:
            conn.rollback()
    except Exception:
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001
            reset_connection()
        raise
    finally:
        try:
            cur.close()
        except Exception:  # noqa: BLE001
            pass


def _to_dicts(cur):
    """pg8000 returns tuples, so map them onto column names."""
    if cur.description is None:
        return []
    columns = [
        col[0].decode() if isinstance(col[0], bytes) else col[0]
        for col in cur.description
    ]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def _to_dict(cur):
    rows = _to_dicts(cur)
    return rows[0] if rows else None


def query_all(sql, params=None):
    with cursor() as cur:
        cur.execute(sql, params or ())
        return _to_dicts(cur)


def query_one(sql, params=None):
    with cursor() as cur:
        cur.execute(sql, params or ())
        return _to_dict(cur)


def execute(sql, params=None, returning=True):
    """Run a write statement. Returns the RETURNING row when there is one."""
    with cursor(commit=True) as cur:
        cur.execute(sql, params or ())
        if returning and cur.description is not None:
            return _to_dict(cur)
        return cur.rowcount


def split_statements(sql):
    """Split a .sql file into individual statements.

    pg8000 sends one statement per execute, unlike libpq's simple query
    protocol, so a multi-statement file has to be split before it is applied.
    Line and trailing comments are stripped first so a `--` never swallows a
    following statement.
    """
    cleaned = []
    for line in sql.splitlines():
        if "--" in line:
            line = line.split("--", 1)[0]
        if line.strip():
            cleaned.append(line)
    joined = "\n".join(cleaned)
    return [stmt.strip() for stmt in joined.split(";") if stmt.strip()]


def execute_script(sql):
    """Apply a multi-statement script inside a single transaction.

    One transaction means a failure halfway through rolls the whole script
    back rather than leaving the database half-built.
    """
    statements = split_statements(sql)
    with cursor(commit=True) as cur:
        for statement in statements:
            cur.execute(statement)
    return len(statements)


def sqlstate(exc):
    """Extract the SQLSTATE code from a pg8000 error, or None."""
    for arg in getattr(exc, "args", ()):
        if isinstance(arg, dict):
            return arg.get("C")
    return None


def is_unique_violation(exc):
    return sqlstate(exc) == UNIQUE_VIOLATION


def exists(table, record_id):
    """Foreign-key existence check, run before accepting a reference."""
    if table not in _REFERENCEABLE_TABLES:
        raise ValueError(f"Refusing to build a query for unknown table {table!r}")
    return query_one(f"SELECT 1 AS ok FROM {table} WHERE id = %s", (record_id,)) is not None
