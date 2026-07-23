"""Tests for backend/deliverables-service/function.py.

Drives the real handler() end to end — routing, auth, RBAC, validation,
business rules, HTTP status mapping, and the /dependencies sub-resource —
with only repository.py's database calls replaced by controllable doubles.
Weighted toward the dependency-graph cycle-detection contract, since that's
this service's most distinctive logic.
"""

import json
import uuid
from unittest.mock import MagicMock

import pytest

DELIVERABLE_ID = str(uuid.uuid4())
OTHER_DELIVERABLE_ID = str(uuid.uuid4())
PROJECT_ID = str(uuid.uuid4())
OWNER_ID = str(uuid.uuid4())

VALID_DELIVERABLE_ROW = {
    "id": DELIVERABLE_ID,
    "project_id": PROJECT_ID,
    "owner_id": OWNER_ID,
    "name": "Design mockups",
    "description": None,
    "status": "NOT_STARTED",
    "percent_complete": 0,
    "weight": 1.0,
    "due_date": "2027-08-15",
    "completed_at": None,
    "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00",
    "project_name": "Expense Tracker",
    "project_code": "PR03",
    "owner_name": "Ada Lovelace",
}

VALID_PAYLOAD = {"project_id": PROJECT_ID, "name": "New Deliverable", "due_date": "2027-09-01"}

DEPENDENCIES_RESULT = {"predecessors": [], "successors": []}


@pytest.fixture
def deliverables(load_service):
    return load_service("deliverables-service")


