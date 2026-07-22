"""Data access for teams.

All SQL lives in this module so the handler stays focused on request
translation and shared HTTP error handling.
"""

from _shared.db import execute, is_unique_violation, query_all, query_one
from _shared.http import ConflictError

from schema import SORTABLE

BASE_SELECT = """
    SELECT t.*,
           d.name AS department_name,
           u.full_name AS manager_name
      FROM teams t
      JOIN departments d ON d.id = t.department_id
      JOIN users u ON u.id = t.manager_id
"""


def _build_filters(params):
    """Translate query string parameters into a WHERE clause."""
    clauses, values = [], []

    for column in ("department_id", "manager_id"):
        if params.get(column):
            clauses.append(f"t.{column} = %s")
            values.append(params[column])

    if params.get("q"):
        clauses.append("(t.name ILIKE %s OR COALESCE(t.description,'') ILIKE %s)")
        term = f"%{params['q']}%"
        values += [term, term]

    if params.get("is_active") is not None:
        clauses.append("t.is_active = %s")
        values.append(str(params["is_active"]).lower() == "true")

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, values


def _int_param(params, name, default, low, high):
    try:
        return min(max(int(params.get(name, default)), low), high)
    except (TypeError, ValueError):
        return default


def list_teams(params):
    where, values = _build_filters(params)

    sort = params.get("sort", "created_at")
    if sort not in SORTABLE:
        sort = "created_at"
    direction = "ASC" if str(params.get("order", "desc")).lower() == "asc" else "DESC"

    limit = _int_param(params, "limit", 50, 1, 200)
    offset = _int_param(params, "offset", 0, 0, 10_000_000)

    total = query_one(f"SELECT COUNT(*) AS count FROM teams t{where}", values)
    rows = query_all(
        f"{BASE_SELECT}{where} ORDER BY t.{sort} {direction} LIMIT %s OFFSET %s",
        values + [limit, offset],
    )
    return rows, {"total": total["count"], "limit": limit, "offset": offset}


def get_team(team_id):
    return query_one(f"{BASE_SELECT} WHERE t.id = %s", (team_id,))


def name_taken(name, exclude_id=None):
    if exclude_id:
        row = query_one(
            "SELECT 1 FROM teams WHERE lower(name) = lower(%s) AND id <> %s",
            (name, exclude_id),
        )
    else:
        row = query_one("SELECT 1 FROM teams WHERE lower(name) = lower(%s)", (name,))
    return row is not None


def create_team(data):
    columns = list(data)
    placeholders = ", ".join(["%s"] * len(columns))
    try:
        return execute(
            f"INSERT INTO teams ({', '.join(columns)}) VALUES ({placeholders}) RETURNING id",
            [data[column] for column in columns],
        )
    except Exception as exc:  # noqa: BLE001
        if is_unique_violation(exc):
            raise ConflictError("A team with this name already exists")
        raise


def update_team(team_id, data):
    assignments = ", ".join(f"{column} = %s" for column in data)
    try:
        return execute(
            f"UPDATE teams SET {assignments}, updated_at = now() WHERE id = %s RETURNING id",
            list(data.values()) + [team_id],
        )
    except Exception as exc:  # noqa: BLE001
        if is_unique_violation(exc):
            raise ConflictError("A team with this name already exists")
        raise


def delete_team(team_id):
    return execute("DELETE FROM teams WHERE id = %s RETURNING id", (team_id,))
