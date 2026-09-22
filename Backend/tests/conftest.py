"""
Shared pytest fixtures.

Points the app at a dedicated MySQL test database (never the dev database)
and forces FORCE_MOCK_PROVIDERS=true *before* any app module is imported,
so the whole suite runs offline with MockProvider - no real Teams/Slack/
SMTP credentials or network access needed.

Requires a MySQL server reachable with the settings below (override via
env vars, e.g. in CI) and a `notification_test_db` database already
created:
    CREATE DATABASE IF NOT EXISTS notification_test_db CHARACTER SET utf8mb4;
"""
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent

os.environ.setdefault("MYSQL_HOST", "127.0.0.1")
os.environ.setdefault("MYSQL_PORT", "3306")
os.environ.setdefault("MYSQL_USER", "root")
os.environ.setdefault("MYSQL_PASSWORD", "rootpass")
os.environ["MYSQL_DATABASE"] = "notification_test_db"  # always this DB in tests, never the dev one
os.environ["FORCE_MOCK_PROVIDERS"] = "true"
os.environ["WEBHOOK_SHARED_SECRET"] = "test-secret"

sys.path.insert(0, str(BACKEND_DIR))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import main  # noqa: E402
from app.db import _connect  # noqa: E402


def _reset_schema():
    """Drop and recreate all tables so every test starts from empty."""
    connection = _connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
            cursor.execute("DROP TABLE IF EXISTS notification_deliveries")
            cursor.execute("DROP TABLE IF EXISTS notifications")
            cursor.execute("DROP TABLE IF EXISTS channel_threads")
            cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        connection.commit()
    finally:
        connection.close()


@pytest.fixture
def client():
    """A TestClient bound to a freshly emptied MySQL schema for every test."""
    _reset_schema()
    with TestClient(main.app) as test_client:  # triggers init_db() via lifespan
        yield test_client
    _reset_schema()
