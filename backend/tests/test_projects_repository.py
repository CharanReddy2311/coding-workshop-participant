"""Direct unit tests for backend/projects-service/repository.py.

test_projects_service.py mocks repository.py wholesale to test function.py's
HTTP contract; these tests exercise repository.py's own code for real —
most importantly delete_project's blocker check, which lives entirely in
this module and is otherwise untested (function.py just calls it and
propagates whatever it raises).
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def projects(load_service):
    return load_service("projects-service")


@pytest.fixture
def db(projects, monkeypatch):
    mocks = {
        "query_all": MagicMock(return_value=[]),
        "query_one": MagicMock(return_value=None),
        "execute": MagicMock(return_value={"id": "returned-id"}),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(projects.repository, name, mock)
    return mocks


class TestBuildFilters:
    def test_no_params_produces_no_where_clause(self, projects):
        where, values = projects.repository._build_filters({})
        assert where == ""
        assert values == []

    def test_status_priority_department_manager_filters(self, projects):
        where, values = projects.repository._build_filters(
            {"status": "ACTIVE", "priority": "HIGH", "department_id": "d1", "manager_id": "m1"}
        )
        for clause in ("p.status = %s", "p.priority = %s", "p.department_id = %s", "p.manager_id = %s"):
            assert clause in where
        assert values == ["ACTIVE", "HIGH", "d1", "m1"]

    def test_q_filter_targets_three_columns(self, projects):
        where, values = projects.repository._build_filters({"q": "tracker"})
        assert "p.name ILIKE %s" in where
        assert "p.code ILIKE %s" in where
        assert values == ["%tracker%", "%tracker%", "%tracker%"]

    def test_overdue_filter_adds_two_clauses(self, projects):
        where, values = projects.repository._build_filters({"overdue": "true"})
        assert "p.planned_end < CURRENT_DATE" in where
        assert "p.status NOT IN ('COMPLETED','CANCELLED')" in where
        assert values == []

    def test_date_range_filters(self, projects):
        where, values = projects.repository._build_filters(
            {"start_after": "2027-01-01", "end_before": "2027-12-31"}
        )
        assert "p.start_date >= %s" in where
        assert "p.planned_end <= %s" in where
        assert values == ["2027-01-01", "2027-12-31"]


class TestListProjects:
    def test_shapes_meta_from_count_query(self, projects, db):
        db["query_one"].return_value = {"count": 5}
        db["query_all"].return_value = [{"id": "p1"}]
        rows, meta = projects.repository.list_projects({"limit": "10"})
        assert rows == [{"id": "p1"}]
        assert meta == {"total": 5, "limit": 10, "offset": 0}

    def test_unknown_sort_falls_back_to_created_at(self, projects, db):
        db["query_one"].return_value = {"count": 0}
        projects.repository.list_projects({"sort": "malicious; DROP TABLE projects"})
        page_sql = db["query_all"].call_args[0][0]
        assert "ORDER BY p.created_at" in page_sql


class TestCodeTaken:
    def test_true_when_row_found(self, projects, db):
        db["query_one"].return_value = {"1": 1}
        assert projects.repository.code_taken("PR01") is True

    def test_exclude_id_adds_clause(self, projects, db):
        projects.repository.code_taken("PR01", exclude_id="p1")
        sql, params = db["query_one"].call_args[0]
        assert "id <> %s" in sql
        assert params == ("PR01", "p1")


class TestCreateProject:
    def test_builds_insert_from_data_keys(self, projects, db):
        data = {"code": "PR05", "name": "New Project"}
        projects.repository.create_project(data)
        sql, params = db["execute"].call_args[0]
        assert "INSERT INTO projects (code, name)" in sql
        assert params == ["PR05", "New Project"]

    def test_unique_violation_raises_conflict_error(self, projects, db):
        db["execute"].side_effect = Exception({"C": "23505"})
        with pytest.raises(projects.http.ConflictError):
            projects.repository.create_project({"code": "DUP"})


class TestUpdateProject:
    def test_builds_update_assignments(self, projects, db):
        projects.repository.update_project("p1", {"name": "Renamed"})
        sql, params = db["execute"].call_args[0]
        assert "UPDATE projects SET name = %s, updated_at = now()" in sql
        assert params == ["Renamed", "p1"]

    def test_unique_violation_raises_conflict_error(self, projects, db):
        db["execute"].side_effect = Exception({"C": "23505"})
        with pytest.raises(projects.http.ConflictError):
            projects.repository.update_project("p1", {"code": "DUP"})


class TestDeleteProjectBlockerCheck:
    """The actual business rule: a project with any linked deliverables or
    allocations refuses to delete, cascading them away silently would
    destroy history a project manager needs."""

    def test_deletes_when_no_linked_records(self, projects, db):
        db["query_one"].return_value = {"deliverables": 0, "allocations": 0}
        projects.repository.delete_project("p1")
        db["execute"].assert_called_once()
        sql, params = db["execute"].call_args[0]
        assert "DELETE FROM projects WHERE id = %s" in sql
        assert params == ("p1",)

    def test_blocked_by_deliverables_raises_conflict_with_counts(self, projects, db):
        db["query_one"].return_value = {"deliverables": 3, "allocations": 0}
        with pytest.raises(projects.http.ConflictError) as excinfo:
            projects.repository.delete_project("p1")
        assert excinfo.value.details["deliverables"] == 3
        assert excinfo.value.details["allocations"] == 0
        assert "hint" in excinfo.value.details
        db["execute"].assert_not_called()

    def test_blocked_by_allocations_raises_conflict(self, projects, db):
        db["query_one"].return_value = {"deliverables": 0, "allocations": 2}
        with pytest.raises(projects.http.ConflictError):
            projects.repository.delete_project("p1")
        db["execute"].assert_not_called()

    def test_blocked_by_both_raises_conflict_with_both_counts(self, projects, db):
        db["query_one"].return_value = {"deliverables": 1, "allocations": 4}
        with pytest.raises(projects.http.ConflictError) as excinfo:
            projects.repository.delete_project("p1")
        assert excinfo.value.details == {
            "deliverables": 1,
            "allocations": 4,
            "hint": "Set status to CANCELLED, or remove the linked records first",
        }
