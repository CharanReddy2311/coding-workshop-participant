"""Direct unit tests for backend/_shared/http.py — the error classes,
response envelope builders, and the payload-v2 parsing helpers every
service's function.py is built on.

Pure logic, no I/O, so these are fast and exhaustive. Parametrized across
every service in scope so each vendored copy gets real execution credit
(see test_shared_db.py for why that matters).
"""

import base64
import datetime
import decimal
import json
import uuid

import pytest


@pytest.fixture(params=["teams-service", "allocations-service", "projects-service", "deliverables-service", "directory-service"])
def shared(request, load_service):
    return load_service(request.param)


@pytest.fixture
def http(shared):
    return shared.http


class TestApiErrorHierarchy:
    def test_default_status_and_code(self, http):
        exc = http.ApiError("boom")
        assert exc.status == 500
        assert exc.code == "internal_error"
        assert exc.message == "boom"
        assert exc.details == {}

    def test_details_default_to_empty_dict_not_none(self, http):
        assert http.ApiError("boom").details == {}
        assert http.ApiError("boom", details={"field": "bad"}).details == {"field": "bad"}

    def test_explicit_code_and_status_override_the_class_defaults(self, http):
        exc = http.ApiError("nope", status=405, code="method_not_allowed")
        assert exc.status == 405
        assert exc.code == "method_not_allowed"

    @pytest.mark.parametrize(
        "exc_class,expected_status,expected_code",
        [
            ("ValidationError", 400, "validation_error"),
            ("UnauthorizedError", 401, "unauthorized"),
            ("ForbiddenError", 403, "forbidden"),
            ("NotFoundError", 404, "not_found"),
            ("ConflictError", 409, "conflict"),
        ],
    )
    def test_each_subclass_has_its_own_default(self, http, exc_class, expected_status, expected_code):
        cls = getattr(http, exc_class)
        exc = cls("message")
        assert exc.status == expected_status
        assert exc.code == expected_code

    def test_is_a_real_exception(self, http):
        with pytest.raises(http.NotFoundError):
            raise http.NotFoundError("gone")


class TestJsonDefault:
    def test_decimal_becomes_float(self, http):
        assert http._json_default(decimal.Decimal("19.99")) == 19.99

    def test_date_becomes_iso_string(self, http):
        assert http._json_default(datetime.date(2027, 1, 15)) == "2027-01-15"

    def test_datetime_becomes_iso_string(self, http):
        result = http._json_default(datetime.datetime(2027, 1, 15, 10, 30))
        assert result == "2027-01-15T10:30:00"

    def test_uuid_becomes_string(self, http):
        value = uuid.uuid4()
        assert http._json_default(value) == str(value)

    def test_unknown_type_falls_back_to_str(self, http):
        class Weird:
            def __str__(self):
                return "weird-value"

        assert http._json_default(Weird()) == "weird-value"


class TestResponse:
    def test_200_wraps_data_in_envelope(self, http):
        result = http.response(200, {"id": "x"})
        assert result["statusCode"] == 200
        assert json.loads(result["body"]) == {"data": {"id": "x"}}

    def test_includes_meta_only_when_provided(self, http):
        result = http.response(200, [{"id": "x"}], meta={"total": 1})
        body = json.loads(result["body"])
        assert body["meta"] == {"total": 1}

        result_no_meta = http.response(200, [{"id": "x"}])
        assert "meta" not in json.loads(result_no_meta["body"])

    def test_204_has_an_empty_body(self, http):
        result = http.response(204)
        assert result["statusCode"] == 204
        assert result["body"] == ""

    def test_always_includes_cors_headers(self, http):
        result = http.response(200, {})
        assert result["headers"]["Access-Control-Allow-Origin"] == "*"

    def test_serializes_decimal_and_date_via_json_default(self, http):
        result = http.response(200, {"amount": decimal.Decimal("5.50"), "due": datetime.date(2027, 1, 1)})
        body = json.loads(result["body"])
        assert body["data"]["amount"] == 5.5
        assert body["data"]["due"] == "2027-01-01"


class TestErrorResponse:
    def test_builds_standard_error_envelope(self, http):
        exc = http.NotFoundError("No team found")
        result = http.error_response(exc)
        assert result["statusCode"] == 404
        body = json.loads(result["body"])
        assert body["error"] == {"code": "not_found", "message": "No team found"}

    def test_includes_details_only_when_present(self, http):
        exc = http.ValidationError("bad input", details={"name": "is required"})
        body = json.loads(http.error_response(exc)["body"])
        assert body["error"]["details"] == {"name": "is required"}

        exc_no_details = http.ValidationError("bad input")
        body_no_details = json.loads(http.error_response(exc_no_details)["body"])
        assert "details" not in body_no_details["error"]


