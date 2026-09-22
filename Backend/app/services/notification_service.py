"""
Core business logic / orchestration (spec's "Notification Service"). This
is the one place that knows the overall flow: create records -> call the
right provider for each channel -> persist independent per-channel status.
It depends only on the repository layer and the provider interface, never
on a specific vendor SDK - see app/providers/factory.py for that mapping.
"""
import logging

from app.config import Settings
from app.db import Database
from app.providers.factory import get_provider
from app.repositories import notification_repository as repo
from app.schemas import NotificationCreateRequest
from app.security import constant_time_equals
from app.services.retry import send_with_retry

logger = logging.getLogger("notification_service")


class NotificationNotFoundError(Exception):
    pass


class InvalidWebhookSecretError(Exception):
    pass


def create_and_send(db: Database, payload: NotificationCreateRequest, settings: Settings):
    """FR-01/02/03/04/05/06/08: create the notification + one delivery
    record per requested destination, then attempt delivery on each
    channel independently so one channel failing never affects another
    (spec section 13, "One channel fails while another succeeds")."""
    notification = repo.create_notification(db, title=payload.title, message=payload.message)

    plan: list[tuple[str, str, str | None]] = []  # (channel, destination, subject)
    if payload.channels.teams:
        plan += [("teams", entry.destination, None) for entry in payload.channels.teams]
    if payload.channels.slack:
        plan += [("slack", entry.destination, None) for entry in payload.channels.slack]
    if payload.channels.email:
        plan += [("email", entry.recipient, entry.subject) for entry in payload.channels.email]

    for channel, destination, subject in plan:
        provider = get_provider(channel, settings)
        channel_upper = channel.upper()
        delivery = repo.add_delivery(
            db,
            notification_id=notification.id,
            channel=channel_upper,
            destination=destination,
            provider=provider.name,
            status="PENDING",
        )

        # Reply into this recipient's existing thread on this channel, if
        # one already exists, instead of starting a new one every time.
        thread_key = repo.get_thread_key(db, channel_upper, destination)

        result, attempts = send_with_retry(
            provider,
            destination=destination,
            title=payload.title,
            message=payload.message,
            subject=subject,
            thread_key=thread_key,
            max_attempts=settings.retry_max_attempts,
            backoff_base_seconds=settings.retry_backoff_base_seconds,
        )

        # attempts==1 -> no retry happened -> retry_count stays 0.
        delivery.retry_count = attempts - 1
        repo.update_delivery_status(
            db,
            delivery,
            status=result.status,
            provider_message_id=result.provider_message_id,
            error_message=result.error_message,
        )
        if result.thread_key:
            # First time for this recipient this just records the new
            # thread's anchor; every time after, it's a no-op (see
            # save_thread_key) since the anchor never changes.
            repo.save_thread_key(db, channel_upper, destination, result.thread_key)
        notification.deliveries.append(delivery)

    db.commit()
    return notification


def get_notification(db: Database, notification_id: str):
    notification = repo.get_notification(db, notification_id)
    if notification is None:
        raise NotificationNotFoundError(notification_id)
    return notification


def list_notifications(db: Database, *, channel=None, status=None, search=None, limit=50, offset=0):
    return repo.list_notifications(db, channel=channel, status=status, search=search, limit=limit, offset=offset)


def get_stats(db: Database):
    return repo.stats(db)


def retry_notification(db: Database, notification_id: str, settings: Settings):
    """POST /api/notifications/{id}/retry - re-attempt every FAILED
    delivery under this notification (FR-09: bounded, never indefinite)."""
    notification = repo.get_notification(db, notification_id)
    if notification is None:
        raise NotificationNotFoundError(notification_id)

    for delivery in notification.deliveries:
        if delivery.status != "FAILED":
            continue

        remaining = max(settings.retry_max_attempts - delivery.retry_count, 1)
        provider = get_provider(delivery.channel.lower(), settings)
        thread_key = repo.get_thread_key(db, delivery.channel, delivery.destination)

        result, attempts = send_with_retry(
            provider,
            destination=delivery.destination,
            title=notification.title,
            message=notification.message,
            subject=None,
            thread_key=thread_key,
            max_attempts=remaining,
            backoff_base_seconds=settings.retry_backoff_base_seconds,
        )

        delivery.retry_count += attempts
        repo.update_delivery_status(
            db,
            delivery,
            status=result.status,
            provider_message_id=result.provider_message_id,
            error_message=result.error_message,
        )
        if result.thread_key:
            repo.save_thread_key(db, delivery.channel, delivery.destination, result.thread_key)

    db.commit()
    return notification


def handle_webhook(db: Database, provider: str, secret_header: str | None, settings: Settings, event):
    """POST /api/webhooks/{provider} - provider delivery-confirmation
    callback. FR-10/FR-12: updates final status, is idempotent against
    duplicate callbacks, and never raises on an unknown notification id -
    it just logs and returns cleanly (spec section 13)."""
    if not constant_time_equals(secret_header or "", settings.webhook_shared_secret):
        raise InvalidWebhookSecretError()

    delivery = repo.find_delivery_by_provider_message_id(db, event.provider_message_id)
    if delivery is None:
        logger.info("webhook from %s referenced unknown provider_message_id=%s - ignoring", provider, event.provider_message_id)
        return None

    if delivery.status == event.status:
        # Duplicate callback for a status we've already recorded - no-op,
        # but still returns 200 so the provider doesn't keep retrying.
        return delivery

    if delivery.status == "DELIVERED":
        # Already terminal and confirmed delivered - a late/duplicate
        # FAILED callback for the same message must not un-deliver it.
        return delivery

    repo.update_delivery_status(db, delivery, status=event.status, error_message=event.error_message)
    db.commit()
    return delivery
