"""
Plain data containers for a notification and its per-channel deliveries -
no ORM. These are just typed shapes; app/repositories/notification_repository.py
fills them in by hand from raw SQL query results (dict rows from PyMySQL's
DictCursor), and app/schemas.py converts them straight to API responses
(Pydantic's `from_attributes` works on any object with matching attributes,
a dataclass included - it doesn't require an ORM).
"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NotificationDelivery:
    id: str
    notification_id: str
    channel: str  # TEAMS / EMAIL / SLACK
    destination: str
    status: str  # PENDING / SENT / DELIVERED / FAILED
    provider: str
    provider_message_id: str | None
    retry_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime


@dataclass
class Notification:
    id: str
    title: str
    message: str
    created_at: datetime
    deliveries: list[NotificationDelivery] = field(default_factory=list)
