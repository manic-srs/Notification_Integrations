"""
Raw MySQL connection management via PyMySQL - no ORM.

There is no separate "SQLAlchemy database" - every value the app reads or
writes lives in real MySQL tables (see schema.sql). This file is only the
thin connection layer: it opens a PyMySQL connection per request and hands
it to the repository layer (app/repositories/notification_repository.py),
which is the only place that writes SQL.
"""
import logging
import socket
import time

import pymysql
import pymysql.cursors

from app.config import get_settings

settings = get_settings()
logger = logging.getLogger("notification_app")


def _connect():
    return pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def _connect_with_retry(max_attempts: int = 10, delay_seconds: float = 1.5, sleep_fn=time.sleep):
    """Only used by init_db() at startup - retries a transient connection
    failure (MySQL still finishing InnoDB startup, or - under Docker
    Compose - the container's DNS not being fully ready the instant a
    freshly created container starts, even though the mysql service's own
    healthcheck already passed) instead of crashing the whole app on the
    very first attempt. Every other place that opens a connection
    (get_db(), the per-request dependency) intentionally does NOT retry -
    by the time a request comes in, startup has already succeeded once, so
    a fresh failure there is a real problem, not a startup race."""
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return _connect()
        except (pymysql.err.OperationalError, socket.gaierror, OSError) as exc:
            last_error = exc
            if attempt < max_attempts:
                logger.warning(
                    "MySQL not reachable yet (attempt %d/%d): %s - retrying in %.1fs",
                    attempt,
                    max_attempts,
                    exc,
                    delay_seconds,
                )
                sleep_fn(delay_seconds)
    assert last_error is not None
    raise last_error


class Database:
    """Thin wrapper around one PyMySQL connection for the lifetime of a
    single request. Every query anywhere in the app goes through
    `execute()` - there is no ORM generating SQL behind the scenes."""

    def __init__(self, connection):
        self._conn = connection

    def execute(self, sql: str, params=None):
        cursor = self._conn.cursor()
        cursor.execute(sql, params or ())
        return cursor

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()


def get_db():
    """FastAPI dependency: one connection per request, rolled back on
    error, always closed afterward."""
    connection = _connect()
    db = Database(connection)
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create the tables if they don't exist yet. Same DDL as schema.sql,
    run directly through PyMySQL - kept in sync by hand since there is no
    ORM to generate it. Uses _connect_with_retry (see above) since this is
    the one connection attempt that runs at app startup, before anything
    else has proven MySQL is actually reachable yet."""
    connection = _connect_with_retry()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS notifications (
                    id          VARCHAR(36)  NOT NULL PRIMARY KEY,
                    title       VARCHAR(255) NOT NULL,
                    message     TEXT         NOT NULL,
                    created_at  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
                ) ENGINE=InnoDB
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS notification_deliveries (
                    id                   VARCHAR(36)  NOT NULL PRIMARY KEY,
                    notification_id      VARCHAR(36)  NOT NULL,
                    channel              VARCHAR(20)  NOT NULL,
                    destination          VARCHAR(255) NOT NULL,
                    status               VARCHAR(20)  NOT NULL DEFAULT 'PENDING',
                    provider             VARCHAR(50)  NOT NULL,
                    provider_message_id  VARCHAR(255) NULL,
                    retry_count          INT          NOT NULL DEFAULT 0,
                    error_message        TEXT         NULL,
                    created_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                    CONSTRAINT fk_notification_deliveries_notification
                        FOREIGN KEY (notification_id) REFERENCES notifications(id) ON DELETE CASCADE,
                    INDEX idx_notification_deliveries_notification_id (notification_id),
                    INDEX idx_notification_deliveries_channel (channel),
                    INDEX idx_notification_deliveries_status (status),
                    INDEX idx_notification_deliveries_provider_message_id (provider_message_id)
                ) ENGINE=InnoDB
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS channel_threads (
                    channel      VARCHAR(20)  NOT NULL,
                    destination  VARCHAR(255) NOT NULL,
                    thread_key   VARCHAR(512) NOT NULL,
                    created_at   DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (channel, destination)
                ) ENGINE=InnoDB
                """
            )
        connection.commit()
    finally:
        connection.close()
