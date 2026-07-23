"""Tests for backend/teams-service/function.py.

Drives the real handler() end to end for every request — routing, auth,
RBAC, validation, business rules, HTTP status mapping — with only
repository.py's database calls replaced by controllable doubles, so these
run without Postgres and produce the same result on any machine.
"""

import json
import uuid
from unittest.mock import MagicMock

import pytest

TEAM_ID = str(uuid.uuid4())
DEPARTMENT_ID = str(uuid.uuid4())
MANAGER_ID = str(uuid.uuid4())

VALID_TEAM_ROW = {
    "id": TEAM_ID,
    "name": "Platform Engineering",
    "description": None,
    "department_id": DEPARTMENT_ID,
    "manager_id": MANAGER_ID,
    "is_active": True,
    "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00",
    "department_name": "Engineering",
    "manager_name": "Ada Lovelace",
}

VALID_PAYLOAD = {"name": "New Team", "department_id": DEPARTMENT_ID, "manager_id": MANAGER_ID}


@pytest.fixture
def teams(load_service):
    return load_service("teams-service")


@pytest.fixture
def mock_repo(teams, monkeypatch):
    """Replace every repository.* function teams-service/function.py calls,
    plus the FK-existence check (`from _shared.db import exists`, called
    directly from function.py, not through repository)."""
    repo = teams.repository
    mocks = {
        "list_teams": MagicMock(return_value=([VALID_TEAM_ROW], {"total": 1, "limit": 50, "offset": 0})),
        "get_team": MagicMock(return_value=VALID_TEAM_ROW),
        "name_taken": MagicMock(return_value=False),
        "create_team": MagicMock(return_value={"id": TEAM_ID}),
        "update_team": MagicMock(return_value={"id": TEAM_ID}),
        "delete_team": MagicMock(return_value={"id": TEAM_ID}),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(repo, name, mock)

    exists_mock = MagicMock(return_value=True)
    monkeypatch.setattr(teams.function, "exists", exists_mock)
    mocks["exists"] = exists_mock
    return mocks


class TestAuthentication:
    def test_missing_token_returns_401(self, teams, make_event):
        event = make_event("GET", "/api/teams-service")
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 401

    def test_garbage_token_returns_401(self, teams, make_event):
        event = make_event("GET", "/api/teams-service", token="not-a-real-token")
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 401

    def test_options_bypasses_auth(self, teams, make_event):
        event = make_event("OPTIONS", "/api/teams-service")
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 204

    def test_unsupported_method_returns_405(self, teams, make_event, make_token):
        event = make_event("PATCH", "/api/teams-service", token=make_token("ADMIN"))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 405


class TestRBAC:
    """Matches PERMISSIONS in teams-service/function.py exactly: GET is open
    to every role, POST requires Manager or Admin, PUT requires Contributor
    or above, DELETE requires Admin."""

    @pytest.mark.parametrize("role", ["VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"])
    def test_get_allowed_for_every_role(self, teams, make_event, make_token, mock_repo, role):
        event = make_event("GET", "/api/teams-service", token=make_token(role))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 200

    @pytest.mark.parametrize(
        "role,expected_status",
        [("VIEWER", 403), ("CONTRIBUTOR", 403), ("MANAGER", 201), ("ADMIN", 201)],
    )
    def test_post_requires_manager_or_admin(self, teams, make_event, make_token, mock_repo, role, expected_status):
        event = make_event("POST", "/api/teams-service", body=VALID_PAYLOAD, token=make_token(role))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == expected_status

    @pytest.mark.parametrize(
        "role,expected_status",
        [("VIEWER", 403), ("CONTRIBUTOR", 200), ("MANAGER", 200), ("ADMIN", 200)],
    )
    def test_put_requires_contributor_or_above(self, teams, make_event, make_token, mock_repo, role, expected_status):
        event = make_event(
            "PUT", f"/api/teams-service/{TEAM_ID}", body={"name": "Renamed"}, token=make_token(role)
        )
        result = teams.function.handler(event, {})
        assert result["statusCode"] == expected_status

    @pytest.mark.parametrize(
        "role,expected_status",
        [("VIEWER", 403), ("CONTRIBUTOR", 403), ("MANAGER", 403), ("ADMIN", 204)],
    )
    def test_delete_requires_admin(self, teams, make_event, make_token, mock_repo, role, expected_status):
        event = make_event("DELETE", f"/api/teams-service/{TEAM_ID}", token=make_token(role))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == expected_status


class TestValidation:
    def test_create_missing_required_fields_returns_400(self, teams, make_event, make_token, mock_repo):
        event = make_event("POST", "/api/teams-service", body={}, token=make_token("ADMIN"))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert body["error"]["code"] == "validation_error"
        assert set(body["error"]["details"]) == {"name", "department_id", "manager_id"}

    def test_create_name_too_short_returns_400(self, teams, make_event, make_token, mock_repo):
        body = {"name": "A", "department_id": DEPARTMENT_ID, "manager_id": MANAGER_ID}
        event = make_event("POST", "/api/teams-service", body=body, token=make_token("ADMIN"))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 400

    def test_create_malformed_uuid_returns_400(self, teams, make_event, make_token, mock_repo):
        body = {"name": "Valid Name", "department_id": "not-a-uuid", "manager_id": MANAGER_ID}
        event = make_event("POST", "/api/teams-service", body=body, token=make_token("ADMIN"))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert "department_id" in body["error"]["details"]

    def test_create_unknown_department_returns_400(self, teams, make_event, make_token, mock_repo):
        mock_repo["exists"].side_effect = lambda table, _id: table != "departments"
        event = make_event("POST", "/api/teams-service", body=VALID_PAYLOAD, token=make_token("ADMIN"))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert body["error"]["details"]["department_id"] == "no department exists with this id"

    def test_create_duplicate_name_returns_400(self, teams, make_event, make_token, mock_repo):
        mock_repo["name_taken"].return_value = True
        event = make_event("POST", "/api/teams-service", body=VALID_PAYLOAD, token=make_token("MANAGER"))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 400
        body = json.loads(result["body"])
        assert body["error"]["details"]["name"] == "is already used by another team"

    def test_unknown_body_field_returns_400(self, teams, make_event, make_token, mock_repo):
        body = {**VALID_PAYLOAD, "not_a_real_field": "x"}
        event = make_event("POST", "/api/teams-service", body=body, token=make_token("ADMIN"))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 400

    def test_update_with_no_fields_returns_400(self, teams, make_event, make_token, mock_repo):
        event = make_event("PUT", f"/api/teams-service/{TEAM_ID}", body={}, token=make_token("ADMIN"))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 400


class TestCrudSuccess:
    def test_list_teams_returns_200_with_meta(self, teams, make_event, make_token, mock_repo):
        event = make_event("GET", "/api/teams-service", token=make_token("VIEWER"))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 200
        payload = json.loads(result["body"])
        assert payload["data"][0]["id"] == TEAM_ID
        assert payload["meta"] == {"total": 1, "limit": 50, "offset": 0}

    def test_get_team_returns_200(self, teams, make_event, make_token, mock_repo):
        event = make_event("GET", f"/api/teams-service/{TEAM_ID}", token=make_token("VIEWER"))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 200
        assert json.loads(result["body"])["data"]["id"] == TEAM_ID

    def test_get_missing_team_returns_404(self, teams, make_event, make_token, mock_repo):
        mock_repo["get_team"].return_value = None
        event = make_event("GET", f"/api/teams-service/{uuid.uuid4()}", token=make_token("VIEWER"))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 404

    def test_create_team_returns_201(self, teams, make_event, make_token, mock_repo):
        event = make_event("POST", "/api/teams-service", body=VALID_PAYLOAD, token=make_token("MANAGER"))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 201
        mock_repo["create_team"].assert_called_once()
        assert json.loads(result["body"])["data"]["id"] == TEAM_ID

    def test_update_team_returns_200(self, teams, make_event, make_token, mock_repo):
        event = make_event(
            "PUT", f"/api/teams-service/{TEAM_ID}", body={"name": "Renamed Team"}, token=make_token("CONTRIBUTOR")
        )
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 200
        mock_repo["update_team"].assert_called_once_with(TEAM_ID, {"name": "Renamed Team"})

    def test_update_missing_team_returns_404(self, teams, make_event, make_token, mock_repo):
        mock_repo["get_team"].return_value = None
        event = make_event(
            "PUT", f"/api/teams-service/{uuid.uuid4()}", body={"name": "X"}, token=make_token("CONTRIBUTOR")
        )
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 404
        mock_repo["update_team"].assert_not_called()

    def test_delete_team_returns_204(self, teams, make_event, make_token, mock_repo):
        event = make_event("DELETE", f"/api/teams-service/{TEAM_ID}", token=make_token("ADMIN"))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 204
        assert result["body"] == ""
        mock_repo["delete_team"].assert_called_once_with(TEAM_ID)

    def test_delete_missing_team_returns_404(self, teams, make_event, make_token, mock_repo):
        mock_repo["get_team"].return_value = None
        event = make_event("DELETE", f"/api/teams-service/{uuid.uuid4()}", token=make_token("ADMIN"))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 404
        mock_repo["delete_team"].assert_not_called()

    def test_put_without_id_returns_400(self, teams, make_event, make_token, mock_repo):
        event = make_event("PUT", "/api/teams-service", body={"name": "X"}, token=make_token("ADMIN"))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 400

    def test_delete_without_id_returns_400(self, teams, make_event, make_token, mock_repo):
        event = make_event("DELETE", "/api/teams-service", token=make_token("ADMIN"))
        result = teams.function.handler(event, {})
        assert result["statusCode"] == 400
