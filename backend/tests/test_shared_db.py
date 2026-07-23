"""Direct unit tests for backend/_shared/db.py — the connection-lifecycle
and query-helper code every service's repository.py builds on.

Only pg8000.dbapi.connect is mocked (a real network call); everything else
in this module — connection caching/health-checking, the cursor context
manager's commit/rollback/reset behavior, row-to-dict mapping, SQL-script
splitting, and SQLSTATE classification — runs for real. Loaded via any one
service (teams-service here) since every service's _shared/db.py is a
byte-identical synced copy (see backend/_shared/__init__.py).
"""

import ssl
from unittest.mock import MagicMock

import pytest


@pytest.fixture(params=["teams-service", "allocations-service"])
def shared(request, load_service):
    """Parametrized across every service in scope so this suite actually
    exercises each one's own vendored _shared/db.py copy — coverage.py
    tracks by file path, so a service whose copy never runs shows as
    untested even though the source is byte-identical everywhere."""
    return load_service(request.param)


@pytest.fixture
def db(shared):
    return shared.db


@pytest.fixture
def fake_connect(db, monkeypatch):
    """_shared/db.py does `import pg8000.dbapi` and calls
    `pg8000.dbapi.connect(...)` at call time (not a `from...import`
    binding), so patching the attribute on the module object it already
    holds affects every call inside get_connection()."""
    mock = MagicMock()
    monkeypatch.setattr(db.pg8000.dbapi, "connect", mock)
    return mock


