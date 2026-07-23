"""Direct unit tests for backend/teams-service/repository.py.

test_teams_service.py mocks repository.py wholesale to test function.py's
HTTP contract, which means repository.py's own code never actually runs
there. These tests close that gap: only `_shared.db`'s query_all/query_one/
execute are replaced, so every real line of repository.py — filter
building, pagination clamping, SQL assembly, conflict handling — executes
for real, still without touching Postgres.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def teams(load_service):
    return load_service("teams-service")


@pytest.fixture
def db(teams, monkeypatch):
    mocks = {
        "query_all": MagicMock(return_value=[]),
        "query_one": MagicMock(return_value=None),
        "execute": MagicMock(return_value={"id": "returned-id"}),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(teams.repository, name, mock)
    return mocks


class TestBuildFilters:
    def test_no_params_produces_no_where_clause(self, teams):
        where, values = teams.repository._build_filters({})
        assert where == ""
        assert values == []

    def test_department_and_manager_filters(self, teams):
        where, values = teams.repository._build_filters(
            {"department_id": "dept-1", "manager_id": "mgr-1"}
        )
        assert "t.department_id = %s" in where
        assert "t.manager_id = %s" in where
        assert values == ["dept-1", "mgr-1"]

    def test_q_filter_wraps_term_and_targets_two_columns(self, teams):
        where, values = teams.repository._build_filters({"q": "platform"})
        assert "ILIKE" in where
        assert values == ["%platform%", "%platform%"]

    def test_is_active_filter_coerces_string_to_boolean(self, teams):
        where, values = teams.repository._build_filters({"is_active": "true"})
        assert "t.is_active = %s" in where
        assert values == [True]

        where, values = teams.repository._build_filters({"is_active": "false"})
        assert values == [False]


class TestIntParam:
    def test_uses_default_when_absent(self, teams):
        assert teams.repository._int_param({}, "limit", 50, 1, 200) == 50

    def test_clamps_to_upper_bound(self, teams):
        assert teams.repository._int_param({"limit": "9999"}, "limit", 50, 1, 200) == 200

    def test_clamps_to_lower_bound(self, teams):
        assert teams.repository._int_param({"limit": "-5"}, "limit", 50, 1, 200) == 1

    def test_falls_back_to_default_on_garbage_input(self, teams):
        assert teams.repository._int_param({"limit": "not-a-number"}, "limit", 50, 1, 200) == 50


class TestListTeams:
    def test_runs_count_then_page_query_and_shapes_meta(self, teams, db):
        db["query_one"].return_value = {"count": 3}
        db["query_all"].return_value = [{"id": "t1"}, {"id": "t2"}]

        rows, meta = teams.repository.list_teams({"limit": "10", "offset": "0"})

        assert rows == [{"id": "t1"}, {"id": "t2"}]
        assert meta == {"total": 3, "limit": 10, "offset": 0}
        count_sql = db["query_one"].call_args[0][0]
        assert "COUNT(*)" in count_sql

    def test_unknown_sort_column_falls_back_to_created_at(self, teams, db):
        db["query_one"].return_value = {"count": 0}
        teams.repository.list_teams({"sort": "'; DROP TABLE teams; --"})
        page_sql = db["query_all"].call_args[0][0]
        assert "ORDER BY t.created_at" in page_sql

    def test_order_defaults_to_desc(self, teams, db):
        db["query_one"].return_value = {"count": 0}
        teams.repository.list_teams({})
        page_sql = db["query_all"].call_args[0][0]
        assert "DESC" in page_sql


class TestGetTeam:
    def test_queries_by_id(self, teams, db):
        db["query_one"].return_value = {"id": "t1"}
        result = teams.repository.get_team("t1")
        assert result == {"id": "t1"}
        sql, params = db["query_one"].call_args[0]
        assert "WHERE t.id = %s" in sql
        assert params == ("t1",)


class TestNameTaken:
    def test_true_when_a_row_is_found(self, teams, db):
        db["query_one"].return_value = {"1": 1}
        assert teams.repository.name_taken("Platform Engineering") is True

    def test_false_when_no_row_is_found(self, teams, db):
        db["query_one"].return_value = None
        assert teams.repository.name_taken("Platform Engineering") is False

    def test_exclude_id_adds_id_not_equal_clause(self, teams, db):
        teams.repository.name_taken("Platform Engineering", exclude_id="t1")
        sql, params = db["query_one"].call_args[0]
        assert "id <> %s" in sql
        assert params == ("Platform Engineering", "t1")


class TestCreateTeam:
    def test_builds_insert_from_data_keys(self, teams, db):
        data = {"name": "New Team", "department_id": "d1", "manager_id": "m1"}
        teams.repository.create_team(data)
        sql, params = db["execute"].call_args[0]
        assert "INSERT INTO teams (name, department_id, manager_id)" in sql
        assert "RETURNING id" in sql
        assert params == ["New Team", "d1", "m1"]

    def test_unique_violation_raises_conflict_error(self, teams, db):
        db["execute"].side_effect = Exception({"C": "23505"})
        with pytest.raises(teams.http.ConflictError):
            teams.repository.create_team({"name": "Dup"})

    def test_other_db_errors_propagate_unchanged(self, teams, db):
        db["execute"].side_effect = RuntimeError("connection reset")
        with pytest.raises(RuntimeError):
            teams.repository.create_team({"name": "X"})


class TestUpdateTeam:
    def test_builds_update_assignments_from_data_keys(self, teams, db):
        teams.repository.update_team("t1", {"name": "Renamed"})
        sql, params = db["execute"].call_args[0]
        assert "UPDATE teams SET name = %s, updated_at = now()" in sql
        assert "WHERE id = %s" in sql
        assert params == ["Renamed", "t1"]

    def test_unique_violation_raises_conflict_error(self, teams, db):
        db["execute"].side_effect = Exception({"C": "23505"})
        with pytest.raises(teams.http.ConflictError):
            teams.repository.update_team("t1", {"name": "Dup"})


class TestDeleteTeam:
    def test_deletes_by_id(self, teams, db):
        teams.repository.delete_team("t1")
        sql, params = db["execute"].call_args[0]
        assert "DELETE FROM teams WHERE id = %s" in sql
        assert params == ("t1",)
