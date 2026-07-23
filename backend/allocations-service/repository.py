"""Data access for allocations.

`period` (a daterange) is never selected directly — pg8000 is a pure-Python
driver with no codec for PostgreSQL range types, so every query projects it
through lower()/upper() into plain start_date/end_date columns, which pg8000
already handles everywhere else in this codebase (see _shared/db.py).

Capacity (a user is never allocated more than 100% on any single day) is
enforced two ways that work together:

  * `peak_existing_pct` computes the true *maximum concurrent* load with a
    sweep line, not a naive SUM over every overlapping row. Two allocations
    that both overlap the proposed window but not each other are never counted
    together, so a valid allocation is not wrongly rejected.

  * `create_allocation` / `update_allocation` re-run that check inside the same
    transaction as the write, behind a per-user advisory lock, so two
    concurrent requests for the same user cannot both pass the check and then
    both write (the classic check-then-write race). A plain Postgres EXCLUDE
    constraint cannot express "sum <= 100" — it forbids *any* overlap, which
    would reject a legitimate 50%+50% split — so the guarantee is provided by
    serialising per user rather than by a constraint.
"""

from _shared.db import cursor, execute, query_all, query_one
from _shared.http import ConflictError

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


# --------------------------------------------------------------------------
# Capacity
# --------------------------------------------------------------------------

def _peak_query(user_id, start_date, end_date, exclude_id):
    """Build the sweep-line query for a user's peak concurrent load over
    [start_date, end_date], excluding `exclude_id` if given.

    Concurrent load only ever changes at an allocation's start, so the peak
    over the window is found by evaluating the total load at each such boundary
    that falls inside the window (plus the window's own start) and taking the
    maximum. `period` is stored inclusive-inclusive via daterange(..,'[]'),
    which Postgres canonicalises to [lo, hi) — hence `>= lo AND < hi`.
    """
    overlap = "user_id = %s AND period && daterange(%s, %s, '[]')"
    params = [user_id, start_date, end_date]
    if exclude_id:
        overlap += " AND id <> %s"
        params.append(exclude_id)

    sql = f"""
        WITH overlapping AS (
            SELECT lower(period) AS lo, upper(period) AS hi, allocation_pct AS pct
              FROM allocations
             WHERE {overlap}
        ),
        boundaries AS (
            SELECT %s::date AS at
            UNION
            SELECT lo FROM overlapping WHERE lo > %s::date AND lo <= %s::date
        )
        SELECT COALESCE(MAX(load), 0) AS peak
          FROM (
                SELECT b.at, COALESCE(SUM(o.pct), 0) AS load
                  FROM boundaries b
                  LEFT JOIN overlapping o ON b.at >= o.lo AND b.at < o.hi
                 GROUP BY b.at
               ) per_boundary
    """
    params += [start_date, start_date, end_date]
    return sql, params


def peak_existing_pct(user_id, start_date, end_date, exclude_id=None):
    """Maximum concurrent allocation_pct already committed for `user_id` on any
    single day within [start_date, end_date] — the value the proposed
    allocation would stack on top of. Read-only; the authoritative, race-free
    check happens inside the write transaction (see `_assert_within_capacity`).
    """
    sql, params = _peak_query(user_id, start_date, end_date, exclude_id)
    row = query_one(sql, params)
    return row["peak"] if row and row["peak"] is not None else 0


def _assert_within_capacity(cur, user_id, start_date, end_date, allocation_pct, exclude_id):
    """Raise ConflictError if this allocation would push the user's peak
    concurrent load over 100% on any day it covers.

    Runs on the caller's cursor so it shares one transaction with the write
    that follows. The advisory lock serialises concurrent writers for this one
    user, so the check and the write are atomic with respect to each other; the
    lock is released automatically when the transaction ends.
    """
    cur.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (str(user_id),))
    sql, params = _peak_query(user_id, start_date, end_date, exclude_id)
    cur.execute(sql, params)
    row = cur.fetchone()
    peak = row[0] if row and row[0] is not None else 0
    projected = peak + int(allocation_pct)
    if projected > 100:
        raise ConflictError(
            "This allocation would over-allocate the user for the overlapping dates",
            details={
                "existing_pct": peak,
                "requested_pct": int(allocation_pct),
                "projected_pct": projected,
                "max_pct": 100,
            },
        )


def create_allocation(data):
    with cursor(commit=True) as cur:
        _assert_within_capacity(
            cur,
            data["user_id"],
            data["start_date"],
            data["end_date"],
            data["allocation_pct"],
            exclude_id=None,
        )
        cur.execute(
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
        return {"id": cur.fetchone()[0]}


def update_allocation(allocation_id, data, merged):
    """`data` holds only the fields actually submitted, for the plain SET
    columns. `merged` holds the full effective record: period is one column
    derived from two logical fields, so if either start_date or end_date
    changed, both have to be written together. Capacity is re-checked against
    the merged (effective) values, excluding this row's own current allocation.
    """
    with cursor(commit=True) as cur:
        _assert_within_capacity(
            cur,
            merged["user_id"],
            merged["start_date"],
            merged["end_date"],
            merged["allocation_pct"],
            exclude_id=allocation_id,
        )

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
        cur.execute(
            f"UPDATE allocations SET {', '.join(assignments)} WHERE id = %s RETURNING id",
            values,
        )
        row = cur.fetchone()
        return {"id": row[0]} if row else None


def delete_allocation(allocation_id):
    return execute("DELETE FROM allocations WHERE id = %s RETURNING id", (allocation_id,))
