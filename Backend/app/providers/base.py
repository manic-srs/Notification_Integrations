"""
Common interface every channel adapter implements. The Notification
Service (app/services/notification_service.py) only ever talks to this
interface - it never contains Teams/Slack/SMTP-specific code, so a new
channel is just a new class that implements `send()` (spec section 9/21).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ProviderResult:
    """What every adapter hands back, regardless of channel."""

    success: bool
    status: str  # "SENT" or "FAILED"
    provider_message_id: str | None = None
    error_message: str | None = None
    # Only meaningful when success is False: should the caller retry?
    retryable: bool = False
    # The anchor for this recipient's running conversation thread (Slack
    # thread_ts, Email Message-ID, ...) after this send. None if the
    # channel has no threading concept (Teams) or the send failed before
    # producing one. The service layer persists this via
    # notification_repository.save_thread_key so the *next* notification to
    # the same (channel, destination) can pass it back in as `thread_key`.
    thread_key: str | None = None


class NotificationProvider(ABC):
    """NotificationProvider.send(...) -> provider_message_id/status (spec section 9)."""

    #: short machine name stored in notification_deliveries.provider
    name: str = "base"

    @abstractmethod
    def send(
        self,
        *,
        destination: str,
        title: str,
        message: str,
        subject: str | None = None,
        thread_key: str | None = None,
    ) -> ProviderResult:
        """Attempt one delivery. Must never raise - catch provider-specific
        exceptions internally and translate them into a ProviderResult so the
        service layer has one consistent failure shape to work with.

        `thread_key` is the existing thread anchor for this (channel,
        destination), if any prior notification to this same recipient
        already established one - see ProviderResult.thread_key above. A
        provider without a threading concept may ignore it."""
        raise NotImplementedError
