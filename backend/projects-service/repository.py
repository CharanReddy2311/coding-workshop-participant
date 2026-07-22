"""Data access for projects.

All SQL lives here so the handler stays about HTTP and schema.py stays about
business rules. Every value is bound as a parameter; the only identifiers ever
interpolated are checked against the SORTABLE whitelist first.
"""

from _shared.db import execute, is_unique_violation, query_all, query_one
from _shared.http import ConflictError

from schema import SORTABLE

# Joined so a list view can show manager and department names, plus deliverable
# progress, without the frontend making N follow-up requests.
BASE_SELECT = """
    SELECT p.*,
           u.full_name AS manager_name,
           d.name      AS department_name,
           COALESCE(dl.total, 0)     AS deliverable_count,
           COALESCE(dl.completed, 0) AS deliverables_completed
      FROM projects p
      JOIN users u       ON u.id = p.manager_id
      JOIN departments d ON d.id = p.department_id
      LEFT JOIN (
            SELECT project_id,
                   COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE status = 'COMPLETED') AS completed
              FROM deliverables
             GROUP BY project_id
      ) dl ON dl.project_id = p.id
"""


def _build_filters(params):
    """Translate query string parameters into a WHERE clause."""
    clauses, values = [], []

    for column in ("status", "priority", "department_id", "manager_id"):
        if params.get(column):
            clauses.append(f"p.{column} = %s")
            values.append(params[column])

    if params.get("q"):
        clauses.append(
            "(p.name ILIKE %s OR p.code ILIKE %s OR COALESCE(p.description,'') ILIKE %s)"
        )
        term = f"%{params['q']}%"
        values += [term, term, term]

    if params.get("start_after"):
        clauses.append("p.start_date >= %s")
        values.append(params["start_after"])

    if params.get("end_before"):
        clauses.append("p.planned_end <= %s")
        values.append(params["end_before"])

    if str(params.get("overdue", "")).lower() == "true":
        clauses.append("p.planned_end < CURRENT_DATE")
        clauses.append("p.status NOT IN ('COMPLETED','CANCELLED')")

    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, values


def _int_param(params, name, default, low, high):
    try:
        return min(max(int(params.get(name, default)), low), high)
    except (TypeError, ValueError):
        return default


def list_projects(params):
    where, values = _build_filters(params)

    sort = params.get("sort", "created_at")
    if sort not in SORTABLE:
        sort = "created_at"
    direction = "ASC" if str(params.get("order", "desc")).lower() == "asc" else "DESC"

    limit = _int_param(params, "limit", 50, 1, 200)
    offset = _int_param(params, "offset", 0, 0, 10_000_000)

    total = query_one(f"SELECT COUNT(*) AS count FROM projects p{where}", values)
    rows = query_all(
        f"{BASE_SELECT}{where} ORDER BY p.{sort} {direction} LIMIT %s OFFSET %s",
        values + [limit, offset],
    )
    return rows, {"total": total["count"], "limit": limit, "offset": offset}


def get_project(project_id):
    return query_one(f"{BASE_SELECT} WHERE p.id = %s", (project_id,))


def code_taken(code, exclude_id=None):
    if exclude_id:
        row = query_one(
            "SELECT 1 FROM projects WHERE lower(code) = lower(%s) AND id <> %s",
            (code, exclude_id),
        )
    else:
        row = query_one("SELECT 1 FROM projects WHERE lower(code) = lower(%s)", (code,))
    return row is not None


def create_project(data):
    columns = list(data)
    placeholders = ", ".join(["%s"] * len(columns))
    try:
        return execute(
            f"INSERT INTO projects ({', '.join(columns)}) "
            f"VALUES ({placeholders}) RETURNING id",
            [data[column] for column in columns],
        )
    except Exception as exc:  # noqa: BLE001
        if is_unique_violation(exc):
            raise ConflictError("A project with this code already exists")
        raise


def update_project(project_id, data):
    assignments = ", ".join(f"{column} = %s" for column in data)
    try:
        return execute(
            f"UPDATE projects SET {assignments}, updated_at = now() "
            f"WHERE id = %s RETURNING id",
            list(data.values()) + [project_id],
        )
    except Exception as exc:  # noqa: BLE001
        if is_unique_violation(exc):
            raise ConflictError("A project with this code already exists")
        raise


def delete_project(project_id):
    """Refuse to delete a project that still has linked records.

    Cascading them away silently would destroy the deliverable and allocation
    history a project manager needs — the opposite of the visibility this
    platform exists to provide.
    """
    blockers = query_one(
        """
        SELECT (SELECT COUNT(*) FROM deliverables WHERE project_id = %s) AS deliverables,
               (SELECT COUNT(*) FROM allocations  WHERE project_id = %s) AS allocations
        """,
        (project_id, project_id),
    )
    if blockers["deliverables"] or blockers["allocations"]:
        raise ConflictError(
            "Project still has linked records and cannot be deleted",
            details={
                "deliverables": blockers["deliverables"],
                "allocations": blockers["allocations"],
                "hint": "Set status to CANCELLED, or remove the linked records first",
            },
        )
    return execute("DELETE FROM projects WHERE id = %s RETURNING id", (project_id,))
