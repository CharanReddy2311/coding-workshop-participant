"""Data access for users.

Password hashes are never selected into an API payload. Every read lists the
public columns explicitly (see PUBLIC_COLUMNS) so a hash can only ever be read
by the one query that needs it — and there isn't one here; verification lives
in auth-service. This service only ever *writes* a hash the handler computed.
"""

from _shared.db import execute, is_unique_violation, query_all, query_one
from _shared.http import ConflictError

from schema import SORTABLE

# Deliberately excludes password_hash. Joined to departments so the list view
# can show a department name without an extra round trip per row.
PUBLIC_COLUMNS = """
    u.id, u.email, u.full_name, u.role, u.is_active,
    u.department_id, d.name AS department_name,
    u.last_login_at, u.created_at
"""

BASE_SELECT = f"""
    SELECT {PUBLIC_COLUMNS}
      FROM users u
      LEFT JOIN departments d ON d.id = u.department_id
"""


def _build_filters(params):
    clauses, values = [], []

    for column in ("role", "department_id"):
        if params.get(column):
            clauses.append(f"u.{column} = %s")
            values.append(params[column])

    if params.get("q"):
        clauses.append("(u.full_name ILIKE %s OR u.email ILIKE %s)")
        term = f"%{params['q']}%"
        values += [term, term]

    if params.get("is_active") is not None:
        clauses.append("u.is_active = %s")
        values.append(str(params["is_active"]).lower() == "true")

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, values


def _int_param(params, name, default, low, high):
    try:
        return min(max(int(params.get(name, default)), low), high)
    except (TypeError, ValueError):
        return default


def list_users(params):
    where, values = _build_filters(params)

    sort = params.get("sort", "created_at")
    if sort not in SORTABLE:
        sort = "created_at"
    direction = "ASC" if str(params.get("order", "desc")).lower() == "asc" else "DESC"

    limit = _int_param(params, "limit", 50, 1, 200)
    offset = _int_param(params, "offset", 0, 0, 10_000_000)

    total = query_one(f"SELECT COUNT(*) AS count FROM users u{where}", values)
    rows = query_all(
        f"{BASE_SELECT}{where} ORDER BY u.{sort} {direction} LIMIT %s OFFSET %s",
        values + [limit, offset],
    )
    return rows, {"total": total["count"], "limit": limit, "offset": offset}


def get_user(user_id):
    return query_one(f"{BASE_SELECT} WHERE u.id = %s", (user_id,))


def email_taken(email, exclude_id=None):
    if exclude_id:
        row = query_one(
            "SELECT 1 FROM users WHERE lower(email) = lower(%s) AND id <> %s",
            (email, exclude_id),
        )
    else:
        row = query_one("SELECT 1 FROM users WHERE lower(email) = lower(%s)", (email,))
    return row is not None


def other_active_admins(exclude_id):
    """Count ACTIVE admins other than `exclude_id`.

    Used to refuse the last-admin lockout: demoting, deactivating, or deleting
    the only remaining active administrator would leave nobody able to manage
    users and roles.
    """
    row = query_one(
        """
        SELECT COUNT(*) AS count
          FROM users
         WHERE role = 'ADMIN' AND is_active = true AND id <> %s
        """,
        (exclude_id,),
    )
    return row["count"]


def managed_reference_counts(user_id):
    """Teams and projects this user manages (both are ON DELETE RESTRICT)."""
    return query_one(
        """
        SELECT (SELECT COUNT(*) FROM teams    WHERE manager_id = %s) AS teams,
               (SELECT COUNT(*) FROM projects WHERE manager_id = %s) AS projects
        """,
        (user_id, user_id),
    )


def create_user(data):
    columns = list(data)
    placeholders = ", ".join(["%s"] * len(columns))
    try:
        created = execute(
            f"INSERT INTO users ({', '.join(columns)}) "
            f"VALUES ({placeholders}) RETURNING id",
            [data[column] for column in columns],
        )
    except Exception as exc:  # noqa: BLE001
        if is_unique_violation(exc):
            raise ConflictError("A user with this email already exists")
        raise
    # Re-read through the public projection so password_hash never comes back.
    return get_user(created["id"])


def update_user(user_id, data):
    assignments = ", ".join(f"{column} = %s" for column in data)
    try:
        execute(
            f"UPDATE users SET {assignments} WHERE id = %s RETURNING id",
            list(data.values()) + [user_id],
        )
    except Exception as exc:  # noqa: BLE001
        if is_unique_violation(exc):
            raise ConflictError("A user with this email already exists")
        raise
    return get_user(user_id)


def delete_user(user_id):
    return execute("DELETE FROM users WHERE id = %s RETURNING id", (user_id,))
