"""Tests for backend/users-service/function.py.

Drives the real handler() end to end — routing, ADMIN-only RBAC, validation,
password hashing, the last-admin / self-delete / managed-reference guards, and
HTTP status mapping — with only repository.py's database calls replaced by
controllable doubles. hash_password runs for real (it is pure stdlib), so the
"password in, hash out, password never echoed" contract is exercised, not
mocked.
"""

import json
import uuid
from unittest.mock import MagicMock

import pytest

USER_ID = str(uuid.uuid4())
DEPARTMENT_ID = str(uuid.uuid4())

VALID_USER_ROW = {
    "id": USER_ID,
    "email": "grace@example.com",
    "full_name": "Grace Hopper",
    "role": "CONTRIBUTOR",
    "is_active": True,
    "department_id": DEPARTMENT_ID,
    "department_name": "Engineering",
    "last_login_at": None,
    "created_at": "2026-01-01T00:00:00+00:00",
}

VALID_PAYLOAD = {
    "email": "new.person@example.com",
    "full_name": "New Person",
    "password": "sup3rsecret",
}


@pytest.fixture
def users(load_service):
    return load_service("users-service")


@pytest.fixture
def mock_repo(users, monkeypatch):
    repo = users.repository
    mocks = {
        "list_users": MagicMock(return_value=([VALID_USER_ROW], {"total": 1, "limit": 50, "offset": 0})),
        "get_user": MagicMock(return_value=VALID_USER_ROW),
        "email_taken": MagicMock(return_value=False),
        "other_active_admins": MagicMock(return_value=1),
        "managed_reference_counts": MagicMock(return_value={"teams": 0, "projects": 0}),
        "create_user": MagicMock(return_value=VALID_USER_ROW),
        "update_user": MagicMock(return_value=VALID_USER_ROW),
        "delete_user": MagicMock(return_value={"id": USER_ID}),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(repo, name, mock)

    exists_mock = MagicMock(return_value=True)
    monkeypatch.setattr(users.function, "exists", exists_mock)
    mocks["exists"] = exists_mock
    return mocks


class TestRBAC:
    @pytest.mark.parametrize(
        "method,path,body",
        [
            ("GET", "/api/users-service", None),
            ("POST", "/api/users-service", VALID_PAYLOAD),
            ("PUT", f"/api/users-service/{USER_ID}", {"full_name": "Renamed"}),
            ("DELETE", f"/api/users-service/{USER_ID}", None),
        ],
    )
    @pytest.mark.parametrize("role", ["VIEWER", "CONTRIBUTOR", "MANAGER"])
    def test_non_admins_are_forbidden(self, users, make_event, make_token, mock_repo, method, path, body, role):
        event = make_event(method, path, body=body, token=make_token(role))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 403

    def test_admin_can_list(self, users, make_event, make_token, mock_repo):
        event = make_event("GET", "/api/users-service", token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 200
        assert json.loads(result["body"])["meta"]["total"] == 1

    def test_options_bypasses_auth(self, users, make_event):
        result = users.function.handler(make_event("OPTIONS", "/api/users-service"), {})
        assert result["statusCode"] == 204

    def test_missing_token_returns_401(self, users, make_event):
        result = users.function.handler(make_event("GET", "/api/users-service"), {})
        assert result["statusCode"] == 401


class TestCreate:
    def test_create_returns_201(self, users, make_event, make_token, mock_repo):
        event = make_event("POST", "/api/users-service", body=VALID_PAYLOAD, token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 201, result["body"]

    def test_password_is_hashed_and_never_persisted_raw(self, users, make_event, make_token, mock_repo):
        event = make_event("POST", "/api/users-service", body=VALID_PAYLOAD, token=make_token("ADMIN"))
        users.function.handler(event, {})
        persisted = mock_repo["create_user"].call_args[0][0]
        assert "password" not in persisted
        assert persisted["password_hash"].startswith("pbkdf2_sha256$")
        assert VALID_PAYLOAD["password"] not in persisted["password_hash"]

    def test_password_is_never_echoed_back(self, users, make_event, make_token, mock_repo):
        event = make_event("POST", "/api/users-service", body=VALID_PAYLOAD, token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        body = result["body"]
        assert "password" not in json.loads(body)["data"]
        assert "password_hash" not in body

    def test_duplicate_email_returns_400(self, users, make_event, make_token, mock_repo):
        mock_repo["email_taken"].return_value = True
        event = make_event("POST", "/api/users-service", body=VALID_PAYLOAD, token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["error"]["details"]["email"] == "is already used by another user"
        mock_repo["create_user"].assert_not_called()

    def test_unknown_department_returns_400(self, users, make_event, make_token, mock_repo):
        mock_repo["exists"].return_value = False
        body = {**VALID_PAYLOAD, "department_id": DEPARTMENT_ID}
        event = make_event("POST", "/api/users-service", body=body, token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["error"]["details"]["department_id"] == "no department exists with this id"

    def test_missing_required_fields_returns_400(self, users, make_event, make_token, mock_repo):
        event = make_event("POST", "/api/users-service", body={}, token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 400
        assert set(json.loads(result["body"])["error"]["details"]) == {"email", "full_name", "password"}

    def test_short_password_returns_400(self, users, make_event, make_token, mock_repo):
        body = {**VALID_PAYLOAD, "password": "short"}
        event = make_event("POST", "/api/users-service", body=body, token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 400

    def test_invalid_role_returns_400(self, users, make_event, make_token, mock_repo):
        body = {**VALID_PAYLOAD, "role": "SUPERUSER"}
        event = make_event("POST", "/api/users-service", body=body, token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 400


class TestUpdate:
    def test_partial_update_returns_200(self, users, make_event, make_token, mock_repo):
        event = make_event("PUT", f"/api/users-service/{USER_ID}", body={"full_name": "Renamed"}, token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 200

    def test_password_change_is_hashed(self, users, make_event, make_token, mock_repo):
        event = make_event("PUT", f"/api/users-service/{USER_ID}", body={"password": "brandnewpass"}, token=make_token("ADMIN"))
        users.function.handler(event, {})
        persisted = mock_repo["update_user"].call_args[0][1]
        assert "password" not in persisted
        assert persisted["password_hash"].startswith("pbkdf2_sha256$")

    def test_missing_user_returns_404(self, users, make_event, make_token, mock_repo):
        mock_repo["get_user"].return_value = None
        event = make_event("PUT", f"/api/users-service/{uuid.uuid4()}", body={"full_name": "X"}, token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 404

    def test_demoting_the_last_active_admin_is_blocked(self, users, make_event, make_token, mock_repo):
        mock_repo["get_user"].return_value = {**VALID_USER_ROW, "role": "ADMIN", "is_active": True}
        mock_repo["other_active_admins"].return_value = 0
        event = make_event("PUT", f"/api/users-service/{USER_ID}", body={"role": "VIEWER"}, token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 409
        mock_repo["update_user"].assert_not_called()

    def test_deactivating_the_last_active_admin_is_blocked(self, users, make_event, make_token, mock_repo):
        mock_repo["get_user"].return_value = {**VALID_USER_ROW, "role": "ADMIN", "is_active": True}
        mock_repo["other_active_admins"].return_value = 0
        event = make_event("PUT", f"/api/users-service/{USER_ID}", body={"is_active": False}, token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 409

    def test_demoting_an_admin_when_others_exist_is_allowed(self, users, make_event, make_token, mock_repo):
        mock_repo["get_user"].return_value = {**VALID_USER_ROW, "role": "ADMIN", "is_active": True}
        mock_repo["other_active_admins"].return_value = 2
        event = make_event("PUT", f"/api/users-service/{USER_ID}", body={"role": "MANAGER"}, token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 200


class TestDelete:
    def test_delete_returns_204(self, users, make_event, make_token, mock_repo):
        event = make_event("DELETE", f"/api/users-service/{USER_ID}", token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 204
        mock_repo["delete_user"].assert_called_once_with(USER_ID)

    def test_cannot_delete_own_account(self, users, make_event, make_token, mock_repo):
        # make_token defaults sub to a fixed id; align the target with it.
        caller_id = "11111111-1111-1111-1111-111111111111"
        mock_repo["get_user"].return_value = {**VALID_USER_ROW, "id": caller_id}
        event = make_event("DELETE", f"/api/users-service/{caller_id}", token=make_token("ADMIN", user_id=caller_id))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 409
        mock_repo["delete_user"].assert_not_called()

    def test_cannot_delete_last_active_admin(self, users, make_event, make_token, mock_repo):
        mock_repo["get_user"].return_value = {**VALID_USER_ROW, "role": "ADMIN", "is_active": True}
        mock_repo["other_active_admins"].return_value = 0
        event = make_event("DELETE", f"/api/users-service/{USER_ID}", token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 409

    def test_cannot_delete_user_managing_teams_or_projects(self, users, make_event, make_token, mock_repo):
        mock_repo["managed_reference_counts"].return_value = {"teams": 2, "projects": 1}
        event = make_event("DELETE", f"/api/users-service/{USER_ID}", token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 409
        details = json.loads(result["body"])["error"]["details"]
        assert details["teams"] == 2 and details["projects"] == 1
        mock_repo["delete_user"].assert_not_called()

    def test_delete_missing_user_returns_404(self, users, make_event, make_token, mock_repo):
        mock_repo["get_user"].return_value = None
        event = make_event("DELETE", f"/api/users-service/{uuid.uuid4()}", token=make_token("ADMIN"))
        result = users.function.handler(event, {})
        assert result["statusCode"] == 404


class TestRoutingEdges:
    def test_get_user_by_id_returns_200(self, users, make_event, make_token, mock_repo):
        event = make_event("GET", f"/api/users-service/{USER_ID}", token=make_token("ADMIN"))
        assert users.function.handler(event, {})["statusCode"] == 200

    def test_get_missing_user_by_id_returns_404(self, users, make_event, make_token, mock_repo):
        mock_repo["get_user"].return_value = None
        event = make_event("GET", f"/api/users-service/{uuid.uuid4()}", token=make_token("ADMIN"))
        assert users.function.handler(event, {})["statusCode"] == 404

    def test_put_without_id_returns_400(self, users, make_event, make_token, mock_repo):
        event = make_event("PUT", "/api/users-service", body={"full_name": "X"}, token=make_token("ADMIN"))
        assert users.function.handler(event, {})["statusCode"] == 400

    def test_delete_without_id_returns_400(self, users, make_event, make_token, mock_repo):
        event = make_event("DELETE", "/api/users-service", token=make_token("ADMIN"))
        assert users.function.handler(event, {})["statusCode"] == 400

    def test_unsupported_method_returns_405(self, users, make_event, make_token, mock_repo):
        event = make_event("PATCH", "/api/users-service", token=make_token("ADMIN"))
        assert users.function.handler(event, {})["statusCode"] == 405
