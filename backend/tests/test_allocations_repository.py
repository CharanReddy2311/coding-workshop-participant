"""Direct unit tests for backend/allocations-service/repository.py.

test_allocations_service.py mocks repository.py wholesale to test function.py's
HTTP contract, which means repository.py's own code never actually runs there.
These tests close that gap: only `_shared.db`'s query helpers / cursor are
replaced, so every real line of repository.py executes for real — most
importantly the sweep-line peak query, the per-user advisory lock taken before
each write, and update_allocation's conditional daterange rebuild.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def allocations(load_service):
    return load_service("allocations-service")


@pytest.fixture
def db(allocations, monkeypatch):
    """Replaces the read helpers and `execute` (used by delete)."""
    mocks = {
        "query_all": MagicMock(return_value=[]),
        "query_one": MagicMock(return_value=None),
        "execute": MagicMock(return_value={"id": "returned-id"}),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(allocations.repository, name, mock)
    return mocks


def _fake_cursor(monkeypatch, allocations, fetchone_results):
    """Point repository.cursor at a fake context manager yielding a cursor
    whose fetchone() returns the queued results in order. Returns the cursor so
    tests can inspect its .execute call log."""
    cur = MagicMock()
    cur.fetchone.side_effect = list(fetchone_results)
    cm = MagicMock()
    cm.__enter__.return_value = cur
    cm.__exit__.return_value = False
    monkeypatch.setattr(allocations.repository, "cursor", MagicMock(return_value=cm))
    return cur


def _executed(cur, needle):
    """Every SQL string this cursor executed that contains `needle`."""
    return [call[0][0] for call in cur.execute.call_args_list if needle in call[0][0]]


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
        db["query_one"].return_value = {"count": 0}
        allocations.repository.list_allocations({"sort": "start_date"})
        page_sql = db["query_all"].call_args[0][0]
        assert "ORDER BY lower(a.period)" in page_sql

    def test_unknown_sort_falls_back_to_created_at(self, allocations, db):
        db["query_one"].return_value = {"count": 0}
        allocations.repository.list_allocations({"sort": "nonsense"})
        page_sql = db["query_all"].call_args[0][0]
        assert "ORDER BY a.created_at" in page_sql


class TestPeakExistingPct:
    """The read-only sweep-line probe used by function.py's friendly pre-check."""

    def test_extracts_peak_from_the_query_result(self, allocations, db):
        db["query_one"].return_value = {"peak": 60}
        result = allocations.repository.peak_existing_pct("u1", "2027-01-01", "2027-06-30")
        assert result == 60

    def test_none_result_is_treated_as_zero(self, allocations, db):
        db["query_one"].return_value = None
        assert allocations.repository.peak_existing_pct("u1", "2027-01-01", "2027-06-30") == 0

    def test_queries_the_overlap_operator_scoped_to_the_user(self, allocations, db):
        db["query_one"].return_value = {"peak": 0}
        allocations.repository.peak_existing_pct("u1", "2027-01-01", "2027-06-30")
        sql, params = db["query_one"].call_args[0]
        assert "period && daterange(%s, %s, '[]')" in sql
        assert "user_id = %s" in sql
        # A sweep line, not a naive SUM over every overlapping row.
        assert "MAX(load)" in sql
        # user_id, start, end (overlap) + start, start, end (boundaries)
        assert params == ["u1", "2027-01-01", "2027-06-30", "2027-01-01", "2027-01-01", "2027-06-30"]

    def test_exclude_id_adds_id_not_equal_clause(self, allocations, db):
        db["query_one"].return_value = {"peak": 0}
        allocations.repository.peak_existing_pct("u1", "2027-01-01", "2027-06-30", exclude_id="a1")
        sql, params = db["query_one"].call_args[0]
        assert "AND id <> %s" in sql
        assert params == ["u1", "2027-01-01", "2027-06-30", "a1", "2027-01-01", "2027-01-01", "2027-06-30"]

    def test_no_exclude_id_omits_the_clause(self, allocations, db):
        db["query_one"].return_value = {"peak": 0}
        allocations.repository.peak_existing_pct("u1", "2027-01-01", "2027-06-30")
        sql, _ = db["query_one"].call_args[0]
        assert "id <> %s" not in sql


