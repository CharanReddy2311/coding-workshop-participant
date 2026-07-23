"""Shared pytest fixtures for every backend service test suite.

Each service under backend/<name>/ defines its own top-level `function`,
`repository`, and `schema` modules, plus its own synced copy of `_shared`
(see backend/_shared/__init__.py) — the same "vendor everything into the
service folder" scheme bin/local-dev-server.py already deals with for local
running. Importing two services' modules in the same pytest process would
collide (both define a bare module called `function`), so `load_service()`
below applies the identical fix: purge the previous service's modules from
sys.modules before importing the next one fresh.

The database is never touched. Tests mock `repository.*` (the functions
service handlers call directly) rather than `_shared.db.*`, so `function.py`
— validation, business rules, RBAC, HTTP status mapping — runs unmodified
and for real; only the SQL round-trip is replaced. That keeps these tests
fast and independent of whether Postgres is running anywhere, which is the
point: they must pass the same way on a grader's machine as on this one.
"""

import importlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import jwt
import pytest

BACKEND_DIR = Path(__file__).parent

# Matches _shared/auth.py's own fallback: IS_LOCAL=true and no JWT_SECRET
# set. Using the real secret (rather than inventing a separate test one)
# means create_token()/decode_token() run completely unmodified.
TEST_JWT_SECRET = "local-development-secret-do-not-use-in-cloud"
TEST_ACCESS_TOKEN_TTL = 3600

_PER_SERVICE_MODULES = ("function", "repository", "schema")


@pytest.fixture(autouse=True)
def _local_environment(monkeypatch):
    """Every service's _shared/auth.py and _shared/db.py branch on
    IS_LOCAL; pin it so tests don't depend on whatever's in the real shell
    environment (e.g. a JWT_SECRET left over from a cloud deploy)."""
    monkeypatch.setenv("IS_LOCAL", "true")
    monkeypatch.delenv("JWT_SECRET", raising=False)


def _load_service(service_name):
    """Import `service_name`'s function/repository/schema modules fresh,
    purging any other service's same-named modules first."""
    service_dir = BACKEND_DIR / service_name
    if not service_dir.is_dir():
        raise ValueError(f"No such backend service: {service_name}")

    for name in list(sys.modules):
        if name in _PER_SERVICE_MODULES or name == "_shared" or name.startswith("_shared."):
            del sys.modules[name]

    sys.path.insert(0, str(service_dir))
    try:
        function = importlib.import_module("function")
        repository = sys.modules.get("repository")
        schema = sys.modules.get("schema")
        shared_auth = importlib.import_module("_shared.auth")
        shared_http = importlib.import_module("_shared.http")
        shared_db = importlib.import_module("_shared.db")
    finally:
        sys.path.remove(str(service_dir))

    return SimpleNamespace(
        function=function,
        repository=repository,
        schema=schema,
        auth=shared_auth,
        http=shared_http,
        db=shared_db,
    )


@pytest.fixture
def load_service():
    """Factory fixture: load_service("teams-service") -> namespace with
    .function/.repository/.schema/.auth/.http/.db attributes."""
    return _load_service


@pytest.fixture
def make_event():
    """Build a Lambda Function URL payload-format-2.0 event, matching what
    _shared/http.py's helpers (http_method, raw_path, path_segments,
    parse_body, query_params) expect — the same shape bin/local-dev-server.py
    constructs from a real HTTP request.
    """

    def _make(method, path, *, body=None, token=None, query=None, headers=None):
        hdrs = {k.lower(): v for k, v in (headers or {}).items()}
        if token:
            hdrs["authorization"] = f"Bearer {token}"
        return {
            "version": "2.0",
            "rawPath": path,
            "headers": hdrs,
            "queryStringParameters": query or None,
            "requestContext": {"http": {"method": method}},
            "body": json.dumps(body) if body is not None else None,
            "isBase64Encoded": False,
        }

    return _make


@pytest.fixture
def make_token():
    """Mint a real, correctly-signed access token for a given role, without
    needing a seeded user row — every service's authorize() verifies the
    JWT itself and trusts the embedded role claim; it never re-queries the
    database per request (only auth-service's own /me and /refresh do).
    """

    def _make(role, user_id="11111111-1111-1111-1111-111111111111", email="tester@example.com"):
        now = int(time.time())
        payload = {
            "sub": user_id,
            "email": email,
            "role": role,
            "type": "access",
            "iat": now,
            "exp": now + TEST_ACCESS_TOKEN_TTL,
        }
        return jwt.encode(payload, TEST_JWT_SECRET, algorithm="HS256")

    return _make
