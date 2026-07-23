"""Direct unit tests for backend/budget-service/repository.py.

test_budget_service.py mocks repository.py wholesale, so its SQL never runs
there. These tests replace only `_shared.db`'s query_all/query_one/execute, so
every real line of repository.py executes — the consumed-vs-planned summary
rollup, item/expense filters, the dynamic UPDATE, and the unique-violation ->
ConflictError mapping on budget items.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def budget(load_service):
    return load_service("budget-service")


@pytest.fixture
def db(budget, monkeypatch):
    mocks = {
        "query_all": MagicMock(return_value=[]),
        "query_one": MagicMock(return_value={"id": "x1"}),
        "execute": MagicMock(return_value={"id": "x1"}),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(budget.repository, name, mock)
    return mocks


class TestSummary:
    def test_summary_rolls_up_expenses_against_planned_per_project(self, budget, db):
        db["query_all"].return_value = [{"project_code": "PR01", "planned_budget": 100, "consumed": 40}]
        rows = budget.repository.budget_summary()
        assert rows[0]["project_code"] == "PR01"
        sql = db["query_all"].call_args[0][0]
        assert "FROM projects p" in sql
        assert "budget_items" in sql and "expenses" in sql
        assert "planned_budget" in sql and "consumed" in sql


class TestBudgetItems:
    def test_list_items_no_filter(self, budget, db):
        budget.repository.list_items({})
        sql, params = db["query_all"].call_args[0]
        assert "FROM budget_items bi" in sql and params == []

    def test_list_items_filters_by_project(self, budget, db):
        budget.repository.list_items({"project_id": "p1"})
        sql, params = db["query_all"].call_args[0]
        assert "bi.project_id = %s" in sql and params == ["p1"]

    def test_list_items_unknown_sort_falls_back(self, budget, db):
        budget.repository.list_items({"sort": "; drop"})
        assert "ORDER BY bi.created_at" in db["query_all"].call_args[0][0]

    def test_get_item_by_id(self, budget, db):
        budget.repository.get_item("i1")
        sql, params = db["query_one"].call_args[0]
        assert "WHERE bi.id = %s" in sql and params == ("i1",)

    def test_create_item_inserts_planned_amount(self, budget, db):
        budget.repository.create_item({"project_id": "p1", "category": "Cloud", "planned_amount": 3000})
        sql, params = db["execute"].call_args[0]
        assert "INSERT INTO budget_items" in sql
        assert params == ("p1", "Cloud", 3000)

    def test_create_item_duplicate_category_maps_to_conflict(self, budget, monkeypatch):
        monkeypatch.setattr(budget.repository, "execute", MagicMock(side_effect=Exception("dup")))
        monkeypatch.setattr(budget.repository, "is_unique_violation", lambda exc: True)
        with pytest.raises(budget.http.ConflictError):
            budget.repository.create_item({"project_id": "p1", "category": "Cloud", "planned_amount": 1})

    def test_update_item_builds_dynamic_set(self, budget, db):
        budget.repository.update_item("i1", {"planned_amount": 5000})
        sql, params = db["execute"].call_args[0]
        assert "UPDATE budget_items SET" in sql and "planned_amount = %s" in sql
        assert params == [5000, "i1"]

    def test_update_item_duplicate_maps_to_conflict(self, budget, monkeypatch):
        monkeypatch.setattr(budget.repository, "execute", MagicMock(side_effect=Exception("dup")))
        monkeypatch.setattr(budget.repository, "is_unique_violation", lambda exc: True)
        with pytest.raises(budget.http.ConflictError):
            budget.repository.update_item("i1", {"category": "Cloud"})

    def test_delete_item_by_id(self, budget, db):
        budget.repository.delete_item("i1")
        sql, params = db["execute"].call_args[0]
        assert "DELETE FROM budget_items WHERE id = %s" in sql and params == ("i1",)


class TestExpenses:
    def test_list_expenses_filters_by_project_and_item(self, budget, db):
        budget.repository.list_expenses({"project_id": "p1", "budget_item_id": "i1"})
        sql, params = db["query_all"].call_args[0]
        assert "ex.budget_item_id = %s" in sql and "bi.project_id = %s" in sql
        assert set(params) == {"p1", "i1"}

    def test_get_expense_by_id(self, budget, db):
        budget.repository.get_expense("e1")
        sql, params = db["query_one"].call_args[0]
        assert "WHERE ex.id = %s" in sql and params == ("e1",)

    def test_create_expense_inserts_all_columns(self, budget, db):
        budget.repository.create_expense(
            {"budget_item_id": "i1", "description": "EC2", "amount": 500, "incurred_on": "2027-02-01"}
        )
        sql, params = db["execute"].call_args[0]
        assert "INSERT INTO expenses" in sql
        assert params == ("i1", "EC2", 500, "2027-02-01")

    def test_create_expense_description_defaults_to_none(self, budget, db):
        budget.repository.create_expense({"budget_item_id": "i1", "amount": 500, "incurred_on": "2027-02-01"})
        _, params = db["execute"].call_args[0]
        assert params[1] is None

    def test_delete_expense_by_id(self, budget, db):
        budget.repository.delete_expense("e1")
        sql, params = db["execute"].call_args[0]
        assert "DELETE FROM expenses WHERE id = %s" in sql and params == ("e1",)
