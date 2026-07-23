"""Tests for backend/budget-service/function.py.

Drives the real handler() end to end — routing across the summary/items/
expenses sub-resources, RBAC, validation, foreign-key checks, the consumed-vs-
planned rollup arithmetic, and HTTP status mapping — with only repository.py's
database calls replaced by controllable doubles.
"""

import json
import uuid
from unittest.mock import MagicMock

import pytest

PROJECT_ID = str(uuid.uuid4())
ITEM_ID = str(uuid.uuid4())
EXPENSE_ID = str(uuid.uuid4())

ITEM_ROW = {
    "id": ITEM_ID,
    "project_id": PROJECT_ID,
    "category": "Cloud",
    "planned_amount": 3000.0,
    "created_at": "2026-01-01T00:00:00+00:00",
    "project_code": "PR01",
    "project_name": "Alpha",
    "consumed": 500.0,
}

EXPENSE_ROW = {
    "id": EXPENSE_ID,
    "budget_item_id": ITEM_ID,
    "description": "EC2",
    "amount": 500.0,
    "incurred_on": "2027-02-01",
    "created_at": "2026-01-01T00:00:00+00:00",
    "category": "Cloud",
    "project_id": PROJECT_ID,
    "project_code": "PR01",
}

SUMMARY_ROWS = [
    {"project_id": PROJECT_ID, "project_code": "PR01", "project_name": "Alpha",
     "project_status": "ACTIVE", "planned_budget": 10000, "planned_itemized": 9000, "consumed": 4000},
    {"project_id": str(uuid.uuid4()), "project_code": "PR02", "project_name": "Beta",
     "project_status": "ACTIVE", "planned_budget": 5000, "planned_itemized": 4000, "consumed": 6000},
    {"project_id": str(uuid.uuid4()), "project_code": "PR03", "project_name": "Gamma",
     "project_status": "PLANNING", "planned_budget": 0, "planned_itemized": 0, "consumed": 0},
]

VALID_ITEM = {"project_id": PROJECT_ID, "category": "Cloud", "planned_amount": 3000}
VALID_EXPENSE = {"budget_item_id": ITEM_ID, "amount": 500, "incurred_on": "2027-02-01"}


@pytest.fixture
def budget(load_service):
    return load_service("budget-service")


