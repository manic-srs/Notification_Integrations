"""
Pydantic request/response models. The create-request shape matches the
"Example request" JSON in the spec (section 8) exactly: per-channel lists,
where Teams/Slack entries use `destination` and Email entries use
`recipient` (+ optional `subject`).
"""
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator



# Requests

class TeamsChannelEntry(BaseModel):
    destination: str = Field(..., min_length=1, description="Teams recipient, e.g. an email address")


class SlackChannelEntry(BaseModel):
    destination: str = Field(..., min_length=1, description="Slack destination: an email address or #channel")


class EmailChannelEntry(BaseModel):
    recipient: EmailStr
    subject: str | None = None


class ChannelsInput(BaseModel):
    teams: list[TeamsChannelEntry] | None = None
    email: list[EmailChannelEntry] | None = None
    slack: list[SlackChannelEntry] | None = None


class NotificationCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    message: str = Field(..., min_length=1)
    channels: ChannelsInput

    @field_validator("channels")
    @classmethod
    def at_least_one_channel(cls, channels: ChannelsInput) -> ChannelsInput:
        if not (channels.teams or channels.email or channels.slack):
            raise ValueError("At least one channel (teams, email or slack) with at least one destination is required")
        return channels



# Responses

class NotificationDeliveryOut(BaseModel):
    id: str
    channel: str
    destination: str
    status: str
    provider: str
    provider_message_id: str | None
    retry_count: int
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class NotificationOut(BaseModel):
    id: str
    title: str
    message: str
    created_at: datetime
    deliveries: list[NotificationDeliveryOut]

    model_config = {"from_attributes": True}


class NotificationListOut(BaseModel):
    total: int
    items: list[NotificationOut]


class StatsOut(BaseModel):
    total: int
    pending: int
    delivered: int
    failed: int


class WebhookEventIn(BaseModel):
    """Generic shape a provider callback is normalized into before being
    handed to the service layer. Real providers vary; app/webhooks/handler.py
    is where provider-specific payloads get translated into this."""

    provider_message_id: str
    status: str  # DELIVERED or FAILED
    error_message: str | None = None