class TestWithHttpErrors:
    def test_passes_through_a_successful_call(self, http):
        @http.with_http_errors
        def handler(event, context):
            return http.response(200, {"ok": True})

        result = handler({"requestContext": {"http": {"method": "GET"}}}, {})
        assert result["statusCode"] == 200

    def test_catches_api_error_and_formats_it(self, http):
        @http.with_http_errors
        def handler(event, context):
            raise http.NotFoundError("missing")

        result = handler({"requestContext": {"http": {"method": "GET"}}}, {})
        assert result["statusCode"] == 404
        assert json.loads(result["body"])["error"]["message"] == "missing"

    def test_catches_any_other_exception_as_a_generic_500_without_leaking_details(self, http):
        """A raw internal exception message must never reach the client —
        only the generic message, regardless of what actually broke."""

        @http.with_http_errors
        def handler(event, context):
            raise RuntimeError("password=hunter2 connection string leaked")

        result = handler({"requestContext": {"http": {"method": "GET"}}}, {})
        assert result["statusCode"] == 500
        body = json.loads(result["body"])
        assert body["error"]["message"] == "An unexpected error occurred"
        assert "hunter2" not in result["body"]

    def test_extracts_method_from_event_passed_as_first_positional_arg(self, http):
        @http.with_http_errors
        def handler(event, context):
            raise http.ValidationError("bad")

        # Must not raise while trying to read the method for logging, even
        # with a minimal event.
        result = handler({}, {})
        assert result["statusCode"] == 400


class TestHttpMethod:
    def test_reads_payload_v2_shape(self, http):
        event = {"requestContext": {"http": {"method": "POST"}}}
        assert http.http_method(event) == "POST"

    def test_falls_back_to_payload_v1_http_method(self, http):
        event = {"httpMethod": "PUT"}
        assert http.http_method(event) == "PUT"

    def test_defaults_to_get_for_empty_event(self, http):
        assert http.http_method(None) == "GET"
        assert http.http_method({}) == "GET"


class TestRawPath:
    def test_reads_raw_path(self, http):
        assert http.raw_path({"rawPath": "/api/teams-service"}) == "/api/teams-service"

    def test_falls_back_to_path(self, http):
        assert http.raw_path({"path": "/api/teams-service"}) == "/api/teams-service"

    def test_defaults_to_root(self, http):
        assert http.raw_path(None) == "/"
        assert http.raw_path({}) == "/"


class TestPathSegments:
    def test_strips_api_and_service_prefix(self, http):
        event = {"rawPath": "/api/deliverables-service/d1/dependencies"}
        assert http.path_segments(event, "deliverables-service") == ["d1", "dependencies"]

    def test_local_shape_without_api_or_service_prefix(self, http):
        event = {"rawPath": "/d1/dependencies"}
        assert http.path_segments(event, "deliverables-service") == ["d1", "dependencies"]

    def test_collection_path_yields_no_segments(self, http):
        event = {"rawPath": "/api/teams-service"}
        assert http.path_segments(event, "teams-service") == []

    def test_without_a_service_name_only_strips_api(self, http):
        event = {"rawPath": "/api/teams-service/t1"}
        assert http.path_segments(event) == ["teams-service", "t1"]


class TestResourceId:
    def test_explicit_path_parameters_take_priority(self, http):
        event = {"pathParameters": {"id": "explicit-id"}, "rawPath": "/api/teams-service/other-id"}
        assert http.resource_id(event, "teams-service") == "explicit-id"

    def test_falls_back_to_first_path_segment(self, http):
        event = {"rawPath": "/api/teams-service/t1"}
        assert http.resource_id(event, "teams-service") == "t1"

    def test_none_for_a_collection_request(self, http):
        event = {"rawPath": "/api/teams-service"}
        assert http.resource_id(event, "teams-service") is None


class TestParseBody:
    def test_missing_body_is_an_empty_dict(self, http):
        assert http.parse_body({}) == {}
        assert http.parse_body({"body": None}) == {}
        assert http.parse_body({"body": ""}) == {}

    def test_dict_body_passes_through(self, http):
        assert http.parse_body({"body": {"name": "x"}}) == {"name": "x"}

    def test_json_string_body_is_parsed(self, http):
        assert http.parse_body({"body": '{"name": "x"}'}) == {"name": "x"}

    def test_base64_encoded_body_is_decoded_then_parsed(self, http):
        raw = json.dumps({"name": "x"}).encode()
        event = {"body": base64.b64encode(raw).decode(), "isBase64Encoded": True}
        assert http.parse_body(event) == {"name": "x"}

    def test_invalid_json_raises_validation_error(self, http):
        with pytest.raises(http.ValidationError):
            http.parse_body({"body": "not json"})

    def test_non_object_json_raises_validation_error(self, http):
        with pytest.raises(http.ValidationError):
            http.parse_body({"body": "[1, 2, 3]"})


class TestQueryParams:
    def test_returns_the_dict_when_present(self, http):
        assert http.query_params({"queryStringParameters": {"q": "x"}}) == {"q": "x"}

    def test_empty_dict_when_absent(self, http):
        assert http.query_params({}) == {}
        assert http.query_params(None) == {}


class TestHeaders:
    def test_lowercases_header_names(self, http):
        event = {"headers": {"Authorization": "Bearer x", "Content-Type": "application/json"}}
        result = http.headers(event)
        assert result["authorization"] == "Bearer x"
        assert result["content-type"] == "application/json"

    def test_empty_dict_when_absent(self, http):
        assert http.headers({}) == {}
        assert http.headers(None) == {}
