"""Data access for deliverables and their dependency graph
(deliverable_dependencies)."""

from _shared.db import execute, query_all, query_one

from schema import SORTABLE

BASE_SELECT = """
    SELECT d.*,
           p.name AS project_name,
           p.code AS project_code,
           u.full_name AS owner_name
      FROM deliverables d
      JOIN projects p ON p.id = d.project_id
      LEFT JOIN users u ON u.id = d.owner_id
"""


def _build_filters(params):
    clauses, values = [], []

    for column in ("project_id", "owner_id", "status"):
        if params.get(column):
            clauses.append(f"d.{column} = %s")
            values.append(params[column])

    if params.get("q"):
        clauses.append("(d.name ILIKE %s OR COALESCE(d.description,'') ILIKE %s)")
        term = f"%{params['q']}%"
        values += [term, term]

    if params.get("due_after"):
        clauses.append("d.due_date >= %s")
        values.append(params["due_after"])

    if params.get("due_before"):
        clauses.append("d.due_date <= %s")
        values.append(params["due_before"])

    if str(params.get("overdue", "")).lower() == "true":
        clauses.append("d.due_date < CURRENT_DATE")
        clauses.append("d.status NOT IN ('COMPLETED','CANCELLED')")

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, values


def _int_param(params, name, default, low, high):
    try:
        return min(max(int(params.get(name, default)), low), high)
    except (TypeError, ValueError):
        return default


def list_deliverables(params):
    where, values = _build_filters(params)

    sort = params.get("sort", "created_at")
    if sort not in SORTABLE:
        sort = "created_at"
    direction = "ASC" if str(params.get("order", "desc")).lower() == "asc" else "DESC"

    limit = _int_param(params, "limit", 50, 1, 200)
    offset = _int_param(params, "offset", 0, 0, 10_000_000)

    total = query_one(f"SELECT COUNT(*) AS count FROM deliverables d{where}", values)
    rows = query_all(
        f"{BASE_SELECT}{where} ORDER BY d.{sort} {direction} LIMIT %s OFFSET %s",
        values + [limit, offset],
    )
    return rows, {"total": total["count"], "limit": limit, "offset": offset}


def get_deliverable(deliverable_id):
    return query_one(f"{BASE_SELECT} WHERE d.id = %s", (deliverable_id,))


def create_deliverable(data):
    columns = list(data)
    placeholders = ", ".join(["%s"] * len(columns))
    return execute(
        f"INSERT INTO deliverables ({', '.join(columns)}) VALUES ({placeholders}) RETURNING id",
        [data[column] for column in columns],
    )


def update_deliverable(deliverable_id, data):
    assignments = ", ".join(f"{column} = %s" for column in data)
    return execute(
        f"UPDATE deliverables SET {assignments}, updated_at = now() WHERE id = %s RETURNING id",
        list(data.values()) + [deliverable_id],
    )


def delete_deliverable(deliverable_id):
    # deliverable_dependencies rows referencing this id cascade at the DB
    # level (ON DELETE CASCADE on both predecessor_id and successor_id), so
    # there's nothing to check or clean up here.
    return execute("DELETE FROM deliverables WHERE id = %s RETURNING id", (deliverable_id,))


# --------------------------------------------------------------------------
# Dependency graph
# --------------------------------------------------------------------------

def list_dependencies(deliverable_id):
    """Every deliverable that must finish before this one (predecessors),
    and every one that depends on this one finishing (successors)."""
    predecessors = query_all(
        """
        SELECT dd.dep_type, d.id, d.name, d.status, d.due_date
          FROM deliverable_dependencies dd
          JOIN deliverables d ON d.id = dd.predecessor_id
         WHERE dd.successor_id = %s
         ORDER BY d.due_date
        """,
        (deliverable_id,),
    )
    successors = query_all(
        """
        SELECT dd.dep_type, d.id, d.name, d.status, d.due_date
          FROM deliverable_dependencies dd
          JOIN deliverables d ON d.id = dd.successor_id
         WHERE dd.predecessor_id = %s
         ORDER BY d.due_date
        """,
        (deliverable_id,),
    )
    return {"predecessors": predecessors, "successors": successors}


def would_create_cycle(predecessor_id, successor_id):
    """True if adding predecessor_id -> successor_id would close a cycle.

    A cycle forms exactly when the proposed successor can already reach the
    proposed predecessor by following existing edges forward — walked with
    the same recursive CTE the critical-path query would use.
    """
    row = query_one(
        """
        WITH RECURSIVE reachable AS (
            SELECT successor_id AS node FROM deliverable_dependencies WHERE predecessor_id = %s
            UNION
            SELECT dd.successor_id
              FROM deliverable_dependencies dd
              JOIN reachable r ON dd.predecessor_id = r.node
        )
        SELECT 1 AS hit FROM reachable WHERE node = %s LIMIT 1
        """,
        (successor_id, predecessor_id),
    )
    return row is not None


def add_dependency(predecessor_id, successor_id, dep_type):
    return execute(
        """
        INSERT INTO deliverable_dependencies (predecessor_id, successor_id, dep_type)
        VALUES (%s, %s, %s)
        ON CONFLICT (predecessor_id, successor_id) DO UPDATE SET dep_type = EXCLUDED.dep_type
        RETURNING predecessor_id
        """,
        (predecessor_id, successor_id, dep_type),
    )


def remove_dependency(predecessor_id, successor_id):
    return execute(
        """
        DELETE FROM deliverable_dependencies
         WHERE predecessor_id = %s AND successor_id = %s
        RETURNING predecessor_id
        """,
        (predecessor_id, successor_id),
    )
