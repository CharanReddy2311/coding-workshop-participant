"""HTTP helpers shared by every Lambda service.

Two scaffold-specific details this module exists to absorb:

1.  Services are exposed as Lambda Function URLs (infra/lambda.tf sets
    authorization_type = "NONE"), which deliver payload format 2.0. There is
    no `httpMethod` and no `pathParameters` — the method lives at
    requestContext.http.method and the path at rawPath.

2.  The path prefix differs between environments. In the cloud CloudFront
    matches `/api/{service}*` and forwards the whole path, so rawPath is
    `/api/projects-service/{id}`. Locally bin/proxy-server.js strips the
    prefix before forwarding, so rawPath is just `/{id}`. `resource_id()`
    normalises both, which is what lets the same code run in both places.
"""

import datetime
import decimal
import json
import logging
import uuid
from functools import wraps
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
}


class ApiError(Exception):
    """Base class for every error that maps onto an HTTP status."""

    status = 500
    code = "internal_error"

    def __init__(self, message, details=None, code=None, status=None):
        super().__init__(message)
        self.message = message
        self.details = details or {}
        if code:
            self.code = code
        if status:
            self.status = status


class ValidationError(ApiError):
    status, code = 400, "validation_error"


class UnauthorizedError(ApiError):
    status, code = 401, "unauthorized"


class ForbiddenError(ApiError):
    status, code = 403, "forbidden"


class NotFoundError(ApiError):
    status, code = 404, "not_found"


class ConflictError(ApiError):
    status, code = 409, "conflict"


def _json_default(value):
    """Serialise the Postgres types psycopg hands back that json cannot."""
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def response(status, data=None, meta=None):
    body = ""
    if status != 204:
        payload = {"data": data}
        if meta:
            payload["meta"] = meta
        body = json.dumps(payload, default=_json_default)
    return {"statusCode": status, "headers": CORS_HEADERS, "body": body}


def error_response(exc: ApiError):
    """Return a standard JSON error envelope with a REST-style status code."""
    body = {"error": {"code": exc.code, "message": exc.message}}
    if exc.details:
        body["error"]["details"] = exc.details
    return {
        "statusCode": exc.status,
        "headers": CORS_HEADERS,
        "body": json.dumps(body, default=_json_default),
    }


F = TypeVar("F", bound=Callable[..., Any])


def with_http_errors(handler: F) -> F:
    """Centralise Lambda error mapping so every route returns a consistent JSON payload."""

    @wraps(handler)
    def wrapped(*args: Any, **kwargs: Any) -> dict:
        event = kwargs.get("event") if kwargs else None
        if event is None and args:
            event = args[0]
        method = http_method(event or {})

        try:
            return handler(*args, **kwargs)
        except ApiError as exc:
            logger.warning("%s -> %s: %s", method, exc.status, exc.message)
            return error_response(exc)
        except Exception:
            logger.exception("Unhandled error in %s", getattr(handler, "__name__", "handler"))
            return error_response(ApiError("An unexpected error occurred"))

    return wrapped  # type: ignore[return-value]


def http_method(event):
    """Method, for payload v2 with a fallback to v1."""
    if not event:
        return "GET"
    method = event.get("requestContext", {}).get("http", {}).get("method")
    return method or event.get("httpMethod") or "GET"


def raw_path(event):
    if not event:
        return "/"
    return event.get("rawPath") or event.get("path") or "/"


def path_segments(event, service_name=None):
    """Return the path segments after the service prefix.

    Normalises the two shapes the same request arrives in:
      cloud  /api/deliverables-service/{id}/chain  -> ["{id}", "chain"]
      local  /{id}/chain                           -> ["{id}", "chain"]
    """
    segments = [segment for segment in raw_path(event).split("/") if segment]
    if segments and segments[0] == "api":
        segments = segments[1:]
    if service_name and segments and segments[0] == service_name:
        segments = segments[1:]
    return segments


def resource_id(event, service_name=None):
    """Return the trailing `{id}` segment, or None for a collection request."""
    explicit = (event.get("pathParameters") or {}).get("id")
    if explicit:
        return explicit
    segments = path_segments(event, service_name)
    return segments[0] if segments else None


def parse_body(event):
    """Return the request body as a dict, or raise ValidationError."""
    raw = (event or {}).get("body")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    if (event or {}).get("isBase64Encoded"):
        import base64

        raw = base64.b64decode(raw).decode("utf-8")
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        raise ValidationError("Request body is not valid JSON")
    if not isinstance(parsed, dict):
        raise ValidationError("Request body must be a JSON object")
    return parsed


def query_params(event):
    return (event or {}).get("queryStringParameters") or {}


def headers(event):
    """Header names lowercased, because casing is not guaranteed."""
    return {k.lower(): v for k, v in ((event or {}).get("headers") or {}).items()}