class TestIsLocal:
    def test_true_when_env_var_set(self, db, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        assert db.is_local() is True

    def test_false_when_unset(self, db, monkeypatch):
        monkeypatch.delenv("IS_LOCAL", raising=False)
        assert db.is_local() is False

    def test_case_insensitive(self, db, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "TRUE")
        assert db.is_local() is True


class TestConnectKwargs:
    def test_reads_from_environment(self, db, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        monkeypatch.setenv("POSTGRES_HOST", "db.example")
        monkeypatch.setenv("POSTGRES_PORT", "5433")
        monkeypatch.setenv("POSTGRES_USER", "alice")
        monkeypatch.setenv("POSTGRES_PASS", "secret")
        monkeypatch.setenv("POSTGRES_NAME", "acme")

        kwargs = db._connect_kwargs()

        assert kwargs["host"] == "db.example"
        assert kwargs["port"] == 5433
        assert kwargs["user"] == "alice"
        assert kwargs["password"] == "secret"
        assert kwargs["database"] == "acme"
        assert "ssl_context" not in kwargs

    def test_defaults_when_unset(self, db, monkeypatch):
        for var in ("POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_PASS", "POSTGRES_NAME"):
            monkeypatch.delenv(var, raising=False)
        monkeypatch.setenv("IS_LOCAL", "true")

        kwargs = db._connect_kwargs()

        assert kwargs["host"] == "localhost"
        assert kwargs["port"] == 5432

    def test_adds_unverified_ssl_context_when_not_local(self, db, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "false")
        kwargs = db._connect_kwargs()
        assert kwargs["ssl_context"].verify_mode == ssl.CERT_NONE
        assert kwargs["ssl_context"].check_hostname is False


class TestConnectionHealth:
    def test_healthy_when_cursor_executes_cleanly(self, db):
        fake_connection = MagicMock()
        assert db._connection_is_healthy(fake_connection) is True

    def test_unhealthy_when_cursor_raises(self, db):
        fake_connection = MagicMock()
        fake_connection.cursor.side_effect = RuntimeError("connection reset")
        assert db._connection_is_healthy(fake_connection) is False


class TestGetConnection:
    def test_opens_a_fresh_connection_when_none_cached(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_conn = MagicMock()
        fake_connect.return_value = fake_conn

        result = db.get_connection()

        assert result is fake_conn
        assert fake_conn.autocommit is False
        fake_connect.assert_called_once()

    def test_reuses_a_healthy_cached_connection(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_connect.return_value = MagicMock()

        first = db.get_connection()
        second = db.get_connection()

        assert first is second
        fake_connect.assert_called_once()

    def test_reconnects_when_cached_connection_is_unhealthy(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        dead_conn = MagicMock()
        dead_conn.cursor.side_effect = RuntimeError("gone")
        fresh_conn = MagicMock()
        fake_connect.side_effect = [dead_conn, fresh_conn]

        first = db.get_connection()
        second = db.get_connection()

        assert first is dead_conn
        assert second is fresh_conn
        assert fake_connect.call_count == 2

    def test_connect_failure_raises_api_error_and_clears_cache(self, shared, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_connect.side_effect = RuntimeError("connection refused")

        with pytest.raises(shared.http.ApiError):
            db.get_connection()

        assert db._connection is None


class TestResetConnection:
    def test_closes_and_clears_cached_connection(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_conn = MagicMock()
        fake_connect.return_value = fake_conn
        db.get_connection()

        db.reset_connection()

        fake_conn.close.assert_called_once()
        assert db._connection is None

    def test_swallows_errors_from_close(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_conn = MagicMock()
        fake_conn.close.side_effect = RuntimeError("already closed")
        fake_connect.return_value = fake_conn
        db.get_connection()

        db.reset_connection()  # must not raise

        assert db._connection is None

    def test_noop_when_nothing_cached(self, db):
        db.reset_connection()  # must not raise
        assert db._connection is None


class TestCursorContextManager:
    def test_commits_when_commit_true(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_conn = MagicMock()
        fake_connect.return_value = fake_conn

        with db.cursor(commit=True):
            pass

        fake_conn.commit.assert_called_once()
        fake_conn.rollback.assert_not_called()

    def test_rolls_back_when_commit_false(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_conn = MagicMock()
        fake_connect.return_value = fake_conn

        with db.cursor(commit=False):
            pass

        fake_conn.rollback.assert_called_once()
        fake_conn.commit.assert_not_called()

    def test_rolls_back_and_reraises_on_exception(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_conn = MagicMock()
        fake_connect.return_value = fake_conn

        with pytest.raises(ValueError):
            with db.cursor():
                raise ValueError("boom")

        fake_conn.rollback.assert_called_once()

    def test_resets_connection_when_rollback_itself_fails(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_conn = MagicMock()
        fake_conn.rollback.side_effect = RuntimeError("connection already gone")
        fake_connect.return_value = fake_conn

        with pytest.raises(ValueError):
            with db.cursor():
                raise ValueError("boom")

        assert db._connection is None

    def test_closes_cursor_even_when_cursor_close_raises(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_conn = MagicMock()
        fake_cur = MagicMock()
        fake_cur.close.side_effect = RuntimeError("already closed")
        fake_conn.cursor.return_value = fake_cur
        fake_connect.return_value = fake_conn

        with db.cursor():
            pass  # must not raise despite cur.close() failing in the finally block


class TestToDicts:
    def test_maps_tuples_onto_column_names(self, db):
        fake_cur = MagicMock()
        fake_cur.description = [("id",), ("name",)]
        fake_cur.fetchall.return_value = [(1, "Alice"), (2, "Bob")]
        assert db._to_dicts(fake_cur) == [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]

    def test_decodes_byte_column_names(self, db):
        fake_cur = MagicMock()
        fake_cur.description = [(b"id",)]
        fake_cur.fetchall.return_value = [(1,)]
        assert db._to_dicts(fake_cur) == [{"id": 1}]

    def test_empty_list_when_no_description(self, db):
        fake_cur = MagicMock()
        fake_cur.description = None
        assert db._to_dicts(fake_cur) == []


class TestToDict:
    def test_returns_first_row_only(self, db):
        fake_cur = MagicMock()
        fake_cur.description = [("id",)]
        fake_cur.fetchall.return_value = [(1,), (2,)]
        assert db._to_dict(fake_cur) == {"id": 1}

    def test_none_when_no_rows(self, db):
        fake_cur = MagicMock()
        fake_cur.description = [("id",)]
        fake_cur.fetchall.return_value = []
        assert db._to_dict(fake_cur) is None


class TestQueryHelpers:
    def test_query_all_executes_maps_rows_and_never_commits(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_conn = MagicMock()
        fake_cur = MagicMock()
        fake_cur.description = [("id",)]
        fake_cur.fetchall.return_value = [(1,), (2,)]
        fake_conn.cursor.return_value = fake_cur
        fake_connect.return_value = fake_conn

        result = db.query_all("SELECT id FROM x WHERE y = %s", ("a",))

        assert result == [{"id": 1}, {"id": 2}]
        fake_cur.execute.assert_called_once_with("SELECT id FROM x WHERE y = %s", ("a",))
        fake_conn.rollback.assert_called_once()
        fake_conn.commit.assert_not_called()

    def test_query_one_returns_none_on_empty_result(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_conn = MagicMock()
        fake_cur = MagicMock()
        fake_cur.description = [("id",)]
        fake_cur.fetchall.return_value = []
        fake_conn.cursor.return_value = fake_cur
        fake_connect.return_value = fake_conn

        assert db.query_one("SELECT id FROM x") is None

    def test_execute_commits_and_returns_returning_row(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_conn = MagicMock()
        fake_cur = MagicMock()
        fake_cur.description = [("id",)]
        fake_cur.fetchall.return_value = [(1,)]
        fake_conn.cursor.return_value = fake_cur
        fake_connect.return_value = fake_conn

        result = db.execute("INSERT INTO x (a) VALUES (%s) RETURNING id", ("a",))

        assert result == {"id": 1}
        fake_conn.commit.assert_called_once()

    def test_execute_without_description_returns_rowcount(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_conn = MagicMock()
        fake_cur = MagicMock()
        fake_cur.description = None
        fake_cur.rowcount = 3
        fake_conn.cursor.return_value = fake_cur
        fake_connect.return_value = fake_conn

        result = db.execute("DELETE FROM x", returning=False)

        assert result == 3


class TestSplitStatements:
    def test_splits_on_semicolons(self, db):
        sql = "CREATE TABLE a (id int); CREATE TABLE b (id int);"
        assert db.split_statements(sql) == ["CREATE TABLE a (id int)", "CREATE TABLE b (id int)"]

    def test_strips_trailing_line_comments(self, db):
        sql = "SELECT 1; -- a trailing comment\nSELECT 2;"
        assert db.split_statements(sql) == ["SELECT 1", "SELECT 2"]

    def test_ignores_blank_statements(self, db):
        sql = "SELECT 1;;;   ;\nSELECT 2;"
        assert db.split_statements(sql) == ["SELECT 1", "SELECT 2"]

    def test_comment_only_line_contributes_nothing(self, db):
        sql = "-- just a comment\nSELECT 1;"
        assert db.split_statements(sql) == ["SELECT 1"]


class TestExecuteScript:
    def test_runs_every_statement_in_one_transaction_and_returns_count(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_conn = MagicMock()
        fake_cur = MagicMock()
        fake_conn.cursor.return_value = fake_cur
        fake_connect.return_value = fake_conn

        count = db.execute_script("CREATE TABLE a (id int); CREATE TABLE b (id int);")

        assert count == 2
        assert fake_cur.execute.call_count == 2
        fake_conn.commit.assert_called_once()


class TestSqlstate:
    def test_extracts_code_from_dict_arg(self, db):
        assert db.sqlstate(Exception({"C": "23505"})) == "23505"

    def test_none_when_no_dict_arg_present(self, db):
        assert db.sqlstate(Exception("plain message")) is None

    def test_is_unique_violation_true_for_23505(self, db):
        assert db.is_unique_violation(Exception({"C": "23505"})) is True

    def test_is_unique_violation_false_for_other_codes(self, db):
        assert db.is_unique_violation(Exception({"C": "23503"})) is False


class TestExists:
    def test_rejects_a_table_not_on_the_whitelist(self, db):
        with pytest.raises(ValueError):
            db.exists("pg_shadow", "some-id")

    def test_true_when_a_row_is_found(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_conn = MagicMock()
        fake_cur = MagicMock()
        fake_cur.description = [("ok",)]
        fake_cur.fetchall.return_value = [(1,)]
        fake_conn.cursor.return_value = fake_cur
        fake_connect.return_value = fake_conn

        assert db.exists("users", "u1") is True

    def test_false_when_no_row_is_found(self, db, fake_connect, monkeypatch):
        monkeypatch.setenv("IS_LOCAL", "true")
        fake_conn = MagicMock()
        fake_cur = MagicMock()
        fake_cur.description = [("ok",)]
        fake_cur.fetchall.return_value = []
        fake_conn.cursor.return_value = fake_cur
        fake_connect.return_value = fake_conn

        assert db.exists("users", "missing") is False
