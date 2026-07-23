"""Validation schemas and business rules for budget items and expenses.

Two entities share this service:

  * budget_items — a planned amount per (project, category). What was budgeted.
  * expenses     — an actual amount spent against a budget item. What was spent.

"Consumed vs planned per project" is then a rollup of expenses against
budget_items, which is exactly what the /summary route returns.
"""

from _shared.validation import Field

BUDGET_ITEM_SCHEMA = {
    "project_id": Field("uuid", required=True),
    "category": Field("string", required=True, min_length=1, max_length=120),
    "planned_amount": Field("decimal", required=True, minimum=0),
}

EXPENSE_SCHEMA = {
    "budget_item_id": Field("uuid", required=True),
    "description": Field("string", max_length=500, nullable=True),
    "amount": Field("decimal", required=True, minimum=0),
    "incurred_on": Field("date", required=True),
}

ITEM_SORTABLE = ("category", "planned_amount", "created_at")
EXPENSE_SORTABLE = ("amount", "incurred_on", "created_at")
