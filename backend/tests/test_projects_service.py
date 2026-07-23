"""Tests for backend/projects-service/function.py.

Drives the real handler() end to end — routing, auth, RBAC, validation,
business rules, HTTP status mapping — with only repository.py's database
calls replaced by controllable doubles. Weighted toward the cross-field
COMPLETED/actual_end business rules, since that's this service's most
distinctive logic; RBAC/CRUD/validation follow the same shape already
proven out in test_teams_service.py (PERMISSIONS is identical).
"""

import json
import uuid
from unittest.mock import MagicMock

import pytest

PROJECT_ID = str(uuid.uuid4())
DEPARTMENT_ID = str(uuid.uuid4())
MANAGER_ID = str(uuid.uuid4())

VALID_PROJECT_ROW = {
    "id": PROJECT_ID,
    "code": "PR03",
    "name": "Expense Tracker",
    "description": None,
    "department_id": DEPARTMENT_ID,
    "manager_id": MANAGER_ID,
    "status": "PLANNING",
    "priority": "MEDIUM",
    "start_date": "2027-01-01",
    "planned_end": "2027-06-30",
    "actual_end": None,
    "planned_budget": 0,
    "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00",
    "manager_name": "Ada Lovelace",
    "department_name": "Engineering",
    "deliverable_count": 0,
    "deliverables_completed": 0,
}

VALID_PAYLOAD = {
    "code": "PR04",
    "name": "New Project",
    "department_id": DEPARTMENT_ID,
    "manager_id": MANAGER_ID,
    "start_date": "2027-01-01",
    "planned_end": "2027-06-30",
}


@pytest.fixture
def projects(load_service):
    return load_service("projects-service")


