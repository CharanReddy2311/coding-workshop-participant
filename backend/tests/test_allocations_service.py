"""Tests for backend/allocations-service/function.py.

Drives the real handler() end to end — routing, auth, RBAC, validation,
business rules, HTTP status mapping — with only repository.py's database
calls replaced by controllable doubles. Weighted heavily toward the
over-allocation boundary check and the update-path self-exclusion, since
that's this service's actual novel logic (see _check_overlap in
allocations-service/function.py) — everything else follows the same shape
already proven out in test_teams_service.py.
"""

import json
import uuid
from unittest.mock import MagicMock

import pytest

ALLOCATION_ID = str(uuid.uuid4())
USER_ID = str(uuid.uuid4())
PROJECT_ID = str(uuid.uuid4())

VALID_ALLOCATION_ROW = {
    "id": ALLOCATION_ID,
    "user_id": USER_ID,
    "project_id": PROJECT_ID,
    "role_on_project": "Engineer",
    "allocation_pct": 60,
    "created_at": "2026-01-01T00:00:00+00:00",
    "start_date": "2027-01-01",
    "end_date": "2027-06-30",
    "user_name": "Ada Lovelace",
    "user_email": "ada@example.com",
    "project_name": "Expense Tracker",
    "project_code": "PR03",
}

VALID_PAYLOAD = {
    "user_id": USER_ID,
    "project_id": PROJECT_ID,
    "allocation_pct": 40,
    "start_date": "2027-01-01",
    "end_date": "2027-06-30",
}


@pytest.fixture
def allocations(load_service):
    return load_service("allocations-service")


@pytest.fixture
def mock_repo(allocations, monkeypatch):
    repo = allocations.repository
    mocks = {
        "list_allocations": MagicMock(return_value=([VALID_ALLOCATION_ROW], {"total": 1, "limit": 50, "offset": 0})),
        "get_allocation": MagicMock(return_value=VALID_ALLOCATION_ROW),
        # No overlapping allocations by default — individual tests override
        # this to land on a specific boundary.
        "peak_existing_pct": MagicMock(return_value=0),
        "create_allocation": MagicMock(return_value={"id": ALLOCATION_ID}),
        "update_allocation": MagicMock(return_value={"id": ALLOCATION_ID}),
        "delete_allocation": MagicMock(return_value={"id": ALLOCATION_ID}),
    }
    for name, mock in mocks.items():
        monkeypatch.setattr(repo, name, mock)

    exists_mock = MagicMock(return_value=True)
    monkeypatch.setattr(allocations.function, "exists", exists_mock)
    mocks["exists"] = exists_mock
    return mocks


