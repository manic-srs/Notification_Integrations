"""
All direct database access lives here (spec's "Repository/Database
Layer"). Every function below executes raw SQL against MySQL through the
Database wrapper in app/db.py - no ORM, no query-building library. The
service layer never writes SQL itself, it only calls these functions, so
persistence can change without touching business logic.
"""
import uuid
from datetime import datetime, timezone

from app.db import Database
from app.models.notification import Notification, NotificationDelivery


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_delivery(row: dict) -> NotificationDelivery:
    return NotificationDelivery(
        id=row["id"],
        notification_id=row["notification_id"],
        channel=row["channel"],
        destination=row["destination"],
        status=row["status"],
        provider=row["provider"],
        provider_message_id=row["provider_message_id"],
        retry_count=row["retry_count"],
        error_message=row["error_message"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _fetch_deliveries(db: Database, notification_id: str) -> list[NotificationDelivery]:
    cursor = db.execute(
        "SELECT * FROM notification_deliveries WHERE notification_id = %s ORDER BY created_at",
        (notification_id,),
    )
    return [_row_to_delivery(row) for row in cursor.fetchall()]


def create_notification(db: Database, *, title: str, message: str) -> Notification:
    notification_id = str(uuid.uuid4())
    created_at = _now()
    db.execute(
        "INSERT INTO notifications (id, title, message, created_at) VALUES (%s, %s, %s, %s)",
        (notification_id, title, message, created_at),
    )
    return Notification(id=notification_id, title=title, message=message, created_at=created_at, deliveries=[])


def add_delivery(
    db: Database,
    *,
    notification_id: str,
    channel: str,
    destination: str,
    provider: str,
    status: str = "PENDING",
) -> NotificationDelivery:
    delivery_id = str(uuid.uuid4())
    now = _now()
    db.execute(
        """
        INSERT INTO notification_deliveries
            (id, notification_id, channel, destination, status, provider,
             provider_message_id, retry_count, error_message, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, NULL, 0, NULL, %s, %s)
        """,
        (delivery_id, notification_id, channel, destination, status, provider, now, now),
    )
    return NotificationDelivery(
        id=delivery_id,
        notification_id=notification_id,
        channel=channel,
        destination=destination,
        status=status,
        provider=provider,
        provider_message_id=None,
        retry_count=0,
        error_message=None,
        created_at=now,
        updated_at=now,
    )


def get_notification(db: Database, notification_id: str) -> Notification | None:
    cursor = db.execute("SELECT * FROM notifications WHERE id = %s", (notification_id,))
    row = cursor.fetchone()
    if row is None:
        return None
    notification = Notification(id=row["id"], title=row["title"], message=row["message"], created_at=row["created_at"])
    notification.deliveries = _fetch_deliveries(db, notification_id)
    return notification


def get_delivery(db: Database, delivery_id: str) -> NotificationDelivery | None:
    cursor = db.execute("SELECT * FROM notification_deliveries WHERE id = %s", (delivery_id,))
    row = cursor.fetchone()
    return _row_to_delivery(row) if row else None


def find_delivery_by_provider_message_id(db: Database, provider_message_id: str) -> NotificationDelivery | None:
    cursor = db.execute(
        "SELECT * FROM notification_deliveries WHERE provider_message_id = %s", (provider_message_id,)
    )
    row = cursor.fetchone()
    return _row_to_delivery(row) if row else None


def list_notifications(
    db: Database,
    *,
    channel: str | None = None,
    status: str | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Notification], int]:
    where_clauses: list[str] = []
    params: list = []

    needs_join = bool(channel or status or search)
    from_clause = "FROM notifications n"
    if needs_join:
        from_clause += " JOIN notification_deliveries d ON d.notification_id = n.id"

    if channel:
        where_clauses.append("d.channel = %s")
        params.append(channel.upper())
    if status:
        where_clauses.append("d.status = %s")
        params.append(status.upper())
    if search:
        like = f"%{search}%"
        where_clauses.append("(n.title LIKE %s OR n.message LIKE %s OR d.destination LIKE %s OR n.id LIKE %s)")
        params.extend([like, like, like, like])

    where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    total = db.execute(
        f"SELECT COUNT(DISTINCT n.id) AS total {from_clause} {where_sql}", tuple(params)
    ).fetchone()["total"]

    rows = db.execute(
        f"SELECT DISTINCT n.id, n.title, n.message, n.created_at {from_clause} {where_sql} "
        "ORDER BY n.created_at DESC LIMIT %s OFFSET %s",
        tuple(params) + (limit, offset),
    ).fetchall()

    items: list[Notification] = []
    for row in rows:
        notification = Notification(id=row["id"], title=row["title"], message=row["message"], created_at=row["created_at"])
        notification.deliveries = _fetch_deliveries(db, notification.id)
        items.append(notification)

    return items, total


def update_delivery_status(
    db: Database,
    delivery: NotificationDelivery,
    *,
    status: str,
    provider_message_id: str | None = None,
    error_message: str | None = None,
) -> NotificationDelivery:
    """Mutates `delivery` in place and persists the same values in one
    UPDATE. Callers that need to change retry_count (see
    notification_service.py) set `delivery.retry_count` themselves before
    calling this - there is no ORM session to auto-track that change, so
    every field that should be persisted is included in the SQL below."""
    delivery.status = status
    if provider_message_id is not None:
        delivery.provider_message_id = provider_message_id
    # error_message is only ever cleared on a successful transition, never
    # silently dropped, so history keeps the most recent error around.
    if status in ("SENT", "DELIVERED"):
        delivery.error_message = None
    elif error_message is not None:
        delivery.error_message = error_message
    delivery.updated_at = _now()

    db.execute(
        """
        UPDATE notification_deliveries
        SET status = %s, provider_message_id = %s, error_message = %s,
            retry_count = %s, updated_at = %s
        WHERE id = %s
        """,
        (
            delivery.status,
            delivery.provider_message_id,
            delivery.error_message,
            delivery.retry_count,
            delivery.updated_at,
            delivery.id,
        ),
    )
    return delivery


def get_thread_key(db: Database, channel: str, destination: str) -> str | None:
    """The existing thread anchor for this (channel, destination), if any
    prior notification to this recipient already established one."""
    cursor = db.execute(
        "SELECT thread_key FROM channel_threads WHERE channel = %s AND destination = %s",
        (channel, destination),
    )
    row = cursor.fetchone()
    return row["thread_key"] if row else None


def save_thread_key(db: Database, channel: str, destination: str, thread_key: str) -> None:
    """Records the thread anchor the *first* time we see one for this
    (channel, destination) and leaves it alone after that - every later
    notification to the same recipient should keep replying into the same
    original thread, not restart it, so a second call with a different
    value is a deliberate no-op via ON DUPLICATE KEY UPDATE."""
    db.execute(
        """
        INSERT INTO channel_threads (channel, destination, thread_key, created_at)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE thread_key = thread_key
        """,
        (channel, destination, thread_key, _now()),
    )


def stats(db: Database) -> dict:
    total = db.execute("SELECT COUNT(*) AS c FROM notifications").fetchone()["c"]
    rows = db.execute("SELECT status, COUNT(*) AS c FROM notification_deliveries GROUP BY status").fetchall()
    counts = {row["status"]: row["c"] for row in rows}
    return {
        "total": total,
        "pending": counts.get("PENDING", 0),
        "delivered": counts.get("SENT", 0) + counts.get("DELIVERED", 0),
        "failed": counts.get("FAILED", 0),
    }
