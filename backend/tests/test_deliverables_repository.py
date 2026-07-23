"""Direct unit tests for backend/deliverables-service/repository.py.

test_deliverables_service.py mocks repository.py wholesale; these tests
exercise its real code — most importantly would_create_cycle's recursive
CTE (the actual logic behind the 409 asserted at the HTTP level) and the
dependency-edge queries.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def deliverables(load_service):
    return load_service("deliverables-service")


@pytest.fixture
def db(deliverables, monkeypatch):
    mocks = {
        "query_all": MagicMock(return_value=[]),
        "query_one": MagicMock(return_value=None),
        "execute": MagicMock(return_value={"id": "returned-id"}),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(deliverables.repository, name, mock)
    return mocks


class TestBuildFilters:
    def test_project_owner_status_filters(self, deliverables):
        where, values = deliverables.repository._build_filters(
            {"project_id": "p1", "owner_id": "o1", "status": "IN_PROGRESS"}
        )
        for clause in ("d.project_id = %s", "d.owner_id = %s", "d.status = %s"):
            assert clause in where
        assert values == ["p1", "o1", "IN_PROGRESS"]

    def test_overdue_filter(self, deliverables):
        where, values = deliverables.repository._build_filters({"overdue": "true"})
        assert "d.due_date < CURRENT_DATE" in where
        assert "d.status NOT IN ('COMPLETED','CANCELLED')" in where

    def test_q_filter_targets_name_and_description(self, deliverables):
        where, values = deliverables.repository._build_filters({"q": "mockups"})
        assert "d.name ILIKE %s" in where
        assert values == ["%mockups%", "%mockups%"]

    def test_due_after_and_due_before_filters(self, deliverables):
        where, values = deliverables.repository._build_filters(
            {"due_after": "2027-01-01", "due_before": "2027-12-31"}
        )
        assert "d.due_date >= %s" in where
        assert "d.due_date <= %s" in where
        assert values == ["2027-01-01", "2027-12-31"]


class TestIntParam:
    def test_uses_default_when_absent(self, deliverables):
        assert deliverables.repository._int_param({}, "limit", 50, 1, 200) == 50

    def test_falls_back_to_default_on_garbage_input(self, deliverables):
        assert deliverables.repository._int_param({"limit": "abc"}, "limit", 50, 1, 200) == 50

    def test_clamps_to_bounds(self, deliverables):
        assert deliverables.repository._int_param({"limit": "9999"}, "limit", 50, 1, 200) == 200
        assert deliverables.repository._int_param({"limit": "-5"}, "limit", 50, 1, 200) == 1


class TestGetDeliverable:
    def test_queries_by_id(self, deliverables, db):
        db["query_one"].return_value = {"id": "d1"}
        assert deliverables.repository.get_deliverable("d1") == {"id": "d1"}
        sql, params = db["query_one"].call_args[0]
        assert "WHERE d.id = %s" in sql
        assert params == ("d1",)


class TestListDeliverables:
    def test_shapes_meta_from_count_query(self, deliverables, db):
        db["query_one"].return_value = {"count": 4}
        db["query_all"].return_value = [{"id": "d1"}]
        rows, meta = deliverables.repository.list_deliverables({"limit": "20"})
        assert rows == [{"id": "d1"}]
        assert meta == {"total": 4, "limit": 20, "offset": 0}


class TestCreateUpdateDelete:
    def test_create_builds_insert_from_data_keys(self, deliverables, db):
        deliverables.repository.create_deliverable({"name": "X", "due_date": "2027-01-01"})
        sql, params = db["execute"].call_args[0]
        assert "INSERT INTO deliverables (name, due_date)" in sql
        assert params == ["X", "2027-01-01"]

    def test_update_builds_assignments(self, deliverables, db):
        deliverables.repository.update_deliverable("d1", {"percent_complete": 75})
        sql, params = db["execute"].call_args[0]
        assert "UPDATE deliverables SET percent_complete = %s, updated_at = now()" in sql
        assert params == [75, "d1"]

    def test_delete_by_id(self, deliverables, db):
        deliverables.repository.delete_deliverable("d1")
        sql, params = db["execute"].call_args[0]
        assert "DELETE FROM deliverables WHERE id = %s" in sql
        assert params == ("d1",)


class TestListDependencies:
    def test_queries_predecessors_and_successors_separately(self, deliverables, db):
        predecessor_row = {"dep_type": "FINISH_TO_START", "id": "p1", "name": "Design", "status": "DONE", "due_date": "2027-01-01"}
        successor_row = {"dep_type": "FINISH_TO_START", "id": "s1", "name": "Build", "status": "NOT_STARTED", "due_date": "2027-02-01"}
        db["query_all"].side_effect = [[predecessor_row], [successor_row]]

        result = deliverables.repository.list_dependencies("d1")

        assert result == {"predecessors": [predecessor_row], "successors": [successor_row]}
        assert db["query_all"].call_count == 2
        predecessors_sql, predecessors_params = db["query_all"].call_args_list[0][0]
        assert "dd.successor_id = %s" in predecessors_sql
        assert predecessors_params == ("d1",)
        successors_sql, successors_params = db["query_all"].call_args_list[1][0]
        assert "dd.predecessor_id = %s" in successors_sql
        assert successors_params == ("d1",)


class TestWouldCreateCycle:
    """The actual cycle-prevention query: True exactly when the proposed
    successor can already reach the proposed predecessor by following
    existing edges forward."""

    def test_true_when_a_path_back_to_the_predecessor_exists(self, deliverables, db):
        db["query_one"].return_value = {"hit": 1}
        assert deliverables.repository.would_create_cycle("pred-1", "succ-1") is True

    def test_false_when_no_path_exists(self, deliverables, db):
        db["query_one"].return_value = None
        assert deliverables.repository.would_create_cycle("pred-1", "succ-1") is False

    def test_query_starts_the_walk_from_the_proposed_successor(self, deliverables, db):
        """Reachability must be walked starting from succ-1 (what the new
        edge would point at), searching for pred-1 — the reverse would
        silently fail to catch real cycles."""
        db["query_one"].return_value = None
        deliverables.repository.would_create_cycle("pred-1", "succ-1")
        sql, params = db["query_one"].call_args[0]
        assert "WITH RECURSIVE" in sql
        assert params == ("succ-1", "pred-1")


class TestAddDependency:
    def test_inserts_the_edge(self, deliverables, db):
        deliverables.repository.add_dependency("pred-1", "succ-1", "FINISH_TO_START")
        sql, params = db["execute"].call_args[0]
        assert "INSERT INTO deliverable_dependencies" in sql
        assert params == ("pred-1", "succ-1", "FINISH_TO_START")

    def test_upserts_dep_type_on_conflict(self, deliverables, db):
        """Re-adding an existing edge updates dep_type instead of erroring —
        an idempotent, POST-as-upsert design for this sub-resource."""
        deliverables.repository.add_dependency("pred-1", "succ-1", "START_TO_START")
        sql, _ = db["execute"].call_args[0]
        assert "ON CONFLICT (predecessor_id, successor_id) DO UPDATE SET dep_type = EXCLUDED.dep_type" in sql


class TestRemoveDependency:
    def test_deletes_the_specific_edge(self, deliverables, db):
        deliverables.repository.remove_dependency("pred-1", "succ-1")
        sql, params = db["execute"].call_args[0]
        assert "DELETE FROM deliverable_dependencies" in sql
        assert "predecessor_id = %s AND successor_id = %s" in sql
        assert params == ("pred-1", "succ-1")