class TestOverAllocationBoundary:
    """Mirrors the exact scenarios verified live against real Postgres in
    Phase 5: the sum of overlapping allocation_pct may reach 100 but never
    exceed it — a strict `> 100` check, not `>= 100`."""

    @pytest.mark.parametrize(
        "existing_pct,requested_pct",
        [
            (0, 100),  # nothing existing, fully allocate — allowed
            (60, 40),  # exactly at the boundary — allowed
            (99, 1),  # exactly at the boundary — allowed
        ],
    )
    def test_at_or_under_100_percent_is_allowed(
        self, allocations, make_event, make_token, mock_repo, existing_pct, requested_pct
    ):
        mock_repo["peak_existing_pct"].return_value = existing_pct
        body = {**VALID_PAYLOAD, "allocation_pct": requested_pct}
        event = make_event("POST", "/api/allocations-service", body=body, token=make_token("MANAGER"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 201, result["body"]

    @pytest.mark.parametrize("existing_pct,requested_pct", [(60, 41), (100, 1), (50, 51)])
    def test_over_100_percent_is_rejected_with_409(
        self, allocations, make_event, make_token, mock_repo, existing_pct, requested_pct
    ):
        mock_repo["peak_existing_pct"].return_value = existing_pct
        body = {**VALID_PAYLOAD, "allocation_pct": requested_pct}
        event = make_event("POST", "/api/allocations-service", body=body, token=make_token("MANAGER"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 409
        mock_repo["create_allocation"].assert_not_called()

    def test_field_level_max_catches_a_single_over_100_allocation_first(
        self, allocations, make_event, make_token, mock_repo
    ):
        """allocation_pct=101 alone already fails Field(maximum=100) before
        the overlap check even runs — that's a 400, not a 409."""
        body = {**VALID_PAYLOAD, "allocation_pct": 101}
        event = make_event("POST", "/api/allocations-service", body=body, token=make_token("MANAGER"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 400
        mock_repo["peak_existing_pct"].assert_not_called()

    def test_conflict_response_reports_exact_numbers(self, allocations, make_event, make_token, mock_repo):
        mock_repo["peak_existing_pct"].return_value = 60
        body = {**VALID_PAYLOAD, "allocation_pct": 50}
        event = make_event("POST", "/api/allocations-service", body=body, token=make_token("MANAGER"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 409
        payload = json.loads(result["body"])
        assert payload["error"]["code"] == "conflict"
        assert payload["error"]["details"] == {
            "existing_pct": 60,
            "requested_pct": 50,
            "projected_pct": 110,
            "max_pct": 100,
        }


class TestUpdatePathExclusion:
    def test_create_does_not_exclude_any_row(self, allocations, make_event, make_token, mock_repo):
        event = make_event("POST", "/api/allocations-service", body=VALID_PAYLOAD, token=make_token("MANAGER"))
        allocations.function.handler(event, {})
        mock_repo["peak_existing_pct"].assert_called_once()
        assert mock_repo["peak_existing_pct"].call_args.kwargs.get("exclude_id") is None

    def test_update_excludes_its_own_row_from_the_overlap_sum(self, allocations, make_event, make_token, mock_repo):
        # Zero *other* overlapping allocations once this row's own prior
        # value is excluded. Without exclusion, saving the same allocation
        # back would double-count it against itself and could be wrongly
        # rejected as over 100%.
        mock_repo["peak_existing_pct"].return_value = 0
        event = make_event(
            "PUT",
            f"/api/allocations-service/{ALLOCATION_ID}",
            body={"allocation_pct": 60},
            token=make_token("CONTRIBUTOR"),
        )
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 200, result["body"]
        assert mock_repo["peak_existing_pct"].call_args.kwargs.get("exclude_id") == ALLOCATION_ID

    def test_update_still_rejects_genuine_over_allocation(self, allocations, make_event, make_token, mock_repo):
        # Excluding this row's own 60% still leaves 80% from *other*
        # allocations — raising this row to 30% would total 110%.
        mock_repo["peak_existing_pct"].return_value = 80
        event = make_event(
            "PUT",
            f"/api/allocations-service/{ALLOCATION_ID}",
            body={"allocation_pct": 30},
            token=make_token("CONTRIBUTOR"),
        )
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 409
        mock_repo["update_allocation"].assert_not_called()

    def test_update_reuses_existing_dates_when_only_pct_changes(self, allocations, make_event, make_token, mock_repo):
        """A partial update touching only allocation_pct must still check
        overlap against the row's existing start/end dates, not blanks."""
        event = make_event(
            "PUT",
            f"/api/allocations-service/{ALLOCATION_ID}",
            body={"allocation_pct": 60},
            token=make_token("CONTRIBUTOR"),
        )
        allocations.function.handler(event, {})
        args, _ = mock_repo["peak_existing_pct"].call_args
        assert args[0] == VALID_ALLOCATION_ROW["user_id"]
        assert args[1] == VALID_ALLOCATION_ROW["start_date"]
        assert args[2] == VALID_ALLOCATION_ROW["end_date"]


class TestDateOrdering:
    def test_end_before_start_returns_400(self, allocations, make_event, make_token, mock_repo):
        body = {**VALID_PAYLOAD, "start_date": "2027-06-01", "end_date": "2027-01-01"}
        event = make_event("POST", "/api/allocations-service", body=body, token=make_token("MANAGER"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 400
        payload = json.loads(result["body"])
        assert payload["error"]["details"]["end_date"] == "must be on or after the start date"
        mock_repo["peak_existing_pct"].assert_not_called()

    def test_end_equal_to_start_is_allowed(self, allocations, make_event, make_token, mock_repo):
        """A single-day allocation (end == start) is a boundary, not a
        violation — only end < start is rejected."""
        body = {**VALID_PAYLOAD, "start_date": "2027-06-01", "end_date": "2027-06-01"}
        event = make_event("POST", "/api/allocations-service", body=body, token=make_token("MANAGER"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 201, result["body"]

    def test_schema_business_rule_in_isolation(self, allocations):
        """The pure date-ordering rule, exercised directly with no HTTP or
        mocking involved at all."""
        with pytest.raises(allocations.http.ValidationError):
            allocations.schema.check_business_rules({"start_date": "2027-06-01", "end_date": "2027-01-01"})
        allocations.schema.check_business_rules({"start_date": "2027-01-01", "end_date": "2027-06-01"})

    def test_schema_business_rule_uses_existing_on_partial_update(self, allocations):
        """On a partial update that only sends end_date, the rule must
        check it against the *existing* start_date, not skip validation."""
        with pytest.raises(allocations.http.ValidationError):
            allocations.schema.check_business_rules(
                {"end_date": "2026-12-31"}, existing={"start_date": "2027-01-01", "end_date": "2027-06-30"}
            )


class TestRBAC:
    @pytest.mark.parametrize("role", ["VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN"])
    def test_get_allowed_for_every_role(self, allocations, make_event, make_token, mock_repo, role):
        event = make_event("GET", "/api/allocations-service", token=make_token(role))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 200

    @pytest.mark.parametrize(
        "role,expected_status",
        [("VIEWER", 403), ("CONTRIBUTOR", 201), ("MANAGER", 201), ("ADMIN", 201)],
    )
    def test_post_requires_contributor_or_above(
        self, allocations, make_event, make_token, mock_repo, role, expected_status
    ):
        event = make_event("POST", "/api/allocations-service", body=VALID_PAYLOAD, token=make_token(role))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == expected_status

    @pytest.mark.parametrize(
        "role,expected_status",
        [("VIEWER", 403), ("CONTRIBUTOR", 403), ("MANAGER", 204), ("ADMIN", 204)],
    )
    def test_delete_requires_manager_or_above(self, allocations, make_event, make_token, mock_repo, role, expected_status):
        event = make_event("DELETE", f"/api/allocations-service/{ALLOCATION_ID}", token=make_token(role))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == expected_status

    def test_options_bypasses_auth(self, allocations, make_event):
        event = make_event("OPTIONS", "/api/allocations-service")
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 204

    def test_missing_token_returns_401(self, allocations, make_event):
        event = make_event("GET", "/api/allocations-service")
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 401


class TestValidationAndReferences:
    def test_missing_required_fields_returns_400(self, allocations, make_event, make_token, mock_repo):
        event = make_event("POST", "/api/allocations-service", body={}, token=make_token("ADMIN"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 400
        details = json.loads(result["body"])["error"]["details"]
        assert set(details) == {"user_id", "project_id", "allocation_pct", "start_date", "end_date"}

    def test_allocation_pct_below_minimum_returns_400(self, allocations, make_event, make_token, mock_repo):
        body = {**VALID_PAYLOAD, "allocation_pct": 0}
        event = make_event("POST", "/api/allocations-service", body=body, token=make_token("ADMIN"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 400

    def test_unknown_user_returns_400(self, allocations, make_event, make_token, mock_repo):
        mock_repo["exists"].side_effect = lambda table, _id: table != "users"
        event = make_event("POST", "/api/allocations-service", body=VALID_PAYLOAD, token=make_token("ADMIN"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["error"]["details"]["user_id"] == "no user exists with this id"
        mock_repo["peak_existing_pct"].assert_not_called()

    def test_unknown_project_returns_400(self, allocations, make_event, make_token, mock_repo):
        mock_repo["exists"].side_effect = lambda table, _id: table != "projects"
        event = make_event("POST", "/api/allocations-service", body=VALID_PAYLOAD, token=make_token("ADMIN"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 400
        assert json.loads(result["body"])["error"]["details"]["project_id"] == "no project exists with this id"


class TestCrudSuccess:
    def test_list_allocations_returns_200_with_meta(self, allocations, make_event, make_token, mock_repo):
        event = make_event("GET", "/api/allocations-service", token=make_token("VIEWER"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 200
        payload = json.loads(result["body"])
        assert payload["data"][0]["id"] == ALLOCATION_ID
        assert payload["meta"] == {"total": 1, "limit": 50, "offset": 0}

    def test_get_allocation_returns_200(self, allocations, make_event, make_token, mock_repo):
        event = make_event("GET", f"/api/allocations-service/{ALLOCATION_ID}", token=make_token("VIEWER"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 200

    def test_get_missing_allocation_returns_404(self, allocations, make_event, make_token, mock_repo):
        mock_repo["get_allocation"].return_value = None
        event = make_event("GET", f"/api/allocations-service/{uuid.uuid4()}", token=make_token("VIEWER"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 404

    def test_create_allocation_returns_201(self, allocations, make_event, make_token, mock_repo):
        event = make_event("POST", "/api/allocations-service", body=VALID_PAYLOAD, token=make_token("MANAGER"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 201
        mock_repo["create_allocation"].assert_called_once()

    def test_delete_allocation_returns_204(self, allocations, make_event, make_token, mock_repo):
        event = make_event("DELETE", f"/api/allocations-service/{ALLOCATION_ID}", token=make_token("ADMIN"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 204
        mock_repo["delete_allocation"].assert_called_once_with(ALLOCATION_ID)

    def test_delete_missing_allocation_returns_404(self, allocations, make_event, make_token, mock_repo):
        mock_repo["get_allocation"].return_value = None
        event = make_event("DELETE", f"/api/allocations-service/{uuid.uuid4()}", token=make_token("ADMIN"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 404

    def test_update_missing_allocation_returns_404(self, allocations, make_event, make_token, mock_repo):
        mock_repo["get_allocation"].return_value = None
        event = make_event(
            "PUT", f"/api/allocations-service/{uuid.uuid4()}", body={"allocation_pct": 50}, token=make_token("ADMIN")
        )
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 404
        mock_repo["update_allocation"].assert_not_called()

    def test_put_without_id_returns_400(self, allocations, make_event, make_token, mock_repo):
        event = make_event("PUT", "/api/allocations-service", body={"allocation_pct": 50}, token=make_token("ADMIN"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 400

    def test_delete_without_id_returns_400(self, allocations, make_event, make_token, mock_repo):
        event = make_event("DELETE", "/api/allocations-service", token=make_token("ADMIN"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 400

    def test_unsupported_method_returns_405(self, allocations, make_event, make_token, mock_repo):
        event = make_event("PATCH", "/api/allocations-service", token=make_token("ADMIN"))
        result = allocations.function.handler(event, {})
        assert result["statusCode"] == 405
        mock_repo["delete_allocation"].assert_not_called()