class TestCreateAllocation:
    BASE = {
        "user_id": "u1",
        "project_id": "p1",
        "allocation_pct": 40,
        "start_date": "2027-01-01",
        "end_date": "2027-06-30",
    }

    def test_builds_insert_with_daterange_constructor(self, allocations, monkeypatch):
        cur = _fake_cursor(monkeypatch, allocations, [(0,), ("returned-id",)])
        result = allocations.repository.create_allocation(dict(self.BASE))
        assert result == {"id": "returned-id"}
        insert_sql = _executed(cur, "INSERT INTO allocations")[0]
        assert "daterange(%s, %s, '[]')" in insert_sql
        insert_params = [
            c[0][1] for c in cur.execute.call_args_list if "INSERT INTO allocations" in c[0][0]
        ][0]
        assert insert_params == ("u1", "p1", None, 40, "2027-01-01", "2027-06-30")

    def test_advisory_lock_is_taken_before_the_write(self, allocations, monkeypatch):
        cur = _fake_cursor(monkeypatch, allocations, [(0,), ("returned-id",)])
        allocations.repository.create_allocation(dict(self.BASE))
        # The very first statement on the connection is the per-user lock.
        assert "pg_advisory_xact_lock" in cur.execute.call_args_list[0][0][0]

    def test_role_on_project_defaults_to_none_when_absent(self, allocations, monkeypatch):
        cur = _fake_cursor(monkeypatch, allocations, [(0,), ("returned-id",)])
        allocations.repository.create_allocation(dict(self.BASE))
        insert_params = [
            c[0][1] for c in cur.execute.call_args_list if "INSERT INTO allocations" in c[0][0]
        ][0]
        assert insert_params[2] is None

    def test_over_capacity_raises_conflict_and_does_not_insert(self, allocations, monkeypatch):
        # Peak existing 80 + requested 40 = 120 > 100.
        cur = _fake_cursor(monkeypatch, allocations, [(80,)])
        with pytest.raises(allocations.http.ConflictError):
            allocations.repository.create_allocation(dict(self.BASE))
        assert _executed(cur, "INSERT INTO allocations") == []


class TestUpdateAllocation:
    def _merged(self, **overrides):
        base = {
            "user_id": "u1",
            "allocation_pct": 75,
            "start_date": "2027-01-01",
            "end_date": "2027-06-30",
        }
        base.update(overrides)
        return base

    def test_updates_only_the_submitted_plain_columns(self, allocations, monkeypatch):
        cur = _fake_cursor(monkeypatch, allocations, [(0,), ("a1",)])
        allocations.repository.update_allocation("a1", {"allocation_pct": 75}, self._merged())
        update_call = [c for c in cur.execute.call_args_list if "UPDATE allocations" in c[0][0]][0]
        sql, params = update_call[0]
        assert "allocation_pct = %s" in sql
        assert "period = " not in sql
        assert params == [75, "a1"]

    def test_rebuilds_period_when_start_date_changes(self, allocations, monkeypatch):
        cur = _fake_cursor(monkeypatch, allocations, [(0,), ("a1",)])
        merged = self._merged(start_date="2027-02-01", end_date="2027-06-30")
        allocations.repository.update_allocation("a1", {"start_date": "2027-02-01"}, merged)
        sql, params = [c[0] for c in cur.execute.call_args_list if "UPDATE allocations" in c[0][0]][0]
        assert "period = daterange(%s, %s, '[]')" in sql
        assert "2027-02-01" in params and "2027-06-30" in params

    def test_rebuilds_period_when_only_end_date_changes(self, allocations, monkeypatch):
        cur = _fake_cursor(monkeypatch, allocations, [(0,), ("a1",)])
        merged = self._merged(end_date="2027-08-31")
        allocations.repository.update_allocation("a1", {"end_date": "2027-08-31"}, merged)
        sql, params = [c[0] for c in cur.execute.call_args_list if "UPDATE allocations" in c[0][0]][0]
        assert "period = daterange(%s, %s, '[]')" in sql
        assert "2027-01-01" in params and "2027-08-31" in params

    def test_combines_plain_columns_and_period_in_one_statement(self, allocations, monkeypatch):
        cur = _fake_cursor(monkeypatch, allocations, [(0,), ("a1",)])
        merged = self._merged(allocation_pct=50, end_date="2027-03-01")
        allocations.repository.update_allocation(
            "a1", {"allocation_pct": 50, "end_date": "2027-03-01"}, merged
        )
        sql, params = [c[0] for c in cur.execute.call_args_list if "UPDATE allocations" in c[0][0]][0]
        assert "allocation_pct = %s" in sql
        assert "period = daterange(%s, %s, '[]')" in sql
        assert params == [50, "2027-01-01", "2027-03-01", "a1"]

    def test_over_capacity_raises_conflict_and_does_not_update(self, allocations, monkeypatch):
        cur = _fake_cursor(monkeypatch, allocations, [(80,)])
        with pytest.raises(allocations.http.ConflictError):
            allocations.repository.update_allocation("a1", {"allocation_pct": 30}, self._merged(allocation_pct=30))
        assert _executed(cur, "UPDATE allocations") == []

    def test_capacity_check_excludes_this_rows_own_allocation(self, allocations, monkeypatch):
        cur = _fake_cursor(monkeypatch, allocations, [(0,), ("a1",)])
        allocations.repository.update_allocation("a1", {"allocation_pct": 75}, self._merged())
        peak_sql = _executed(cur, "period && daterange")[0]
        assert "id <> %s" in peak_sql


class TestDeleteAllocation:
    def test_deletes_by_id(self, allocations, db):
        allocations.repository.delete_allocation("a1")
        sql, params = db["execute"].call_args[0]
        assert "DELETE FROM allocations WHERE id = %s" in sql
        assert params == ("a1",)
