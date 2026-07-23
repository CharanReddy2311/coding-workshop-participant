"""Authentication and role-based access control shared by every service.

Password hashing uses PBKDF2-HMAC-SHA256 from the standard library rather than
bcrypt. bcrypt is a compiled extension that would have to be built for the
Lambda runtime; pbkdf2_hmac is stdlib, so there is no wheel to get wrong. The
stored format is self-describing, so swapping in bcrypt later is a migration
rather than a rewrite.

Local development note: bin/proxy-server.js drops the Authorization header.
Rather than modifying a scaffold file, `current_user()` also accepts a token
via ?token=... when IS_LOCAL is true. See `_token_from_event`.
"""

import functools
import hashlib
import hmac
import os
import secrets
import time

import jwt

from .http import ForbiddenError, UnauthorizedError, headers, http_method

ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = 60 * 60             # 1 hour
REFRESH_TOKEN_TTL = 60 * 60 * 24 * 7   # 7 days
PBKDF2_ITERATIONS = 260_000

# Ordered least to most privileged.
ROLES = ("VIEWER", "CONTRIBUTOR", "MANAGER", "ADMIN")

DEFAULT_PERMISSIONS = {
    "GET": ROLES,
    "OPTIONS": ROLES,
    "POST": ("CONTRIBUTOR", "MANAGER", "ADMIN"),
    "PUT": ("CONTRIBUTOR", "MANAGER", "ADMIN"),
    "DELETE": ("MANAGER", "ADMIN"),
}


def _secret():
    secret = os.getenv("JWT_SECRET")
    if secret:
        return secret
    if os.getenv("IS_LOCAL", "false").lower() == "true":
        return "local-development-secret-do-not-use-in-cloud"
    # Never fall back to a fixed default in the cloud: a predictable signing
    # key means anyone can mint themselves an ADMIN token.
    raise UnauthorizedError("Server is misconfigured: JWT_SECRET is not set")


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------

def hash_password(plain):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", plain.encode(), salt.encode(), PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(plain, stored):
    try:
        algorithm, iterations, salt, expected = stored.split("$")
    except (AttributeError, ValueError):
        return False
    if algorithm != "pbkdf2_sha256":
        return False
    candidate = hashlib.pbkdf2_hmac(
        "sha256", plain.encode(), salt.encode(), int(iterations)
    ).hex()
    return hmac.compare_digest(candidate, expected)


# --------------------------------------------------------------------------
# Tokens
# --------------------------------------------------------------------------

def create_token(user, token_type="access"):
    ttl = ACCESS_TOKEN_TTL if token_type == "access" else REFRESH_TOKEN_TTL
    now = int(time.time())
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "role": user["role"],
        "type": token_type,
        "iat": now,
        "exp": now + ttl,
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def decode_token(token, expected_type="access"):
    try:
        payload = jwt.decode(token, _secret(), algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise UnauthorizedError("Token has expired", code="token_expired")
    except jwt.InvalidTokenError:
        raise UnauthorizedError("Token is invalid", code="token_invalid")
    if payload.get("type") != expected_type:
        raise UnauthorizedError(f"Expected a {expected_type} token")
    return payload


def _token_from_event(event):
    """Find the bearer token, with a local-development fallback.

    bin/proxy-server.js rebuilds every outgoing request and keeps only four
    headers — accept, content-type, user-agent and host. Authorization is
    dropped, so a token sent the normal way never reaches the Lambda locally.

    Rather than editing a file that ships with the scaffold, a token may also
    be passed as ?token=... during local development. The proxy preserves the
    query string, so it arrives intact. This path is gated on IS_LOCAL and is
    never active in the cloud, where CloudFront talks to the Function URL
    directly and the Authorization header survives.

    Query strings end up in access logs, which is exactly why this is
    local-only.
    """
    header = headers(event).get("authorization", "")
    if header.startswith("Bearer "):
        return header.split(" ", 1)[1].strip()

    if os.getenv("IS_LOCAL", "false").lower() == "true":
        token = ((event or {}).get("queryStringParameters") or {}).get("token")
        if token:
            return token.strip()

    return None


def current_user(event):
    """Extract and verify the caller from the request."""
    token = _token_from_event(event)
    if not token:
        raise UnauthorizedError("Missing bearer token")
    payload = decode_token(token)
    return {"id": payload["sub"], "email": payload["email"], "role": payload["role"]}


# --------------------------------------------------------------------------
# RBAC
# --------------------------------------------------------------------------

def authorize(event, permissions=None):
    """Authenticate, then check the caller's role against the method.

    Authentication first, authorisation second, both in one place so no
    handler can forget to call them.
    """
    permissions = permissions or DEFAULT_PERMISSIONS
    user = current_user(event)
    method = http_method(event)
    if user["role"] not in permissions.get(method, ()):
        raise ForbiddenError(
            f"Role {user['role']} may not perform {method} on this resource"
        )
    return user


def protected(permissions=None):
    """Decorator that injects the authorised user as a `user` kwarg."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(event, context, *args, **kwargs):
            return func(event, context, *args,
                        user=authorize(event, permissions), **kwargs)

        return wrapper

    return decorator
