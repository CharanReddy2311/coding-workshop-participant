"""Direct unit tests for backend/allocations-service/repository.py.

test_allocations_service.py mocks repository.py wholesale to test
function.py's HTTP contract, which means repository.py's own code never
actually runs there. These tests close that gap: only `_shared.db`'s
query_all/query_one/execute are replaced, so every real line of
repository.py executes for real — most importantly overlapping_pct's
exclude_id branch and update_allocation's conditional daterange rebuild,
which is the actual logic behind the boundary/exclusion behavior asserted
at the HTTP level in test_allocations_service.py.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def allocations(load_service):
    return load_service("allocations-service")


@pytest.fixture
def db(allocations, monkeypatch):
    mocks = {
        "query_all": MagicMock(return_value=[]),
        "query_one": MagicMock(return_value=None),
        "execute": MagicMock(return_value={"id": "returned-id"}),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(allocations.repository, name, mock)
    return mocks


class TestBuildFilters:
    def test_no_params_produces_no_where_clause(self, allocations):
        where, values = allocations.repository._build_filters({})
        assert where == ""
        assert values == []

    def test_user_and_project_filters(self, allocations):
        where, values = allocations.repository._build_filters({"user_id": "u1", "project_id": "p1"})
        assert "a.user_id = %s" in where
        assert "a.project_id = %s" in where
        assert values == ["u1", "p1"]


class TestListAllocations:
    def test_shapes_meta_from_count_query(self, allocations, db):
        db["query_one"].return_value = {"count": 7}
        db["query_all"].return_value = [{"id": "a1"}]

        rows, meta = allocations.repository.list_allocations({"limit": "5"})

        assert rows == [{"id": "a1"}]
        assert meta == {"total": 7, "limit": 5, "offset": 0}

    def test_sort_by_start_date_uses_the_range_expression_not_a_bare_column(self, allocations, db):
        """start_date isn't a real column — it's derived from `period` — so
        sorting by it must use SORT_EXPRESSIONS, not a plain identifier."""
        db["query_one"].return_value = {"count": 0}
        allocations.repository.list_allocations({"sort": "start_date"})
        page_sql = db["query_all"].call_args[0][0]
        assert "ORDER BY lower(a.period)" in page_sql

    def test_unknown_sort_falls_back_to_created_at(self, allocations, db):
        db["query_one"].return_value = {"count": 0}
        allocations.repository.list_allocations({"sort": "nonsense"})
        page_sql = db["query_all"].call_args[0][0]
        assert "ORDER BY a.created_at" in page_sql


class TestOverlappingPct:
    def test_extracts_total_from_the_query_result(self, allocations, db):
        db["query_one"].return_value = {"total": 60}
        result = allocations.repository.overlapping_pct("u1", "2027-01-01", "2027-06-30")
        assert result == 60

    def test_queries_the_overlap_operator_scoped_to_the_user(self, allocations, db):
        db["query_one"].return_value = {"total": 0}
        allocations.repository.overlapping_pct("u1", "2027-01-01", "2027-06-30")
        sql, params = db["query_one"].call_args[0]
        assert "period && daterange(%s, %s, '[]')" in sql
        assert "WHERE user_id = %s" in sql
        assert params == ["u1", "2027-01-01", "2027-06-30"]

    def test_exclude_id_adds_id_not_equal_clause(self, allocations, db):
        db["query_one"].return_value = {"total": 0}
        allocations.repository.overlapping_pct("u1", "2027-01-01", "2027-06-30", exclude_id="a1")
        sql, params = db["query_one"].call_args[0]
        assert "AND id <> %s" in sql
        assert params == ["u1", "2027-01-01", "2027-06-30", "a1"]

    def test_no_exclude_id_omits_the_clause(self, allocations, db):
        db["query_one"].return_value = {"total": 0}
        allocations.repository.overlapping_pct("u1", "2027-01-01", "2027-06-30")
        sql, params = db["query_one"].call_args[0]
        assert "id <> %s" not in sql
        assert len(params) == 3


class TestCreateAllocation:
    def test_builds_insert_with_daterange_constructor(self, allocations, db):
        data = {
            "user_id": "u1",
            "project_id": "p1",
            "allocation_pct": 40,
            "start_date": "2027-01-01",
            "end_date": "2027-06-30",
        }
        allocations.repository.create_allocation(data)
        sql, params = db["execute"].call_args[0]
        assert "daterange(%s, %s, '[]')" in sql
        assert params == ("u1", "p1", None, 40, "2027-01-01", "2027-06-30")

    def test_role_on_project_defaults_to_none_when_absent(self, allocations, db):
        data = {"user_id": "u1", "project_id": "p1", "allocation_pct": 40, "start_date": "2027-01-01", "end_date": "2027-06-30"}
        allocations.repository.create_allocation(data)
        _, params = db["execute"].call_args[0]
        assert params[2] is None


class TestUpdateAllocation:
    def test_updates_only_the_submitted_plain_columns(self, allocations, db):
        allocations.repository.update_allocation("a1", {"allocation_pct": 75}, {"allocation_pct": 75})
        sql, params = db["execute"].call_args[0]
        assert "allocation_pct = %s" in sql
        assert "period = " not in sql
        assert params == [75, "a1"]

    def test_rebuilds_period_when_start_date_changes(self, allocations, db):
        merged = {"start_date": "2027-02-01", "end_date": "2027-06-30"}
        allocations.repository.update_allocation("a1", {"start_date": "2027-02-01"}, merged)
        sql, params = db["execute"].call_args[0]
        assert "period = daterange(%s, %s, '[]')" in sql
        # The rebuilt range uses the *merged* (effective) dates, not just
        # the partial value that was actually submitted.
        assert "2027-02-01" in params
        assert "2027-06-30" in params

    def test_rebuilds_period_when_only_end_date_changes(self, allocations, db):
        """A partial update touching only end_date still has to rewrite the
        whole daterange using the merged start_date, since period is one
        atomic column, not two independent fields."""
        merged = {"start_date": "2027-01-01", "end_date": "2027-08-31"}
        allocations.repository.update_allocation("a1", {"end_date": "2027-08-31"}, merged)
        sql, params = db["execute"].call_args[0]
        assert "period = daterange(%s, %s, '[]')" in sql
        assert "2027-01-01" in params
        assert "2027-08-31" in params

    def test_combines_plain_columns_and_period_in_one_statement(self, allocations, db):
        merged = {"allocation_pct": 50, "start_date": "2027-01-01", "end_date": "2027-03-01"}
        allocations.repository.update_allocation(
            "a1", {"allocation_pct": 50, "end_date": "2027-03-01"}, merged
        )
        sql, params = db["execute"].call_args[0]
        assert "allocation_pct = %s" in sql
        assert "period = daterange(%s, %s, '[]')" in sql
        assert params == [50, "2027-01-01", "2027-03-01", "a1"]


class TestDeleteAllocation:
    def test_deletes_by_id(self, allocations, db):
        allocations.repository.delete_allocation("a1")
        sql, params = db["execute"].call_args[0]
        assert "DELETE FROM allocations WHERE id = %s" in sql
        assert params == ("a1",)