@pytest.fixture
def mock_repo(deliverables, monkeypatch):
    repo = deliverables.repository
    mocks = {
        "list_deliverables": MagicMock(return_value=([VALID_DELIVERABLE_ROW], {"total": 1, "limit": 50, "offset": 0})),
        "get_deliverable": MagicMock(return_value=VALID_DELIVERABLE_ROW),
        "create_deliverable": MagicMock(return_value={"id": DELIVERABLE_ID}),
        "update_deliverable": MagicMock(return_value={"id": DELIVERABLE_ID}),
        "delete_deliverable": MagicMock(return_value={"id": DELIVERABLE_ID}),
        "list_dependencies": MagicMock(return_value=DEPENDENCIES_RESULT),
        "would_create_cycle": MagicMock(return_value=False),
        "add_dependency": MagicMock(return_value={"predecessor_id": OTHER_DELIVERABLE_ID}),
        "remove_dependency": MagicMock(return_value={"predecessor_id": OTHER_DELIVERABLE_ID}),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(repo, name, mock)

    exists_mock = MagicMock(return_value=True)
    monkeypatch.setattr(deliverables.function, "exists", exists_mock)
    mocks["exists"] = exists_mock
    return mocks


class TestCompletedRequiresCompletedAt:
    def test_completed_without_completed_at_returns_400(self, deliverables, make_event, make_token, mock_repo):
        body = {**VALID_PAYLOAD, "status": "COMPLETED"}
        event = make_event("POST", "/api/deliverables-service", body=body, token=make_token("CONTRIBUTOR"))
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 400
        details = json.loads(result["body"])["error"]["details"]
        assert details["completed_at"] == "is required when a deliverable is marked completed"

    def test_completed_with_completed_at_succeeds(self, deliverables, make_event, make_token, mock_repo):
        body = {**VALID_PAYLOAD, "status": "COMPLETED", "completed_at": "2027-08-20"}
        event = make_event("POST", "/api/deliverables-service", body=body, token=make_token("CONTRIBUTOR"))
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 201, result["body"]

    def test_completed_at_without_terminal_status_returns_400(self, deliverables, make_event, make_token, mock_repo):
        body = {**VALID_PAYLOAD, "status": "IN_PROGRESS", "completed_at": "2027-08-20"}
        event = make_event("POST", "/api/deliverables-service", body=body, token=make_token("CONTRIBUTOR"))
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 400
        details = json.loads(result["body"])["error"]["details"]
        assert details["status"] == "must be COMPLETED or CANCELLED when completed_at is set"


class TestDependencyGraph:
    def test_list_dependencies_returns_200(self, deliverables, make_event, make_token, mock_repo):
        event = make_event(
            "GET", f"/api/deliverables-service/{DELIVERABLE_ID}/dependencies", token=make_token("VIEWER")
        )
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 200
        assert json.loads(result["body"])["data"] == DEPENDENCIES_RESULT

    def test_list_dependencies_for_missing_deliverable_returns_404(self, deliverables, make_event, make_token, mock_repo):
        mock_repo["get_deliverable"].return_value = None
        event = make_event(
            "GET", f"/api/deliverables-service/{uuid.uuid4()}/dependencies", token=make_token("VIEWER")
        )
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 404

    def test_add_dependency_returns_201(self, deliverables, make_event, make_token, mock_repo):
        body = {"predecessor_id": OTHER_DELIVERABLE_ID, "dep_type": "FINISH_TO_START"}
        event = make_event(
            "POST", f"/api/deliverables-service/{DELIVERABLE_ID}/dependencies", body=body, token=make_token("CONTRIBUTOR")
        )
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 201, result["body"]
        mock_repo["add_dependency"].assert_called_once_with(OTHER_DELIVERABLE_ID, DELIVERABLE_ID, "FINISH_TO_START")

    def test_add_dependency_defaults_dep_type_to_finish_to_start(self, deliverables, make_event, make_token, mock_repo):
        body = {"predecessor_id": OTHER_DELIVERABLE_ID}
        event = make_event(
            "POST", f"/api/deliverables-service/{DELIVERABLE_ID}/dependencies", body=body, token=make_token("CONTRIBUTOR")
        )
        deliverables.function.handler(event, {})
        mock_repo["add_dependency"].assert_called_once_with(OTHER_DELIVERABLE_ID, DELIVERABLE_ID, "FINISH_TO_START")

    def test_self_dependency_returns_400(self, deliverables, make_event, make_token, mock_repo):
        body = {"predecessor_id": DELIVERABLE_ID}
        event = make_event(
            "POST", f"/api/deliverables-service/{DELIVERABLE_ID}/dependencies", body=body, token=make_token("CONTRIBUTOR")
        )
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 400
        details = json.loads(result["body"])["error"]["details"]
        assert details["predecessor_id"] == "a deliverable cannot depend on itself"
        mock_repo["would_create_cycle"].assert_not_called()
        mock_repo["add_dependency"].assert_not_called()

    def test_unknown_predecessor_returns_400(self, deliverables, make_event, make_token, mock_repo):
        mock_repo["exists"].return_value = False
        body = {"predecessor_id": str(uuid.uuid4())}
        event = make_event(
            "POST", f"/api/deliverables-service/{DELIVERABLE_ID}/dependencies", body=body, token=make_token("CONTRIBUTOR")
        )
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 400
        details = json.loads(result["body"])["error"]["details"]
        assert details["predecessor_id"] == "no deliverable exists with this id"
        mock_repo["would_create_cycle"].assert_not_called()

    def test_cycle_returns_409_and_does_not_write(self, deliverables, make_event, make_token, mock_repo):
        """The exact scenario verified live in Phase 5: D1 -> D2 already
        exists; proposing D2 -> D1 must be rejected as a cycle."""
        mock_repo["would_create_cycle"].return_value = True
        body = {"predecessor_id": OTHER_DELIVERABLE_ID}
        event = make_event(
            "POST", f"/api/deliverables-service/{DELIVERABLE_ID}/dependencies", body=body, token=make_token("CONTRIBUTOR")
        )
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 409
        payload = json.loads(result["body"])
        assert payload["error"]["code"] == "conflict"
        assert payload["error"]["details"] == {
            "predecessor_id": OTHER_DELIVERABLE_ID,
            "successor_id": DELIVERABLE_ID,
        }
        mock_repo["add_dependency"].assert_not_called()

    def test_would_create_cycle_called_with_proposed_edge_direction(self, deliverables, make_event, make_token, mock_repo):
        body = {"predecessor_id": OTHER_DELIVERABLE_ID}
        event = make_event(
            "POST", f"/api/deliverables-service/{DELIVERABLE_ID}/dependencies", body=body, token=make_token("CONTRIBUTOR")
        )
        deliverables.function.handler(event, {})
        mock_repo["would_create_cycle"].assert_called_once_with(OTHER_DELIVERABLE_ID, DELIVERABLE_ID)

    def test_add_dependency_for_missing_deliverable_returns_404(self, deliverables, make_event, make_token, mock_repo):
        mock_repo["get_deliverable"].return_value = None
        body = {"predecessor_id": OTHER_DELIVERABLE_ID}
        event = make_event(
            "POST", f"/api/deliverables-service/{uuid.uuid4()}/dependencies", body=body, token=make_token("CONTRIBUTOR")
        )
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 404

    def test_remove_dependency_returns_204(self, deliverables, make_event, make_token, mock_repo):
        # DELETE on /dependencies is checked against the same top-level
        # PERMISSIONS as the main resource, which requires ADMIN for DELETE
        # — not just Contributor, unlike POST/GET on this same sub-resource.
        event = make_event(
            "DELETE",
            f"/api/deliverables-service/{DELIVERABLE_ID}/dependencies/{OTHER_DELIVERABLE_ID}",
            token=make_token("ADMIN"),
        )
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 204
        mock_repo["remove_dependency"].assert_called_once_with(OTHER_DELIVERABLE_ID, DELIVERABLE_ID)

    def test_remove_dependency_without_predecessor_id_returns_400(self, deliverables, make_event, make_token, mock_repo):
        event = make_event(
            "DELETE", f"/api/deliverables-service/{DELIVERABLE_ID}/dependencies", token=make_token("ADMIN")
        )
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 400

    def test_unsupported_method_on_dependencies_returns_405(self, deliverables, make_event, make_token, mock_repo):
        event = make_event(
            "PUT", f"/api/deliverables-service/{DELIVERABLE_ID}/dependencies", token=make_token("ADMIN")
        )
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 405

    def test_dependency_endpoints_respect_the_same_rbac_as_the_main_resource(
        self, deliverables, make_event, make_token, mock_repo
    ):
        body = {"predecessor_id": OTHER_DELIVERABLE_ID}
        event = make_event(
            "POST", f"/api/deliverables-service/{DELIVERABLE_ID}/dependencies", body=body, token=make_token("VIEWER")
        )
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 403


class TestRBAC:
    @pytest.mark.parametrize("role", ["VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"])
    def test_get_allowed_for_every_role(self, deliverables, make_event, make_token, mock_repo, role):
        event = make_event("GET", "/api/deliverables-service", token=make_token(role))
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 200

    @pytest.mark.parametrize(
        "role,expected_status",
        [("VIEWER", 403), ("CONTRIBUTOR", 201), ("MANAGER", 201), ("ADMIN", 201)],
    )
    def test_post_requires_contributor_or_above(self, deliverables, make_event, make_token, mock_repo, role, expected_status):
        event = make_event("POST", "/api/deliverables-service", body=VALID_PAYLOAD, token=make_token(role))
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == expected_status

    @pytest.mark.parametrize(
        "role,expected_status",
        [("VIEWER", 403), ("CONTRIBUTOR", 403), ("MANAGER", 204), ("ADMIN", 204)],
    )
    def test_delete_requires_manager_or_above(self, deliverables, make_event, make_token, mock_repo, role, expected_status):
        event = make_event("DELETE", f"/api/deliverables-service/{DELIVERABLE_ID}", token=make_token(role))
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == expected_status

    def test_missing_token_returns_401(self, deliverables, make_event):
        event = make_event("GET", "/api/deliverables-service")
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 401

    def test_options_bypasses_auth(self, deliverables, make_event):
        event = make_event("OPTIONS", "/api/deliverables-service")
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 204

    def test_unsupported_method_returns_405(self, deliverables, make_event, make_token, mock_repo):
        event = make_event("PATCH", "/api/deliverables-service", token=make_token("ADMIN"))
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 405


class TestValidationAndReferences:
    def test_missing_required_fields_returns_400(self, deliverables, make_event, make_token, mock_repo):
        event = make_event("POST", "/api/deliverables-service", body={}, token=make_token("ADMIN"))
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 400
        details = json.loads(result["body"])["error"]["details"]
        assert set(details) == {"project_id", "name", "due_date"}

    def test_unknown_project_returns_400(self, deliverables, make_event, make_token, mock_repo):
        mock_repo["exists"].side_effect = lambda table, _id: table != "projects"
        event = make_event("POST", "/api/deliverables-service", body=VALID_PAYLOAD, token=make_token("ADMIN"))
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["error"]["details"]["project_id"] == "no project exists with this id"

    def test_owner_id_is_optional(self, deliverables, make_event, make_token, mock_repo):
        event = make_event("POST", "/api/deliverables-service", body=VALID_PAYLOAD, token=make_token("ADMIN"))
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 201

    def test_unknown_owner_returns_400(self, deliverables, make_event, make_token, mock_repo):
        mock_repo["exists"].side_effect = lambda table, _id: table != "users"
        body = {**VALID_PAYLOAD, "owner_id": str(uuid.uuid4())}
        event = make_event("POST", "/api/deliverables-service", body=body, token=make_token("ADMIN"))
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["error"]["details"]["owner_id"] == "no user exists with this id"


class TestCrudSuccess:
    def test_list_deliverables_returns_200_with_meta(self, deliverables, make_event, make_token, mock_repo):
        event = make_event("GET", "/api/deliverables-service", token=make_token("VIEWER"))
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 200
        payload = json.loads(result["body"])
        assert payload["meta"] == {"total": 1, "limit": 50, "offset": 0}

    def test_get_missing_deliverable_returns_404(self, deliverables, make_event, make_token, mock_repo):
        mock_repo["get_deliverable"].return_value = None
        event = make_event("GET", f"/api/deliverables-service/{uuid.uuid4()}", token=make_token("VIEWER"))
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 404

    def test_update_deliverable_returns_200(self, deliverables, make_event, make_token, mock_repo):
        event = make_event(
            "PUT", f"/api/deliverables-service/{DELIVERABLE_ID}", body={"percent_complete": 50}, token=make_token("CONTRIBUTOR")
        )
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 200
        mock_repo["update_deliverable"].assert_called_once_with(DELIVERABLE_ID, {"percent_complete": 50})

    def test_delete_deliverable_returns_204(self, deliverables, make_event, make_token, mock_repo):
        event = make_event("DELETE", f"/api/deliverables-service/{DELIVERABLE_ID}", token=make_token("ADMIN"))
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 204
        mock_repo["delete_deliverable"].assert_called_once_with(DELIVERABLE_ID)

    def test_delete_missing_deliverable_returns_404(self, deliverables, make_event, make_token, mock_repo):
        mock_repo["get_deliverable"].return_value = None
        event = make_event("DELETE", f"/api/deliverables-service/{uuid.uuid4()}", token=make_token("ADMIN"))
        result = deliverables.function.handler(event, {})
        assert result["statusCode"] == 404
