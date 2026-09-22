"""
Bounded retry with exponential backoff for a single provider.send() call
(spec FR-09 and section 13's error-handling table). Only *retryable*
failures - timeouts, 5xx, rate limits - get another attempt; anything the
adapter flagged as permanent (bad credentials, invalid destination) fails
immediately with no wasted attempts.
"""
import logging
import time

from app.providers.base import NotificationProvider, ProviderResult

logger = logging.getLogger("notification_service")


def send_with_retry(
    provider: NotificationProvider,
    *,
    destination: str,
    title: str,
    message: str,
    subject: str | None,
    max_attempts: int,
    backoff_base_seconds: float,
    thread_key: str | None = None,
    sleep_fn=time.sleep,
) -> tuple[ProviderResult, int]:
    """Returns (final_result, attempts_made).

    `thread_key` (see app/providers/base.py:ProviderResult) is passed
    through unchanged on every retry attempt - it's the existing thread
    anchor for this (channel, destination), not something retries update."""
    attempts = 0
    result: ProviderResult | None = None

    while attempts < max_attempts:
        attempts += 1
        result = provider.send(
            destination=destination, title=title, message=message, subject=subject, thread_key=thread_key
        )

        if result.success or not result.retryable:
            break

        if attempts < max_attempts:
            backoff = backoff_base_seconds * (2 ** (attempts - 1))
            logger.warning(
                "provider=%s destination=%s attempt=%d/%d failed (%s) - retrying in %.1fs",
                provider.name,
                destination,
                attempts,
                max_attempts,
                result.error_message,
                backoff,
            )
            sleep_fn(backoff)

    assert result is not None
    return result, attempts