@pytest.fixture
def mock_repo(budget, monkeypatch):
    repo = budget.repository
    mocks = {
        "budget_summary": MagicMock(return_value=SUMMARY_ROWS),
        "list_items": MagicMock(return_value=[ITEM_ROW]),
        "get_item": MagicMock(return_value=ITEM_ROW),
        "create_item": MagicMock(return_value={"id": ITEM_ID}),
        "update_item": MagicMock(return_value={"id": ITEM_ID}),
        "delete_item": MagicMock(return_value={"id": ITEM_ID}),
        "list_expenses": MagicMock(return_value=[EXPENSE_ROW]),
        "get_expense": MagicMock(return_value=EXPENSE_ROW),
        "create_expense": MagicMock(return_value={"id": EXPENSE_ID}),
        "delete_expense": MagicMock(return_value={"id": EXPENSE_ID}),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(repo, name, mock)
    exists_mock = MagicMock(return_value=True)
    monkeypatch.setattr(budget.function, "exists", exists_mock)
    mocks["exists"] = exists_mock
    return mocks


class TestSummary:
    def test_returns_200_with_derived_fields(self, budget, make_event, make_token, mock_repo):
        event = make_event("GET", "/api/budget-service/summary", token=make_token("VIEWER"))
        result = budget.function.handler(event, {})
        assert result["statusCode"] == 200
        rows = json.loads(result["body"])["data"]

        alpha = rows[0]
        assert alpha["consumed"] == 4000
        assert alpha["remaining"] == 6000
        assert alpha["consumed_pct"] == 40.0
        assert alpha["over_budget"] is False

    def test_flags_over_budget_projects(self, budget, make_event, make_token, mock_repo):
        event = make_event("GET", "/api/budget-service/summary", token=make_token("VIEWER"))
        rows = json.loads(budget.function.handler(event, {})["body"])["data"]
        beta = rows[1]
        assert beta["consumed_pct"] == 120.0
        assert beta["over_budget"] is True
        assert beta["remaining"] == -1000

    def test_zero_planned_budget_yields_null_pct_not_divide_by_zero(self, budget, make_event, make_token, mock_repo):
        event = make_event("GET", "/api/budget-service/summary", token=make_token("VIEWER"))
        rows = json.loads(budget.function.handler(event, {})["body"])["data"]
        gamma = rows[2]
        assert gamma["consumed_pct"] is None
        assert gamma["over_budget"] is False


class TestBudgetItems:
    def test_create_item_returns_201(self, budget, make_event, make_token, mock_repo):
        event = make_event("POST", "/api/budget-service/items", body=VALID_ITEM, token=make_token("CONTRIBUTOR"))
        result = budget.function.handler(event, {})
        assert result["statusCode"] == 201, result["body"]
        mock_repo["create_item"].assert_called_once()

    def test_create_item_unknown_project_returns_400(self, budget, make_event, make_token, mock_repo):
        mock_repo["exists"].return_value = False
        event = make_event("POST", "/api/budget-service/items", body=VALID_ITEM, token=make_token("CONTRIBUTOR"))
        result = budget.function.handler(event, {})
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["error"]["details"]["project_id"] == "no project exists with this id"
        mock_repo["create_item"].assert_not_called()

    def test_create_item_missing_fields_returns_400(self, budget, make_event, make_token, mock_repo):
        event = make_event("POST", "/api/budget-service/items", body={}, token=make_token("CONTRIBUTOR"))
        result = budget.function.handler(event, {})
        assert result["statusCode"] == 400
        assert set(json.loads(result["body"])["error"]["details"]) == {"project_id", "category", "planned_amount"}

    def test_negative_planned_amount_returns_400(self, budget, make_event, make_token, mock_repo):
        body = {**VALID_ITEM, "planned_amount": -5}
        event = make_event("POST", "/api/budget-service/items", body=body, token=make_token("CONTRIBUTOR"))
        assert budget.function.handler(event, {})["statusCode"] == 400

    def test_list_items_returns_200(self, budget, make_event, make_token, mock_repo):
        event = make_event("GET", "/api/budget-service/items", query={"project_id": PROJECT_ID}, token=make_token("VIEWER"))
        assert budget.function.handler(event, {})["statusCode"] == 200

    def test_update_item_returns_200(self, budget, make_event, make_token, mock_repo):
        event = make_event("PUT", f"/api/budget-service/items/{ITEM_ID}", body={"planned_amount": 4000}, token=make_token("CONTRIBUTOR"))
        assert budget.function.handler(event, {})["statusCode"] == 200

    def test_update_item_cannot_move_project(self, budget, make_event, make_token, mock_repo):
        # project_id is not an updatable field; the validator rejects it.
        event = make_event("PUT", f"/api/budget-service/items/{ITEM_ID}", body={"project_id": str(uuid.uuid4())}, token=make_token("CONTRIBUTOR"))
        assert budget.function.handler(event, {})["statusCode"] == 400

    def test_get_missing_item_returns_404(self, budget, make_event, make_token, mock_repo):
        mock_repo["get_item"].return_value = None
        event = make_event("GET", f"/api/budget-service/items/{uuid.uuid4()}", token=make_token("VIEWER"))
        assert budget.function.handler(event, {})["statusCode"] == 404


class TestExpenses:
    def test_create_expense_returns_201(self, budget, make_event, make_token, mock_repo):
        event = make_event("POST", "/api/budget-service/expenses", body=VALID_EXPENSE, token=make_token("CONTRIBUTOR"))
        result = budget.function.handler(event, {})
        assert result["statusCode"] == 201, result["body"]

    def test_create_expense_unknown_item_returns_400(self, budget, make_event, make_token, mock_repo):
        mock_repo["exists"].return_value = False
        event = make_event("POST", "/api/budget-service/expenses", body=VALID_EXPENSE, token=make_token("CONTRIBUTOR"))
        result = budget.function.handler(event, {})
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["error"]["details"]["budget_item_id"] == "no budget item exists with this id"

    def test_delete_expense_returns_204(self, budget, make_event, make_token, mock_repo):
        event = make_event("DELETE", f"/api/budget-service/expenses/{EXPENSE_ID}", token=make_token("MANAGER"))
        result = budget.function.handler(event, {})
        assert result["statusCode"] == 204
        mock_repo["delete_expense"].assert_called_once_with(EXPENSE_ID)


class TestRBAC:
    @pytest.mark.parametrize("role", ["VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"])
    def test_summary_readable_by_all_roles(self, budget, make_event, make_token, mock_repo, role):
        event = make_event("GET", "/api/budget-service/summary", token=make_token(role))
        assert budget.function.handler(event, {})["statusCode"] == 200

    @pytest.mark.parametrize("role,expected", [("VIEWER", 403), ("CONTRIBUTOR", 201), ("MANAGER", 201), ("ADMIN", 201)])
    def test_create_requires_contributor_or_above(self, budget, make_event, make_token, mock_repo, role, expected):
        event = make_event("POST", "/api/budget-service/items", body=VALID_ITEM, token=make_token(role))
        assert budget.function.handler(event, {})["statusCode"] == expected

    @pytest.mark.parametrize("role,expected", [("VIEWER", 403), ("CONTRIBUTOR", 403), ("MANAGER", 204), ("ADMIN", 204)])
    def test_delete_requires_manager_or_above(self, budget, make_event, make_token, mock_repo, role, expected):
        event = make_event("DELETE", f"/api/budget-service/items/{ITEM_ID}", token=make_token(role))
        assert budget.function.handler(event, {})["statusCode"] == expected

    def test_options_bypasses_auth(self, budget, make_event):
        assert budget.function.handler(make_event("OPTIONS", "/api/budget-service/summary"), {})["statusCode"] == 204

    def test_missing_token_returns_401(self, budget, make_event):
        assert budget.function.handler(make_event("GET", "/api/budget-service/summary"), {})["statusCode"] == 401

    def test_unknown_route_returns_404(self, budget, make_event, make_token, mock_repo):
        event = make_event("GET", "/api/budget-service/nonsense", token=make_token("ADMIN"))
        assert budget.function.handler(event, {})["statusCode"] == 404


class TestRoutingEdges:
    def test_get_item_by_id_returns_200(self, budget, make_event, make_token, mock_repo):
        event = make_event("GET", f"/api/budget-service/items/{ITEM_ID}", token=make_token("VIEWER"))
        assert budget.function.handler(event, {})["statusCode"] == 200

    def test_get_expense_by_id_returns_200(self, budget, make_event, make_token, mock_repo):
        event = make_event("GET", f"/api/budget-service/expenses/{EXPENSE_ID}", token=make_token("VIEWER"))
        assert budget.function.handler(event, {})["statusCode"] == 200

    def test_get_missing_expense_returns_404(self, budget, make_event, make_token, mock_repo):
        mock_repo["get_expense"].return_value = None
        event = make_event("GET", f"/api/budget-service/expenses/{uuid.uuid4()}", token=make_token("VIEWER"))
        assert budget.function.handler(event, {})["statusCode"] == 404

    def test_update_missing_item_returns_404(self, budget, make_event, make_token, mock_repo):
        mock_repo["get_item"].return_value = None
        event = make_event("PUT", f"/api/budget-service/items/{uuid.uuid4()}", body={"planned_amount": 1}, token=make_token("CONTRIBUTOR"))
        assert budget.function.handler(event, {})["statusCode"] == 404

    def test_delete_missing_item_returns_404(self, budget, make_event, make_token, mock_repo):
        mock_repo["get_item"].return_value = None
        event = make_event("DELETE", f"/api/budget-service/items/{uuid.uuid4()}", token=make_token("MANAGER"))
        assert budget.function.handler(event, {})["statusCode"] == 404

    def test_delete_missing_expense_returns_404(self, budget, make_event, make_token, mock_repo):
        mock_repo["get_expense"].return_value = None
        event = make_event("DELETE", f"/api/budget-service/expenses/{uuid.uuid4()}", token=make_token("MANAGER"))
        assert budget.function.handler(event, {})["statusCode"] == 404

    def test_unsupported_method_returns_405(self, budget, make_event, make_token, mock_repo):
        event = make_event("PATCH", "/api/budget-service/summary", token=make_token("ADMIN"))
        assert budget.function.handler(event, {})["statusCode"] == 405

    def test_no_resource_path_returns_404(self, budget, make_event, make_token, mock_repo):
        event = make_event("GET", "/api/budget-service", token=make_token("ADMIN"))
        assert budget.function.handler(event, {})["statusCode"] == 404

    def test_post_to_expense_id_is_unknown_route_404(self, budget, make_event, make_token, mock_repo):
        event = make_event("POST", f"/api/budget-service/expenses/{EXPENSE_ID}", body={}, token=make_token("ADMIN"))
        assert budget.function.handler(event, {})["statusCode"] == 404
