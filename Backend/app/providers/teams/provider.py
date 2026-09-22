"""
Microsoft Teams adapter.

This is the same Power Automate flow we already built and tested earlier in
this project: an instant cloud flow triggered by "When a Teams webhook
request is received" -> Parse JSON -> "Post message in a chat or channel"
(Flow bot, private 1:1 chat). The flow reads `recipient` and `text` from the
JSON body and posts a private message to that person - so `destination`
here is the recipient's email address, exactly like the tested
test_teams_webhook.py script.

Threading: `thread_key` is accepted (for interface parity with the other
providers - see app/providers/base.py:ProviderResult) but intentionally
unused. A 1:1 chat with a person is already one single, continuous
conversation in Teams - there's no separate "thread" to opt into the way
Slack has. Real threaded replies only exist for *channel* messages, which
would need a different delivery mechanism entirely (Microsoft Graph API
channel posts instead of this webhook).
"""
import httpx

from app.providers.base import NotificationProvider, ProviderResult


class TeamsProvider(NotificationProvider):
    name = "teams"

    def __init__(self, webhook_url: str, timeout_seconds: float = 10.0):
        self._webhook_url = webhook_url
        self._timeout_seconds = timeout_seconds

    def send(
        self,
        *,
        destination: str,
        title: str,
        message: str,
        subject: str | None = None,
        thread_key: str | None = None,  # unused - see module docstring
    ) -> ProviderResult:
        text = f"{title}: {message}" if title else message
        payload = {"text": text, "recipient": destination}

        try:
            response = httpx.post(self._webhook_url, json=payload, timeout=self._timeout_seconds)
        except httpx.TimeoutException:
            return ProviderResult(success=False, status="FAILED", error_message="Teams webhook timed out", retryable=True)
        except httpx.RequestError as exc:
            return ProviderResult(success=False, status="FAILED", error_message=f"Teams request error: {exc}", retryable=True)

        if response.status_code == 429:
            return ProviderResult(success=False, status="FAILED", error_message="Teams rate limited (429)", retryable=True)
        if response.status_code >= 500:
            return ProviderResult(
                success=False,
                status="FAILED",
                error_message=f"Teams webhook returned {response.status_code}",
                retryable=True,
            )
        if response.status_code >= 400:
            # Bad request / auth / unknown recipient - retrying won't help.
            return ProviderResult(
                success=False,
                status="FAILED",
                error_message=f"Teams webhook rejected the request ({response.status_code})",
                retryable=False,
            )

        # The Power Automate webhook trigger replies 202 with an empty body
        # on success - there's no message id to capture, so we use the
        # flow's own response status as the delivery confirmation.
        return ProviderResult(success=True, status="SENT", provider_message_id=None)
