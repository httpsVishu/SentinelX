"""Shared pytest setup.

The tests run against a real PostgreSQL database, because the app depends on
pgcrypto, native enum types, ARRAY and JSONB columns and database-level
constraints that SQLite cannot reproduce.

How isolation works:
  - At the start of a run a database named <name>_test is dropped and created
    again, then built with `alembic upgrade head`. That exercises the real
    migrations on every run, and the development database is never touched.
  - Each test runs inside one outer transaction on one connection. The app
    calls commit() freely, but the session is configured to turn those commits
    into savepoints, so everything is rolled back when the test ends.
  - Code that opens its own session (Celery tasks, the mock scanner) is
    pointed at the same connection, so it sees the test's data.
  - Celery .delay() is replaced with a recorder, so nothing needs Redis. A new
    task that the API calls with .delay() must be added to `task_calls` below.
"""
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# ---- Environment. Must be set before any `app` module is imported. ----
os.environ.setdefault("PGCRYPTO_KEY", "test-only-pgcrypto-key")
os.environ.setdefault("JWT_SECRET_KEY", "test-only-jwt-secret-key-for-hs256-signing")
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://sentinelx:sentinelx_dev_password@localhost:5432/sentinelx"
)
for _key, _value in {
    "SCANNER_MODE": "mock",
    "EARLY_AGENT_LLM_MODE": "mock",
    "LATE_AGENT_LLM_MODE": "mock",
    "NOTIFICATION_MODE": "dev_console",
    "MOCK_FIXES_REQUIRED": "1",
}.items():
    os.environ[_key] = _value

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402
from sqlalchemy.exc import OperationalError  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

_base_url = make_url(os.environ["DATABASE_URL"])
_base_name = _base_url.database or "sentinelx"
TEST_DATABASE = _base_name if _base_name.endswith("_test") else f"{_base_name}_test"
os.environ["DATABASE_URL"] = _base_url.set(database=TEST_DATABASE).render_as_string(hide_password=False)
_ADMIN_URL = _base_url.set(database="postgres")

from tests import factories  # noqa: E402  (imports app modules, so it must come after the env setup)

# Modules that open their own session with `from app.database import SessionLocal`.
_SESSION_FACTORY_USERS = [
    "app.scanners.mock_scanner.SessionLocal",
    "app.tasks.scan_tasks.SessionLocal",
    "app.tasks.deadline_tasks.SessionLocal",
    "app.tasks.verification_tasks.SessionLocal",
    "app.tasks.notification_tasks.SessionLocal",
]


def _recreate_test_database() -> None:
    # Safety: never drop anything that is not clearly a test database.
    assert TEST_DATABASE.endswith("_test")
    admin = create_engine(_ADMIN_URL, isolation_level="AUTOCOMMIT")
    try:
        with admin.connect() as connection:
            connection.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DATABASE}" WITH (FORCE)'))
            connection.execute(text(f'CREATE DATABASE "{TEST_DATABASE}"'))
    finally:
        admin.dispose()


def _run_migrations() -> None:
    from alembic import command
    from alembic.config import Config

    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    command.upgrade(config, "head")


@pytest.fixture(scope="session")
def engine():
    try:
        _recreate_test_database()
    except OperationalError as exc:
        pytest.exit(
            "Cannot reach PostgreSQL to create the test database. "
            "Run the tests with `make test` so they run inside the Compose network.\n"
            f"Details: {exc.orig}",
            returncode=2,
        )
    _run_migrations()

    from app.database import engine as app_engine

    yield app_engine
    app_engine.dispose()


@pytest.fixture()
def db(engine, monkeypatch) -> Iterator[Session]:
    connection = engine.connect()
    outer = connection.begin()
    session_factory = sessionmaker(
        bind=connection, autoflush=False, join_transaction_mode="create_savepoint"
    )
    session = session_factory()

    for target in _SESSION_FACTORY_USERS:
        monkeypatch.setattr(target, session_factory)

    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        connection.close()


@pytest.fixture(autouse=True)
def task_calls(monkeypatch) -> list[tuple[str, tuple]]:
    """Records Celery .delay() calls instead of sending them to a broker.
    Each entry is (task name, positional args)."""
    from app.tasks.notification_tasks import notify_scan_failed, notify_vendor_of_ticket_change
    from app.tasks.scan_tasks import execute_scan
    from app.tasks.verification_tasks import run_verification_scan

    calls: list[tuple[str, tuple]] = []

    def recorder(task_name: str):
        def delay(*args, **kwargs):
            calls.append((task_name, args))

        return delay

    for task in (execute_scan, run_verification_scan, notify_scan_failed, notify_vendor_of_ticket_change):
        monkeypatch.setattr(task, "delay", recorder(task.name))
    return calls


@pytest.fixture(autouse=True)
def approval_calls(db, monkeypatch) -> list[tuple]:
    """The approval task opens its own session and would otherwise call a
    broker. Point it at the test connection and record its .delay() calls."""
    from app.tasks.approval_tasks import run_post_approval

    factory = sessionmaker(bind=db.get_bind(), autoflush=False, join_transaction_mode="create_savepoint")
    monkeypatch.setattr("app.tasks.approval_tasks.SessionLocal", factory)

    calls: list[tuple] = []
    monkeypatch.setattr(run_post_approval, "delay", lambda *args, **kwargs: calls.append(args))
    return calls


@pytest.fixture()
def client(db) -> Iterator[TestClient]:
    from app.database import get_db
    from app.main import app

    def use_test_session():
        yield db

    app.dependency_overrides[get_db] = use_test_session
    try:
        # Not used as a context manager on purpose, so startup hooks do not run.
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ---- A small world most tests start from ----

@pytest.fixture()
def dept(db):
    return factories.make_department(db)


@pytest.fixture()
def admin(db, dept):
    return factories.make_admin(db, dept)


@pytest.fixture()
def vendor_a(db, dept):
    return factories.make_vendor(db, dept, name="Vendor A")


@pytest.fixture()
def vendor_b(db, dept):
    return factories.make_vendor(db, dept, name="Vendor B")


@pytest.fixture()
def vendor_a_user(db, vendor_a):
    return factories.make_vendor_user(db, vendor_a)


@pytest.fixture()
def vendor_b_user(db, vendor_b):
    return factories.make_vendor_user(db, vendor_b)