"""Unit tests for the shared bounded-retry helper (spec FR-08/FR-09:
retries must be bounded, use backoff, and stop immediately on a
non-retryable failure). No DB/HTTP involved here - just the retry logic
against fake providers, with sleep_fn stubbed so tests run instantly."""
from app.providers.base import ProviderResult
from app.services.retry import send_with_retry


class FlakyProvider:
    """Fails `fail_times` times with a retryable error, then succeeds."""

    name = "flaky"

    def __init__(self, fail_times):
        self.fail_times = fail_times
        self.calls = 0

    def send(self, *, destination, title, message, subject=None, thread_key=None):
        self.calls += 1
        self.last_thread_key = thread_key
        if self.calls <= self.fail_times:
            return ProviderResult(success=False, status="FAILED", error_message="temporary", retryable=True)
        return ProviderResult(success=True, status="SENT", provider_message_id="mid-1", thread_key=thread_key or "root-1")


class AlwaysNonRetryable:
    name = "nr"

    def send(self, *, destination, title, message, subject=None, thread_key=None):
        return ProviderResult(success=False, status="FAILED", error_message="bad request", retryable=False)


def test_retries_until_success_and_sleeps_between_attempts():
    provider = FlakyProvider(fail_times=2)
    sleeps = []

    result, attempts = send_with_retry(
        provider,
        destination="d",
        title="t",
        message="m",
        subject=None,
        max_attempts=5,
        backoff_base_seconds=1,
        sleep_fn=sleeps.append,
    )

    assert result.success is True
    assert attempts == 3
    assert sleeps == [1, 2]  # exponential backoff: base * 2**(attempt-1)


def test_gives_up_after_max_attempts_without_exceeding_it():
    provider = FlakyProvider(fail_times=10)

    result, attempts = send_with_retry(
        provider,
        destination="d",
        title="t",
        message="m",
        subject=None,
        max_attempts=3,
        backoff_base_seconds=0.01,
        sleep_fn=lambda seconds: None,
    )

    assert result.success is False
    assert attempts == 3
    assert provider.calls == 3


def test_non_retryable_failure_stops_immediately_without_sleeping():
    def fail_if_called(seconds):
        raise AssertionError("must not sleep after a non-retryable failure")

    result, attempts = send_with_retry(
        AlwaysNonRetryable(),
        destination="d",
        title="t",
        message="m",
        subject=None,
        max_attempts=5,
        backoff_base_seconds=0.01,
        sleep_fn=fail_if_called,
    )

    assert attempts == 1
    assert result.success is False
    assert result.retryable is False


def test_thread_key_is_passed_through_unchanged_on_every_attempt():
    """A retry must not invent a new thread - every attempt (including
    retries) gets the same thread_key the caller supplied, and the
    provider is expected to just echo it back."""
    provider = FlakyProvider(fail_times=2)

    result, attempts = send_with_retry(
        provider,
        destination="d",
        title="t",
        message="m",
        subject=None,
        thread_key="existing-root",
        max_attempts=5,
        backoff_base_seconds=0.01,
        sleep_fn=lambda seconds: None,
    )

    assert attempts == 3
    assert provider.last_thread_key == "existing-root"
    assert result.thread_key == "existing-root"


def test_no_thread_key_means_provider_mints_a_new_root():
    provider = FlakyProvider(fail_times=0)

    result, _ = send_with_retry(
        provider,
        destination="d",
        title="t",
        message="m",
        subject=None,
        max_attempts=1,
        backoff_base_seconds=0.01,
        sleep_fn=lambda seconds: None,
    )

    assert provider.last_thread_key is None
    assert result.thread_key == "root-1"