@pytest.fixture
def mock_repo(projects, monkeypatch):
    repo = projects.repository
    mocks = {
        "list_projects": MagicMock(return_value=([VALID_PROJECT_ROW], {"total": 1, "limit": 50, "offset": 0})),
        "get_project": MagicMock(return_value=VALID_PROJECT_ROW),
        "code_taken": MagicMock(return_value=False),
        "create_project": MagicMock(return_value={"id": PROJECT_ID}),
        "update_project": MagicMock(return_value={"id": PROJECT_ID}),
        "delete_project": MagicMock(return_value={"id": PROJECT_ID}),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(repo, name, mock)

    exists_mock = MagicMock(return_value=True)
    monkeypatch.setattr(projects.function, "exists", exists_mock)
    mocks["exists"] = exists_mock
    return mocks


class TestCompletedRequiresActualEnd:
    """The cross-field rule in schema.check_business_rules: a project can't
    be marked COMPLETED without an actual_end, and setting actual_end
    forces status to COMPLETED or CANCELLED."""

    def test_completed_without_actual_end_returns_400(self, projects, make_event, make_token, mock_repo):
        body = {**VALID_PAYLOAD, "status": "COMPLETED"}
        event = make_event("POST", "/api/projects-service", body=body, token=make_token("MANAGER"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 400
        details = json.loads(result["body"])["error"]["details"]
        assert details["actual_end"] == "is required when a project is marked completed"
        mock_repo["create_project"].assert_not_called()

    def test_completed_with_actual_end_succeeds(self, projects, make_event, make_token, mock_repo):
        body = {**VALID_PAYLOAD, "status": "COMPLETED", "actual_end": "2027-05-01"}
        event = make_event("POST", "/api/projects-service", body=body, token=make_token("MANAGER"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 201, result["body"]

    def test_actual_end_without_completed_or_cancelled_status_returns_400(
        self, projects, make_event, make_token, mock_repo
    ):
        body = {**VALID_PAYLOAD, "status": "ACTIVE", "actual_end": "2027-05-01"}
        event = make_event("POST", "/api/projects-service", body=body, token=make_token("MANAGER"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 400
        details = json.loads(result["body"])["error"]["details"]
        assert details["status"] == "must be COMPLETED or CANCELLED when an end date is set"

    def test_actual_end_with_cancelled_status_is_allowed(self, projects, make_event, make_token, mock_repo):
        body = {**VALID_PAYLOAD, "status": "CANCELLED", "actual_end": "2027-05-01"}
        event = make_event("POST", "/api/projects-service", body=body, token=make_token("MANAGER"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 201, result["body"]

    def test_planned_end_before_start_date_returns_400(self, projects, make_event, make_token, mock_repo):
        body = {**VALID_PAYLOAD, "start_date": "2027-06-01", "planned_end": "2027-01-01"}
        event = make_event("POST", "/api/projects-service", body=body, token=make_token("MANAGER"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 400
        details = json.loads(result["body"])["error"]["details"]
        assert details["planned_end"] == "must be on or after the start date"

    def test_actual_end_before_start_date_returns_400(self, projects, make_event, make_token, mock_repo):
        body = {**VALID_PAYLOAD, "status": "COMPLETED", "actual_end": "2026-01-01"}
        event = make_event("POST", "/api/projects-service", body=body, token=make_token("MANAGER"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 400
        details = json.loads(result["body"])["error"]["details"]
        assert details["actual_end"] == "must be on or after the start date"

    def test_partial_update_checks_rule_against_existing_row(self, projects, make_event, make_token, mock_repo):
        """Marking an existing (in-progress, no actual_end) project COMPLETED
        via a partial PUT must still trigger the rule, using the existing
        row's fields merged with the partial payload."""
        event = make_event(
            "PUT", f"/api/projects-service/{PROJECT_ID}", body={"status": "COMPLETED"}, token=make_token("CONTRIBUTOR")
        )
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 400
        details = json.loads(result["body"])["error"]["details"]
        assert details["actual_end"] == "is required when a project is marked completed"
        mock_repo["update_project"].assert_not_called()


class TestDeleteBlockedByLinkedRecords:
    """delete_project's blocker check lives in repository.py (see
    test_projects_repository.py for the real logic); here we only confirm
    function.py propagates the resulting 409 correctly."""

    def test_delete_blocked_returns_409(self, projects, make_event, make_token, mock_repo):
        mock_repo["delete_project"].side_effect = projects.http.ConflictError(
            "Project still has linked records and cannot be deleted",
            details={"deliverables": 2, "allocations": 0, "hint": "Set status to CANCELLED, or remove the linked records first"},
        )
        event = make_event("DELETE", f"/api/projects-service/{PROJECT_ID}", token=make_token("ADMIN"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 409
        payload = json.loads(result["body"])
        assert payload["error"]["details"]["deliverables"] == 2


class TestRBAC:
    """Identical PERMISSIONS shape to teams-service: GET open to all,
    POST requires Manager/Admin, PUT requires Contributor+, DELETE Admin
    only."""

    @pytest.mark.parametrize("role", ["VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"])
    def test_get_allowed_for_every_role(self, projects, make_event, make_token, mock_repo, role):
        event = make_event("GET", "/api/projects-service", token=make_token(role))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 200

    @pytest.mark.parametrize(
        "role,expected_status",
        [("VIEWER", 403), ("CONTRIBUTOR", 403), ("MANAGER", 201), ("ADMIN", 201)],
    )
    def test_post_requires_manager_or_admin(self, projects, make_event, make_token, mock_repo, role, expected_status):
        event = make_event("POST", "/api/projects-service", body=VALID_PAYLOAD, token=make_token(role))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == expected_status

    @pytest.mark.parametrize(
        "role,expected_status",
        [("VIEWER", 403), ("CONTRIBUTOR", 200), ("MANAGER", 200), ("ADMIN", 200)],
    )
    def test_put_requires_contributor_or_above(self, projects, make_event, make_token, mock_repo, role, expected_status):
        event = make_event(
            "PUT", f"/api/projects-service/{PROJECT_ID}", body={"name": "Renamed"}, token=make_token(role)
        )
        result = projects.function.handler(event, {})
        assert result["statusCode"] == expected_status

    @pytest.mark.parametrize(
        "role,expected_status",
        [("VIEWER", 403), ("CONTRIBUTOR", 403), ("MANAGER", 204), ("ADMIN", 204)],
    )
    def test_delete_requires_manager_or_above(self, projects, make_event, make_token, mock_repo, role, expected_status):
        event = make_event("DELETE", f"/api/projects-service/{PROJECT_ID}", token=make_token(role))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == expected_status

    def test_missing_token_returns_401(self, projects, make_event):
        event = make_event("GET", "/api/projects-service")
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 401

    def test_options_bypasses_auth(self, projects, make_event):
        event = make_event("OPTIONS", "/api/projects-service")
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 204

    def test_unsupported_method_returns_405_before_rbac(self, projects, make_event, mock_repo):
        """Method support is checked before authorize(), so an unsupported
        verb is a 405 even with no token at all."""
        event = make_event("PATCH", "/api/projects-service")
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 405


class TestValidation:
    def test_missing_required_fields_returns_400(self, projects, make_event, make_token, mock_repo):
        event = make_event("POST", "/api/projects-service", body={}, token=make_token("ADMIN"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 400
        details = json.loads(result["body"])["error"]["details"]
        assert set(details) == {"code", "name", "department_id", "manager_id", "start_date", "planned_end"}

    def test_invalid_status_choice_returns_400(self, projects, make_event, make_token, mock_repo):
        body = {**VALID_PAYLOAD, "status": "PAUSED"}
        event = make_event("POST", "/api/projects-service", body=body, token=make_token("ADMIN"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 400

    def test_duplicate_code_returns_400(self, projects, make_event, make_token, mock_repo):
        mock_repo["code_taken"].return_value = True
        event = make_event("POST", "/api/projects-service", body=VALID_PAYLOAD, token=make_token("MANAGER"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["error"]["details"]["code"] == "is already used by another project"

    def test_unknown_manager_returns_400(self, projects, make_event, make_token, mock_repo):
        mock_repo["exists"].side_effect = lambda table, _id: table != "users"
        event = make_event("POST", "/api/projects-service", body=VALID_PAYLOAD, token=make_token("ADMIN"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["error"]["details"]["manager_id"] == "no user exists with this id"


class TestCrudSuccess:
    def test_list_projects_returns_200_with_meta(self, projects, make_event, make_token, mock_repo):
        event = make_event("GET", "/api/projects-service", token=make_token("VIEWER"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 200
        payload = json.loads(result["body"])
        assert payload["data"][0]["id"] == PROJECT_ID
        assert payload["meta"] == {"total": 1, "limit": 50, "offset": 0}

    def test_get_project_returns_200(self, projects, make_event, make_token, mock_repo):
        event = make_event("GET", f"/api/projects-service/{PROJECT_ID}", token=make_token("VIEWER"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 200

    def test_get_missing_project_returns_404(self, projects, make_event, make_token, mock_repo):
        mock_repo["get_project"].return_value = None
        event = make_event("GET", f"/api/projects-service/{uuid.uuid4()}", token=make_token("VIEWER"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 404

    def test_create_project_returns_201(self, projects, make_event, make_token, mock_repo):
        event = make_event("POST", "/api/projects-service", body=VALID_PAYLOAD, token=make_token("MANAGER"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 201
        mock_repo["create_project"].assert_called_once()

    def test_update_project_returns_200(self, projects, make_event, make_token, mock_repo):
        event = make_event(
            "PUT", f"/api/projects-service/{PROJECT_ID}", body={"name": "Renamed"}, token=make_token("CONTRIBUTOR")
        )
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 200
        mock_repo["update_project"].assert_called_once_with(PROJECT_ID, {"name": "Renamed"})

    def test_update_missing_project_returns_404(self, projects, make_event, make_token, mock_repo):
        mock_repo["get_project"].return_value = None
        event = make_event(
            "PUT", f"/api/projects-service/{uuid.uuid4()}", body={"name": "X"}, token=make_token("CONTRIBUTOR")
        )
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 404

    def test_delete_project_returns_204(self, projects, make_event, make_token, mock_repo):
        event = make_event("DELETE", f"/api/projects-service/{PROJECT_ID}", token=make_token("ADMIN"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 204
        mock_repo["delete_project"].assert_called_once_with(PROJECT_ID)

    def test_delete_missing_project_returns_404(self, projects, make_event, make_token, mock_repo):
        mock_repo["get_project"].return_value = None
        event = make_event("DELETE", f"/api/projects-service/{uuid.uuid4()}", token=make_token("ADMIN"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 404

    def test_put_without_id_returns_400(self, projects, make_event, make_token, mock_repo):
        event = make_event("PUT", "/api/projects-service", body={"name": "X"}, token=make_token("ADMIN"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 400

    def test_delete_without_id_returns_400(self, projects, make_event, make_token, mock_repo):
        event = make_event("DELETE", "/api/projects-service", token=make_token("ADMIN"))
        result = projects.function.handler(event, {})
        assert result["statusCode"] == 400
