"""budget-service — planned budget items, actual expenses, and the rollup.

    GET    /api/budget-service/summary            consumed vs planned, per project
    GET    /api/budget-service/items              list budget items (?project_id=)
    POST   /api/budget-service/items              create a budget item
    GET    /api/budget-service/items/{id}         read one budget item
    PUT    /api/budget-service/items/{id}         update a budget item
    DELETE /api/budget-service/items/{id}         delete a budget item (expenses cascade)
    GET    /api/budget-service/expenses           list expenses (?project_id=/?budget_item_id=)
    POST   /api/budget-service/expenses           record an expense
    GET    /api/budget-service/expenses/{id}      read one expense
    DELETE /api/budget-service/expenses/{id}      delete an expense

`/summary` answers the business question directly: "how much budget has been
consumed versus planned for each project?" — one row per project, every project
included.
"""

import logging

import repository
from schema import BUDGET_ITEM_SCHEMA, EXPENSE_SCHEMA

from _shared.auth import authorize
from _shared.db import exists
from _shared.http import (
    ApiError,
    NotFoundError,
    ValidationError,
    http_method,
    parse_body,
    path_segments,
    query_params,
    response,
    with_http_errors,
)
from _shared.validation import validate

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SERVICE_NAME = "budget-service"
SUPPORTED_METHODS = ("GET", "POST", "PUT", "DELETE", "OPTIONS")

# Everyone reads budget data; Contributors and Managers record it; Managers and
# Admins can delete (aligned with the platform-wide DELETE matrix).
PERMISSIONS = {
    "GET": ("VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"),
    "OPTIONS": ("VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"),
    "POST": ("CONTRIBUTOR", "MANAGER", "ADMIN"),
    "PUT": ("CONTRIBUTOR", "MANAGER", "ADMIN"),
    "DELETE": ("MANAGER", "ADMIN"),
}


def _decimal(value):
    return float(value) if value is not None else 0.0


def get_summary():
    rows = repository.budget_summary()
    enriched = []
    for row in rows:
        planned = _decimal(row["planned_budget"])
        consumed = _decimal(row["consumed"])
        enriched.append({
            **row,
            "planned_budget": planned,
            "planned_itemized": _decimal(row["planned_itemized"]),
            "consumed": consumed,
            "remaining": round(planned - consumed, 2),
            "consumed_pct": round(consumed / planned * 100, 1) if planned > 0 else None,
            "over_budget": consumed > planned and planned > 0,
        })
    return response(200, enriched)


# --------------------------------------------------------------------------
# Budget items
# --------------------------------------------------------------------------

def list_items(event):
    return response(200, repository.list_items(query_params(event)))


def get_item(item_id):
    item = repository.get_item(item_id)
    if not item:
        raise NotFoundError(f"No budget item found with id {item_id}")
    return response(200, item)


def create_item(event):
    data = validate(parse_body(event), BUDGET_ITEM_SCHEMA)
    if not exists("projects", data["project_id"]):
        raise ValidationError(
            "One or more references are invalid",
            details={"project_id": "no project exists with this id"},
        )
    created = repository.create_item(data)
    logger.info("Created budget item %s", created["id"])
    return response(201, repository.get_item(created["id"]))


def update_item(event, item_id):
    if not repository.get_item(item_id):
        raise NotFoundError(f"No budget item found with id {item_id}")
    # project_id is immutable here: moving an item between projects would
    # silently rewrite spend history, so only category/planned_amount update.
    data = validate(parse_body(event),
                    {k: BUDGET_ITEM_SCHEMA[k] for k in ("category", "planned_amount")},
                    partial=True)
    repository.update_item(item_id, data)
    logger.info("Updated budget item %s (fields: %s)", item_id, ", ".join(data))
    return response(200, repository.get_item(item_id))


def delete_item(item_id):
    if not repository.get_item(item_id):
        raise NotFoundError(f"No budget item found with id {item_id}")
    repository.delete_item(item_id)
    logger.info("Deleted budget item %s", item_id)
    return response(204)


# --------------------------------------------------------------------------
# Expenses
# --------------------------------------------------------------------------

def list_expenses(event):
    return response(200, repository.list_expenses(query_params(event)))


def get_expense(expense_id):
    expense = repository.get_expense(expense_id)
    if not expense:
        raise NotFoundError(f"No expense found with id {expense_id}")
    return response(200, expense)


def create_expense(event):
    data = validate(parse_body(event), EXPENSE_SCHEMA)
    if not exists("budget_items", data["budget_item_id"]):
        raise ValidationError(
            "One or more references are invalid",
            details={"budget_item_id": "no budget item exists with this id"},
        )
    created = repository.create_expense(data)
    logger.info("Recorded expense %s", created["id"])
    return response(201, repository.get_expense(created["id"]))


def delete_expense(expense_id):
    if not repository.get_expense(expense_id):
        raise NotFoundError(f"No expense found with id {expense_id}")
    repository.delete_expense(expense_id)
    logger.info("Deleted expense %s", expense_id)
    return response(204)


def _route(method, resource, resource_id, event):
    if resource == "summary" and method == "GET":
        return get_summary()

    if resource == "items":
        if resource_id:
            if method == "GET":
                return get_item(resource_id)
            if method == "PUT":
                return update_item(event, resource_id)
            if method == "DELETE":
                return delete_item(resource_id)
        else:
            if method == "GET":
                return list_items(event)
            if method == "POST":
                return create_item(event)

    if resource == "expenses":
        if resource_id:
            if method == "GET":
                return get_expense(resource_id)
            if method == "DELETE":
                return delete_expense(resource_id)
        else:
            if method == "GET":
                return list_expenses(event)
            if method == "POST":
                return create_expense(event)

    raise ApiError(
        f"Unknown route: {method} /{resource or ''}",
        status=404,
        code="route_not_found",
        details={"available": [
            "GET /summary",
            "GET|POST /items", "GET|PUT|DELETE /items/{id}",
            "GET|POST /expenses", "GET|DELETE /expenses/{id}",
        ]},
    )


@with_http_errors
def handler(event=None, context=None):
    event = event or {}
    method = http_method(event)

    if method == "OPTIONS":
        return response(204)

    if method not in SUPPORTED_METHODS:
        raise ApiError(f"Method {method} is not supported", status=405, code="method_not_allowed")

    user = authorize(event, PERMISSIONS)
    segments = path_segments(event, SERVICE_NAME)
    resource = segments[0] if segments else None
    resource_id = segments[1] if len(segments) > 1 else None

    logger.info("%s %s by %s (%s)", method, "/".join(segments) or "-", user["email"], user["role"])

    return _route(method, resource, resource_id, event)


if __name__ == "__main__":
    print(handler())
