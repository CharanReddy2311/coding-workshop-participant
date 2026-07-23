"""Data access for budget items and expenses.

Planned amounts (budget_items) and actual spend (expenses) are separate tables
so "consumed vs planned" is a rollup rather than two numbers kept in sync by
hand. `budget_summary` is that rollup, per project.
"""

from _shared.db import execute, is_unique_violation, query_all, query_one
from _shared.http import ConflictError

from schema import EXPENSE_SORTABLE, ITEM_SORTABLE


# --------------------------------------------------------------------------
# Summary — the headline "consumed vs planned per project" question
# --------------------------------------------------------------------------

def budget_summary():
    """One row per project: its top-line planned budget, the sum of its
    itemised planned amounts, and the actual amount consumed (expenses).

    Every project is returned, including those with no budget items yet, so the
    dashboard can show a complete portfolio rather than only projects that
    happen to have spend recorded.
    """
    return query_all(
        """
        SELECT p.id            AS project_id,
               p.code          AS project_code,
               p.name          AS project_name,
               p.status        AS project_status,
               p.planned_budget,
               COALESCE(bi.planned_itemized, 0) AS planned_itemized,
               COALESCE(bi.consumed, 0)         AS consumed
          FROM projects p
          LEFT JOIN (
                SELECT bi.project_id,
                       SUM(bi.planned_amount)          AS planned_itemized,
                       COALESCE(SUM(ex.consumed), 0)   AS consumed
                  FROM budget_items bi
                  LEFT JOIN (
                        SELECT budget_item_id, SUM(amount) AS consumed
                          FROM expenses
                         GROUP BY budget_item_id
                  ) ex ON ex.budget_item_id = bi.id
                 GROUP BY bi.project_id
          ) bi ON bi.project_id = p.id
         ORDER BY p.code
        """
    )


# --------------------------------------------------------------------------
# Budget items
# --------------------------------------------------------------------------

ITEM_SELECT = """
    SELECT bi.id, bi.project_id, bi.category, bi.planned_amount, bi.created_at,
           p.code AS project_code, p.name AS project_name,
           COALESCE((SELECT SUM(amount) FROM expenses WHERE budget_item_id = bi.id), 0) AS consumed
      FROM budget_items bi
      JOIN projects p ON p.id = bi.project_id
"""


def list_items(params):
    clauses, values = [], []
    if params.get("project_id"):
        clauses.append("bi.project_id = %s")
        values.append(params["project_id"])
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

    sort = params.get("sort", "created_at")
    if sort not in ITEM_SORTABLE:
        sort = "created_at"
    direction = "ASC" if str(params.get("order", "desc")).lower() == "asc" else "DESC"

    return query_all(f"{ITEM_SELECT}{where} ORDER BY bi.{sort} {direction}", values)


def get_item(item_id):
    return query_one(f"{ITEM_SELECT} WHERE bi.id = %s", (item_id,))


def create_item(data):
    try:
        return execute(
            """
            INSERT INTO budget_items (project_id, category, planned_amount)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (data["project_id"], data["category"], data["planned_amount"]),
        )
    except Exception as exc:  # noqa: BLE001
        if is_unique_violation(exc):
            raise ConflictError("A budget item for this category already exists on the project")
        raise


def update_item(item_id, data):
    assignments = ", ".join(f"{column} = %s" for column in data)
    try:
        return execute(
            f"UPDATE budget_items SET {assignments} WHERE id = %s RETURNING id",
            list(data.values()) + [item_id],
        )
    except Exception as exc:  # noqa: BLE001
        if is_unique_violation(exc):
            raise ConflictError("A budget item for this category already exists on the project")
        raise


def delete_item(item_id):
    # expenses referencing this item cascade at the DB level (ON DELETE CASCADE).
    return execute("DELETE FROM budget_items WHERE id = %s RETURNING id", (item_id,))


# --------------------------------------------------------------------------
# Expenses
# --------------------------------------------------------------------------

EXPENSE_SELECT = """
    SELECT ex.id, ex.budget_item_id, ex.description, ex.amount, ex.incurred_on, ex.created_at,
           bi.category, bi.project_id,
           p.code AS project_code
      FROM expenses ex
      JOIN budget_items bi ON bi.id = ex.budget_item_id
      JOIN projects p ON p.id = bi.project_id
"""


def list_expenses(params):
    clauses, values = [], []
    if params.get("budget_item_id"):
        clauses.append("ex.budget_item_id = %s")
        values.append(params["budget_item_id"])
    if params.get("project_id"):
        clauses.append("bi.project_id = %s")
        values.append(params["project_id"])
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

    sort = params.get("sort", "incurred_on")
    if sort not in EXPENSE_SORTABLE:
        sort = "incurred_on"
    direction = "ASC" if str(params.get("order", "desc")).lower() == "asc" else "DESC"

    return query_all(f"{EXPENSE_SELECT}{where} ORDER BY ex.{sort} {direction}", values)


def get_expense(expense_id):
    return query_one(f"{EXPENSE_SELECT} WHERE ex.id = %s", (expense_id,))


def create_expense(data):
    return execute(
        """
        INSERT INTO expenses (budget_item_id, description, amount, incurred_on)
        VALUES (%s, %s, %s, %s)
        RETURNING id
        """,
        (data["budget_item_id"], data.get("description"), data["amount"], data["incurred_on"]),
    )


def delete_expense(expense_id):
    return execute("DELETE FROM expenses WHERE id = %s RETURNING id", (expense_id,))
