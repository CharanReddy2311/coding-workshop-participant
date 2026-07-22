"""auth-service — login, token refresh, and current-user lookup.

    POST /api/auth-service/login     email + password -> access + refresh tokens
    POST /api/auth-service/refresh   refresh token    -> new access token
    GET  /api/auth-service/me        bearer token     -> current user

This service does not follow the CRUD template: it dispatches on the trailing
path segment rather than treating it as a record id. `login` and `refresh` are
the only unauthenticated endpoints in the entire platform — everything else
goes through authorize().
"""

import logging

import repository

from _shared.auth import (
    ACCESS_TOKEN_TTL,
    create_token,
    current_user,
    decode_token,
    verify_password,
)
from _shared.http import (
    ApiError,
    UnauthorizedError,
    http_method,
    parse_body,
    resource_id,
    response,
    with_http_errors,
)
from _shared.validation import Field, validate

logger = logging.getLogger()
logger.setLevel(logging.INFO)

SERVICE_NAME = "auth-service"

LOGIN_SCHEMA = {
    "email": Field("email", required=True),
    "password": Field("string", required=True, min_length=1, max_length=256),
}

REFRESH_SCHEMA = {
    "refresh_token": Field("string", required=True, min_length=10),
}

# Deliberately identical for unknown email, wrong password and deactivated
# account. Distinguishing them tells an attacker which addresses are real.
INVALID_CREDENTIALS = "Email or password is incorrect"


def _public_user(row):
    return {
        "id": str(row["id"]),
        "email": row["email"],
        "full_name": row["full_name"],
        "role": row["role"],
    }


def login(event):
    data = validate(parse_body(event), LOGIN_SCHEMA)
    user = repository.find_by_email_for_login(data["email"])

    if not user or not verify_password(data["password"], user["password_hash"]):
        logger.warning("Failed login attempt for %s", data["email"])
        raise UnauthorizedError(INVALID_CREDENTIALS, code="invalid_credentials")

    if not user["is_active"]:
        logger.warning("Login attempt on deactivated account %s", data["email"])
        raise UnauthorizedError(INVALID_CREDENTIALS, code="invalid_credentials")

    repository.touch_last_login(user["id"])
    logger.info("Successful login for %s (%s)", user["email"], user["role"])

    payload = _public_user(user)
    return response(200, {
        "access_token": create_token(payload, "access"),
        "refresh_token": create_token(payload, "refresh"),
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_TTL,
        "user": payload,
    })


def refresh(event):
    data = validate(parse_body(event), REFRESH_SCHEMA)
    claims = decode_token(data["refresh_token"], expected_type="refresh")

    # Re-read the user rather than trusting the token's claims: a role change
    # or deactivation since the token was issued must take effect immediately.
    user = repository.find_by_id(claims["sub"])
    if not user or not user["is_active"]:
        raise UnauthorizedError("Account is no longer active",
                                code="account_inactive")

    payload = _public_user(user)
    logger.info("Refreshed token for %s", user["email"])
    return response(200, {
        "access_token": create_token(payload, "access"),
        "token_type": "Bearer",
        "expires_in": ACCESS_TOKEN_TTL,
        "user": payload,
    })


def me(event):
    caller = current_user(event)
    user = repository.find_by_id(caller["id"])
    if not user:
        raise UnauthorizedError("Account no longer exists", code="account_missing")
    return response(200, user)


@with_http_errors
def handler(event=None, context=None):
    event = event or {}
    method = http_method(event)
    action = resource_id(event, SERVICE_NAME)

    if method == "OPTIONS":
        return response(204)

    if method == "POST" and action == "login":
        return login(event)
    if method == "POST" and action == "refresh":
        return refresh(event)
    if method == "GET" and action == "me":
        return me(event)

    raise ApiError(
        f"Unknown route: {method} /{action or ''}",
        status=404,
        code="route_not_found",
        details={"available": ["POST /login", "POST /refresh", "GET /me"]},
    )


if __name__ == "__main__":
    print(handler())
