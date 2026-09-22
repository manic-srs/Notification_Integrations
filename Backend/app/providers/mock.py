"""
In-memory provider used automatically whenever a channel's real credentials
are not configured (spec section 21: "a Mock Provider may be used where real
credentials are unavailable"). It never makes a network call and always
succeeds, so the rest of the app - API, DB, retry logic, frontend - can be
exercised end to end without any third-party account.
"""
import uuid

from app.providers.base import NotificationProvider, ProviderResult


class MockProvider(NotificationProvider):
    name = "mock"

    def send(
        self,
        *,
        destination: str,
        title: str,
        message: str,
        subject: str | None = None,
        thread_key: str | None = None,
    ) -> ProviderResult:
        return ProviderResult(
            success=True,
            status="SENT",
            provider_message_id=f"mock-{uuid.uuid4()}",
            # Echo the existing thread back unchanged, or mint a new one -
            # same rule real providers follow, so threading is exercisable
            # end to end (API/dashboard/tests) without any real credentials.
            thread_key=thread_key or f"mock-thread-{uuid.uuid4()}",
        )
