"""Tests for backend/directory-service — both function.py (HTTP contract)
and repository.py (the two read-only queries), combined in one file since
this service is small: two GET routes, no create/update/delete at all.

Notably different from every other service here: PERMISSIONS only defines
GET and OPTIONS, and there's no SUPPORTED_METHODS guard — a POST/PUT/DELETE
falls straight into authorize(), where permissions.get(method, ()) returns
an empty tuple, so *any* role is forbidden rather than the request being
flagged as an unsupported method.
"""

import json
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def directory(load_service):
    return load_service("directory-service")


@pytest.fixture
def mock_repo(directory, monkeypatch):
    mocks = {
        "list_departments": MagicMock(return_value=[{"id": "d1", "name": "Engineering"}]),
        "list_active_users": MagicMock(return_value=[{"id": "u1", "full_name": "Ada Lovelace", "email": "ada@example.com"}]),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(directory.repository, name, mock)
    return mocks


class TestRoutes:
    def test_get_departments_returns_200(self, directory, make_event, make_token, mock_repo):
        event = make_event("GET", "/api/directory-service/departments", token=make_token("VIEWER"))
        result = directory.function.handler(event, {})
        assert result["statusCode"] == 200
        assert json.loads(result["body"])["data"] == [{"id": "d1", "name": "Engineering"}]

    def test_get_users_returns_200(self, directory, make_event, make_token, mock_repo):
        event = make_event("GET", "/api/directory-service/users", token=make_token("VIEWER"))
        result = directory.function.handler(event, {})
        assert result["statusCode"] == 200
        assert json.loads(result["body"])["data"][0]["email"] == "ada@example.com"

    def test_unknown_resource_returns_404(self, directory, make_event, make_token, mock_repo):
        event = make_event("GET", "/api/directory-service/projects", token=make_token("VIEWER"))
        result = directory.function.handler(event, {})
        assert result["statusCode"] == 404
        payload = json.loads(result["body"])
        assert payload["error"]["code"] == "route_not_found"
        assert payload["error"]["details"]["available"] == ["GET /departments", "GET /users"]

    def test_collection_root_returns_404(self, directory, make_event, make_token, mock_repo):
        event = make_event("GET", "/api/directory-service", token=make_token("VIEWER"))
        result = directory.function.handler(event, {})
        assert result["statusCode"] == 404

    def test_options_bypasses_auth(self, directory, make_event):
        event = make_event("OPTIONS", "/api/directory-service")
        result = directory.function.handler(event, {})
        assert result["statusCode"] == 204


class TestAuth:
    def test_missing_token_returns_401(self, directory, make_event):
        event = make_event("GET", "/api/directory-service/departments")
        result = directory.function.handler(event, {})
        assert result["statusCode"] == 401

    @pytest.mark.parametrize("role", ["VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"])
    def test_every_role_can_read(self, directory, make_event, make_token, mock_repo, role):
        event = make_event("GET", "/api/directory-service/departments", token=make_token(role))
        result = directory.function.handler(event, {})
        assert result["statusCode"] == 200

    @pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH"])
    def test_any_write_method_is_forbidden_for_every_role(self, directory, make_event, make_token, mock_repo, method):
        """PERMISSIONS has no entry for these methods at all, so
        authorize()'s `permissions.get(method, ())` is always empty —
        forbidden regardless of role, not just for non-admins."""
        event = make_event(method, "/api/directory-service/departments", token=make_token("ADMIN"))
        result = directory.function.handler(event, {})
        assert result["statusCode"] == 403


class TestRepository:
    def test_list_departments_query_shape(self, directory, monkeypatch):
        query_all = MagicMock(return_value=[])
        monkeypatch.setattr(directory.repository, "query_all", query_all)
        directory.repository.list_departments()
        sql = query_all.call_args[0][0]
        assert "SELECT id, name FROM departments ORDER BY name" == sql

    def test_list_active_users_filters_and_orders(self, directory, monkeypatch):
        query_all = MagicMock(return_value=[])
        monkeypatch.setattr(directory.repository, "query_all", query_all)
        directory.repository.list_active_users()
        sql = query_all.call_args[0][0]
        assert "is_active = true" in sql
        assert "ORDER BY full_name" in sql
