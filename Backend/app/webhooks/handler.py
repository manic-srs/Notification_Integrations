"""
Provider callback normalization (spec FR-10: "Provider status events can
update delivery status where supported").

None of the three mandatory channels has a delivery-confirmation webhook we
can rely on out of the box for this MVP:
  - the Teams Power Automate flow replies synchronously and has no
    outbound "delivered" callback,
  - the Slack Bot Token scopes we use don't include Events API access,
  - plain SMTP has no delivery webhook at all.

So POST /api/webhooks/{provider} accepts one normalized JSON shape
(WebhookEventIn: provider_message_id/status/error_message) rather than
guessing a vendor payload we can't observe. `provider` in the URL is kept
for routing/logging and so a real provider-specific parser can be dropped
in here later without touching the API route or the service layer.
"""
from app.schemas import WebhookEventIn

SUPPORTED_WEBHOOK_PROVIDERS = ("teams", "slack", "email")


def normalize(provider: str, payload: dict) -> WebhookEventIn:
    """Provider-specific payloads would be translated to WebhookEventIn
    here. For now every provider uses the same normalized shape."""
    return WebhookEventIn(**payload)
