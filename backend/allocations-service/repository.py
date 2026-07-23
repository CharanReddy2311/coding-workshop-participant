"""Data access for allocations.

`period` (a daterange) is never selected directly — pg8000 is a pure-Python
driver with no codec for PostgreSQL range types, so every query projects it
through lower()/upper() into plain start_date/end_date columns, which pg8000
already handles everywhere else in this codebase (see _shared/db.py).
"""

from _shared.db import execute, query_all, query_one

from schema import SORT_EXPRESSIONS, SORTABLE

BASE_SELECT = """
    SELECT a.id, a.user_id, a.project_id, a.role_on_project, a.allocation_pct,
           a.created_at,
           lower(a.period)        AS start_date,
           (upper(a.period) - 1)  AS end_date,
           u.full_name AS user_name,
           u.email     AS user_email,
           p.name      AS project_name,
           p.code      AS project_code
      FROM allocations a
      JOIN users u     ON u.id = a.user_id
      JOIN projects p  ON p.id = a.project_id
"""


def _build_filters(params):
    clauses, values = [], []

    for column in ("user_id", "project_id"):
        if params.get(column):
            clauses.append(f"a.{column} = %s")
            values.append(params[column])

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, values


def _int_param(params, name, default, low, high):
    try:
        return min(max(int(params.get(name, default)), low), high)
    except (TypeError, ValueError):
        return default


def list_allocations(params):
    where, values = _build_filters(params)

    sort = params.get("sort", "created_at")
    if sort not in SORTABLE:
        sort = "created_at"
    sort_expr = SORT_EXPRESSIONS[sort]
    direction = "ASC" if str(params.get("order", "desc")).lower() == "asc" else "DESC"

    limit = _int_param(params, "limit", 50, 1, 200)
    offset = _int_param(params, "offset", 0, 0, 10_000_000)

    total = query_one(f"SELECT COUNT(*) AS count FROM allocations a{where}", values)
    rows = query_all(
        f"{BASE_SELECT}{where} ORDER BY {sort_expr} {direction} LIMIT %s OFFSET %s",
        values + [limit, offset],
    )
    return rows, {"total": total["count"], "limit": limit, "offset": offset}


def get_allocation(allocation_id):
    return query_one(f"{BASE_SELECT} WHERE a.id = %s", (allocation_id,))


def overlapping_pct(user_id, start_date, end_date, exclude_id=None):
    """Sum of allocation_pct already committed for `user_id` on any date
    that overlaps [start_date, end_date] — the exact lookup
    idx_allocations_user_period (a GiST index on (user_id, period)) exists
    to make cheap.
    """
    sql = """
        SELECT COALESCE(SUM(allocation_pct), 0) AS total
          FROM allocations
         WHERE user_id = %s
           AND period && daterange(%s, %s, '[]')
    """
    params = [user_id, start_date, end_date]
    if exclude_id:
        sql += " AND id <> %s"
        params.append(exclude_id)
    return query_one(sql, params)["total"]


def create_allocation(data):
    return execute(
        """
        INSERT INTO allocations (user_id, project_id, role_on_project, allocation_pct, period)
        VALUES (%s, %s, %s, %s, daterange(%s, %s, '[]'))
        RETURNING id
        """,
        (
            data["user_id"],
            data["project_id"],
            data.get("role_on_project"),
            data["allocation_pct"],
            data["start_date"],
            data["end_date"],
        ),
    )


def update_allocation(allocation_id, data, merged):
    """`data` holds only the fields actually submitted, for the plain SET
    columns. `merged` holds the full effective record: period is one column
    derived from two logical fields, so if either start_date or end_date
    changed, both have to be written together.
    """
    assignments, values = [], []

    for column in ("user_id", "project_id", "role_on_project", "allocation_pct"):
        if column in data:
            assignments.append(f"{column} = %s")
            values.append(data[column])

    if "start_date" in data or "end_date" in data:
        assignments.append("period = daterange(%s, %s, '[]')")
        values.append(merged["start_date"])
        values.append(merged["end_date"])

    values.append(allocation_id)
    return execute(
        f"UPDATE allocations SET {', '.join(assignments)} WHERE id = %s RETURNING id",
        values,
    )


def delete_allocation(allocation_id):
    return execute("DELETE FROM allocations WHERE id = %s RETURNING id", (allocation_id,))
