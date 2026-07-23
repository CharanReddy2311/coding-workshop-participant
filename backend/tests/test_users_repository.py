"""Direct unit tests for backend/users-service/repository.py.

test_users_service.py mocks repository.py wholesale to test function.py's HTTP
contract, so repository.py's own SQL never runs there. These tests close that
gap: only `_shared.db`'s query_all/query_one/execute are replaced, so every
real line of repository.py executes — filter building, the public-column
projection, the last-admin / managed-reference count queries, and the
unique-violation -> ConflictError mapping.
"""

from unittest.mock import MagicMock

import pytest

USER_ROW = {"id": "u1", "email": "grace@example.com", "full_name": "Grace Hopper", "role": "ADMIN"}


@pytest.fixture
def users(load_service):
    return load_service("users-service")


@pytest.fixture
def db(users, monkeypatch):
    mocks = {
        "query_all": MagicMock(return_value=[]),
        "query_one": MagicMock(return_value=USER_ROW),
        "execute": MagicMock(return_value={"id": "u1"}),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(users.repository, name, mock)
    return mocks


class TestBuildFilters:
    def test_no_params_produces_no_where_clause(self, users):
        where, values = users.repository._build_filters({})
        assert where == "" and values == []

    def test_role_and_department_filters(self, users):
        where, values = users.repository._build_filters({"role": "ADMIN", "department_id": "d1"})
        assert "u.role = %s" in where and "u.department_id = %s" in where
        assert values == ["ADMIN", "d1"]

    def test_search_matches_name_or_email(self, users):
        where, values = users.repository._build_filters({"q": "grace"})
        assert "u.full_name ILIKE %s OR u.email ILIKE %s" in where
        assert values == ["%grace%", "%grace%"]

    def test_is_active_filter_coerces_to_boolean(self, users):
        _, values = users.repository._build_filters({"is_active": "false"})
        assert values == [False]


class TestListUsers:
    def test_shapes_meta_and_omits_password_hash_columns(self, users, db):
        db["query_one"].return_value = {"count": 3}
        db["query_all"].return_value = [USER_ROW]
        rows, meta = users.repository.list_users({"limit": "10"})
        assert rows == [USER_ROW]
        assert meta == {"total": 3, "limit": 10, "offset": 0}
        page_sql = db["query_all"].call_args[0][0]
        assert "password_hash" not in page_sql

    def test_unknown_sort_falls_back_to_created_at(self, users, db):
        db["query_one"].return_value = {"count": 0}
        users.repository.list_users({"sort": "password_hash"})
        assert "ORDER BY u.created_at" in db["query_all"].call_args[0][0]


class TestLookups:
    def test_get_user_selects_public_columns_only(self, users, db):
        users.repository.get_user("u1")
        sql, params = db["query_one"].call_args[0]
        assert "password_hash" not in sql and params == ("u1",)

    def test_email_taken_without_exclude(self, users, db):
        db["query_one"].return_value = {"?": 1}
        assert users.repository.email_taken("a@b.com") is True
        sql, params = db["query_one"].call_args[0]
        assert "id <> %s" not in sql and params == ("a@b.com",)

    def test_email_taken_with_exclude(self, users, db):
        db["query_one"].return_value = None
        assert users.repository.email_taken("a@b.com", exclude_id="u9") is False
        sql, params = db["query_one"].call_args[0]
        assert "id <> %s" in sql and params == ("a@b.com", "u9")

    def test_other_active_admins_counts_active_admins_excluding_self(self, users, db):
        db["query_one"].return_value = {"count": 2}
        assert users.repository.other_active_admins("u1") == 2
        sql, params = db["query_one"].call_args[0]
        assert "role = 'ADMIN'" in sql and "is_active = true" in sql and params == ("u1",)

    def test_managed_reference_counts_queries_teams_and_projects(self, users, db):
        db["query_one"].return_value = {"teams": 1, "projects": 2}
        result = users.repository.managed_reference_counts("u1")
        assert result == {"teams": 1, "projects": 2}
        sql, params = db["query_one"].call_args[0]
        assert "FROM teams" in sql and "FROM projects" in sql and params == ("u1", "u1")


class TestWrites:
    def test_create_user_inserts_and_returns_public_row(self, users, db):
        data = {"email": "g@x.com", "full_name": "G", "password_hash": "h", "role": "VIEWER"}
        result = users.repository.create_user(data)
        assert result == USER_ROW  # re-read via get_user, no password_hash
        insert_sql, params = db["execute"].call_args[0]
        assert "INSERT INTO users" in insert_sql
        assert list(params) == ["g@x.com", "G", "h", "VIEWER"]

    def test_create_user_maps_unique_violation_to_conflict(self, users, monkeypatch):
        monkeypatch.setattr(users.repository, "execute", MagicMock(side_effect=Exception("dup")))
        monkeypatch.setattr(users.repository, "is_unique_violation", lambda exc: True)
        with pytest.raises(users.http.ConflictError):
            users.repository.create_user({"email": "g@x.com", "full_name": "G", "password_hash": "h"})

    def test_create_user_reraises_non_unique_errors(self, users, monkeypatch):
        monkeypatch.setattr(users.repository, "execute", MagicMock(side_effect=Exception("boom")))
        monkeypatch.setattr(users.repository, "is_unique_violation", lambda exc: False)
        with pytest.raises(Exception):
            users.repository.create_user({"email": "g@x.com", "full_name": "G", "password_hash": "h"})

    def test_update_user_builds_dynamic_set_and_returns_public_row(self, users, db):
        result = users.repository.update_user("u1", {"role": "MANAGER", "is_active": False})
        assert result == USER_ROW
        sql, params = db["execute"].call_args[0]
        assert "role = %s" in sql and "is_active = %s" in sql
        assert params == ["MANAGER", False, "u1"]

    def test_update_user_maps_unique_violation_to_conflict(self, users, monkeypatch):
        monkeypatch.setattr(users.repository, "execute", MagicMock(side_effect=Exception("dup")))
        monkeypatch.setattr(users.repository, "is_unique_violation", lambda exc: True)
        with pytest.raises(users.http.ConflictError):
            users.repository.update_user("u1", {"email": "g@x.com"})

    def test_delete_user_deletes_by_id(self, users, db):
        users.repository.delete_user("u1")
        sql, params = db["execute"].call_args[0]
        assert "DELETE FROM users WHERE id = %s" in sql and params == ("u1",)
