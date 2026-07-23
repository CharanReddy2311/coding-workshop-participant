"""Direct unit tests for backend/_shared/auth.py — password hashing, JWT
issuing/verification, the local-dev ?token= fallback, and RBAC.

Every other test file in this suite exercises authorize()/current_user()
indirectly through a real service's handler(); these tests close the real
gaps that leaves: hash_password/verify_password (nothing here touches
passwords except auth-service, which isn't in scope), create_token itself
(prior tests mint tokens with raw PyJWT in conftest.py, bypassing it),
expired/wrong-type tokens, the query-string fallback, and the `protected`
decorator (unused by every service tested so far).

Parametrized across every service in scope so both/all vendored copies of
this file get real execution credit (see test_shared_db.py for why that
matters).
"""

import time

import jwt
import pytest


@pytest.fixture(params=["teams-service", "allocations-service", "projects-service", "deliverables-service", "directory-service"])
def shared(request, load_service):
    return load_service(request.param)


@pytest.fixture
def auth(shared):
    return shared.auth


@pytest.fixture(autouse=True)
def local_secret(monkeypatch):
    monkeypatch.setenv("IS_LOCAL", "true")
    monkeypatch.delenv("JWT_SECRET", raising=False)


class TestSecret:
    def test_explicit_jwt_secret_wins_even_when_local(self, auth, monkeypatch):
        monkeypatch.setenv("JWT_SECRET", "explicit-secret")
        assert auth._secret() == "explicit-secret"

    def test_local_fallback_when_no_explicit_secret(self, auth, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        monkeypatch.delenv("JWT_SECRET", raising=False)
        assert auth._secret() == "local-development-secret-do-not-use-in-cloud"

    def test_raises_when_not_local_and_no_secret_set(self, auth, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "false")
        monkeypatch.delenv("JWT_SECRET", raising=False)
        with pytest.raises(auth.UnauthorizedError):
            auth._secret()


class TestPasswordHashing:
    def test_round_trip_succeeds(self, auth):
        stored = auth.hash_password("correct horse battery staple")
        assert auth.verify_password("correct horse battery staple", stored) is True

    def test_wrong_password_fails(self, auth):
        stored = auth.hash_password("correct horse battery staple")
        assert auth.verify_password("wrong password", stored) is False

    def test_same_password_hashes_differently_each_time(self, auth):
        """A random salt per call — otherwise identical passwords would
        produce identical stored hashes, leaking who shares a password."""
        first = auth.hash_password("hunter2")
        second = auth.hash_password("hunter2")
        assert first != second
        assert auth.verify_password("hunter2", first) is True
        assert auth.verify_password("hunter2", second) is True

    def test_stored_format_is_self_describing(self, auth):
        stored = auth.hash_password("hunter2")
        algorithm, iterations, salt, digest = stored.split("$")
        assert algorithm == "pbkdf2_sha256"
        assert int(iterations) == auth.PBKDF2_ITERATIONS
        assert salt and digest

    @pytest.mark.parametrize("malformed", ["not-enough-parts", "", "a$b$c$d$e", None])
    def test_malformed_stored_value_fails_closed(self, auth, malformed):
        assert auth.verify_password("anything", malformed) is False

    def test_wrong_algorithm_prefix_fails(self, auth):
        stored = auth.hash_password("hunter2").replace("pbkdf2_sha256", "bcrypt", 1)
        assert auth.verify_password("hunter2", stored) is False


class TestTokenRoundTrip:
    def test_access_token_round_trips(self, auth):
        user = {"id": "u1", "email": "ada@example.com", "role": "ADMIN"}
        token = auth.create_token(user, "access")
        payload = auth.decode_token(token, expected_type="access")
        assert payload["sub"] == "u1"
        assert payload["email"] == "ada@example.com"
        assert payload["role"] == "ADMIN"
        assert payload["type"] == "access"

    def test_refresh_token_round_trips_and_outlives_access(self, auth):
        user = {"id": "u1", "email": "ada@example.com", "role": "VIEWER"}
        token = auth.create_token(user, "refresh")
        payload = auth.decode_token(token, expected_type="refresh")
        assert payload["type"] == "refresh"
        assert payload["exp"] - payload["iat"] == auth.REFRESH_TOKEN_TTL
        assert auth.REFRESH_TOKEN_TTL > auth.ACCESS_TOKEN_TTL

    def test_decoding_with_the_wrong_expected_type_is_rejected(self, auth):
        user = {"id": "u1", "email": "ada@example.com", "role": "VIEWER"}
        refresh_token = auth.create_token(user, "refresh")
        with pytest.raises(auth.UnauthorizedError):
            auth.decode_token(refresh_token, expected_type="access")

    def test_garbage_token_is_invalid(self, auth):
        with pytest.raises(auth.UnauthorizedError) as excinfo:
            auth.decode_token("this-is-not-a-jwt")
        assert excinfo.value.code == "token_invalid"

    def test_expired_token_is_rejected_with_specific_code(self, auth):
        now = int(time.time())
        payload = {
            "sub": "u1",
            "email": "ada@example.com",
            "role": "VIEWER",
            "type": "access",
            "iat": now - 7200,
            "exp": now - 3600,
        }
        expired_token = jwt.encode(payload, auth._secret(), algorithm=auth.ALGORITHM)
        with pytest.raises(auth.UnauthorizedError) as excinfo:
            auth.decode_token(expired_token)
        assert excinfo.value.code == "token_expired"

    def test_token_signed_with_a_different_secret_is_rejected(self, auth):
        payload = {"sub": "u1", "email": "x@example.com", "role": "VIEWER", "type": "access",
                   "iat": int(time.time()), "exp": int(time.time()) + 3600}
        forged = jwt.encode(payload, "not-the-real-secret", algorithm=auth.ALGORITHM)
        with pytest.raises(auth.UnauthorizedError):
            auth.decode_token(forged)


class TestTokenFromEvent:
    def test_reads_bearer_token_from_authorization_header(self, auth):
        event = {"headers": {"authorization": "Bearer abc123"}}
        assert auth._token_from_event(event) == "abc123"

    def test_header_without_bearer_prefix_is_ignored(self, auth):
        event = {"headers": {"authorization": "abc123"}}
        assert auth._token_from_event(event) is None

    def test_local_query_string_fallback_when_header_missing(self, auth, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        event = {"headers": {}, "queryStringParameters": {"token": "from-query"}}
        assert auth._token_from_event(event) == "from-query"

    def test_query_string_fallback_disabled_outside_local(self, auth, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "false")
        event = {"headers": {}, "queryStringParameters": {"token": "from-query"}}
        assert auth._token_from_event(event) is None

    def test_header_takes_priority_over_query_string(self, auth, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        event = {"headers": {"authorization": "Bearer from-header"}, "queryStringParameters": {"token": "from-query"}}
        assert auth._token_from_event(event) == "from-header"

    def test_nothing_present_returns_none(self, auth):
        assert auth._token_from_event({"headers": {}}) is None


class TestCurrentUser:
    def test_valid_token_yields_user_dict(self, auth):
        token = auth.create_token({"id": "u1", "email": "ada@example.com", "role": "MANAGER"})
        event = {"headers": {"authorization": f"Bearer {token}"}}
        assert auth.current_user(event) == {"id": "u1", "email": "ada@example.com", "role": "MANAGER"}

    def test_missing_token_raises_unauthorized(self, auth):
        with pytest.raises(auth.UnauthorizedError):
            auth.current_user({"headers": {}})


class TestAuthorize:
    def _event_for(self, auth, role, method="GET"):
        token = auth.create_token({"id": "u1", "email": "ada@example.com", "role": role})
        return {
            "headers": {"authorization": f"Bearer {token}"},
            "requestContext": {"http": {"method": method}},
        }

    def test_uses_default_permissions_when_none_given(self, auth):
        event = self._event_for(auth, "VIEWER", "GET")
        user = auth.authorize(event)
        assert user["role"] == "VIEWER"

    def test_default_permissions_forbid_viewer_from_deleting(self, auth):
        event = self._event_for(auth, "VIEWER", "DELETE")
        with pytest.raises(auth.ForbiddenError):
            auth.authorize(event)

    def test_custom_permissions_are_respected(self, auth):
        permissions = {"GET": ("ADMIN",)}
        event = self._event_for(auth, "MANAGER", "GET")
        with pytest.raises(auth.ForbiddenError):
            auth.authorize(event, permissions)

        admin_event = self._event_for(auth, "ADMIN", "GET")
        assert auth.authorize(admin_event, permissions)["role"] == "ADMIN"

    def test_forbidden_error_message_names_role_and_method(self, auth):
        event = self._event_for(auth, "VIEWER", "DELETE")
        with pytest.raises(auth.ForbiddenError) as excinfo:
            auth.authorize(event)
        assert "VIEWER" in str(excinfo.value)
        assert "DELETE" in str(excinfo.value)


class TestProtectedDecorator:
    def test_injects_the_authorised_user_as_a_kwarg(self, auth):
        @auth.protected()
        def handler(event, context, user=None):
            return user

        event = {
            "headers": {"authorization": f"Bearer {auth.create_token({'id': 'u1', 'email': 'a@b.com', 'role': 'ADMIN'})}"},
            "requestContext": {"http": {"method": "GET"}},
        }
        result = handler(event, {})
        assert result["role"] == "ADMIN"

    def test_preserves_the_wrapped_functions_name(self, auth):
        @auth.protected()
        def my_handler(event, context, user=None):
            return user

        assert my_handler.__name__ == "my_handler"

    def test_raises_before_calling_the_wrapped_function_when_unauthorized(self, auth):
        calls = []

        @auth.protected(permissions={"GET": ("ADMIN",)})
        def handler(event, context, user=None):
            calls.append(user)
            return user

        event = {
            "headers": {"authorization": f"Bearer {auth.create_token({'id': 'u1', 'email': 'a@b.com', 'role': 'VIEWER'})}"},
            "requestContext": {"http": {"method": "GET"}},
        }
        with pytest.raises(auth.ForbiddenError):
            handler(event, {})
        assert calls == []
