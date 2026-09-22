
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import ValidationError

from app.config import Settings, get_settings
from app.db import Database, get_db
from app.schemas import (
    NotificationCreateRequest,
    NotificationListOut,
    NotificationOut,
    StatsOut,
)
from app.services import notification_service as service
from app.webhooks.handler import SUPPORTED_WEBHOOK_PROVIDERS, normalize

logger = logging.getLogger("notification_api")

router = APIRouter()


@router.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


@router.post("/api/notifications", response_model=NotificationOut, status_code=201, tags=["notifications"])
def create_notification(
    payload: NotificationCreateRequest,
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """FR-01: valid request creates a notification and per-channel
    delivery records, then attempts delivery on each channel."""
    notification = service.create_and_send(db, payload, settings)
    return notification


@router.get("/api/notifications", response_model=NotificationListOut, tags=["notifications"])
def list_notifications(
    channel: str | None = Query(None, description="Filter by TEAMS / EMAIL / SLACK"),
    status: str | None = Query(None, description="Filter by PENDING / SENT / DELIVERED / FAILED"),
    q: str | None = Query(None, description="Search title, message, destination or id"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
):
    """FR-11: list and filter notification history."""
    items, total = service.list_notifications(
        db, channel=channel, status=status, search=q, limit=limit, offset=offset
    )
    return NotificationListOut(total=total, items=items)


@router.get("/api/stats", response_model=StatsOut, tags=["notifications"])
def get_stats(db: Database = Depends(get_db)):
    return service.get_stats(db)


@router.get("/api/notifications/{notification_id}", response_model=NotificationOut, tags=["notifications"])
def get_notification(notification_id: str, db: Database = Depends(get_db)):
    try:
        return service.get_notification(db, notification_id)
    except service.NotificationNotFoundError:
        raise HTTPException(status_code=404, detail="Notification not found")


@router.post("/api/notifications/{notification_id}/retry", response_model=NotificationOut, tags=["notifications"])
def retry_notification(
    notification_id: str,
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """FR-09: retry failed channel deliveries for this notification,
    bounded by RETRY_MAX_ATTEMPTS per delivery."""
    try:
        return service.retry_notification(db, notification_id, settings)
    except service.NotificationNotFoundError:
        raise HTTPException(status_code=404, detail="Notification not found")


@router.post("/api/webhooks/{provider}", tags=["webhooks"])
def receive_webhook(
    provider: str,
    payload: dict,
    x_webhook_secret: str | None = Header(default=None),
    db: Database = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    """FR-10/FR-12: provider delivery-status callback. Protected by a
    shared-secret header (spec section 14, "Protect webhook endpoints
    where applicable") and idempotent against duplicate callbacks."""
    if provider.lower() not in SUPPORTED_WEBHOOK_PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider: {provider}")

    try:
        event = normalize(provider, payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())

    try:
        delivery = service.handle_webhook(db, provider, x_webhook_secret, settings, event)
    except service.InvalidWebhookSecretError:
        raise HTTPException(status_code=401, detail="Invalid webhook secret")

    # Unknown notification id -> log safely and return 200 (spec section 13)
    # rather than surfacing an error to whatever is calling the webhook.
    if delivery is None:
        return {"status": "ignored", "reason": "unknown provider_message_id"}
    return {"status": "ok", "delivery_id": delivery.id, "new_status": delivery.status}
