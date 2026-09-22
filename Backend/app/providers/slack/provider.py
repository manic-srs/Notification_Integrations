"""
Slack adapter - same three-call sequence we tested earlier in this project
(test_slack_webhook.py) against the "PII-Shield Notifications" Slack app:

  1. users_lookupByEmail(email)      -> resolve destination (an email
                                         address) to a Slack user id
  2. conversations_open(users=...)   -> open/reuse a private 1:1 DM
  3. chat_postMessage(channel=...)   -> post into that DM only

`destination` here is the recipient's email address, matching the Slack
Bot Token scopes we configured: chat:write, im:write, users:read,
users:read.email.

Threading: if a `thread_key` (a prior message's `ts`) is passed in, the
message replies into that thread via `thread_ts` instead of posting a new
top-level DM, so repeated notifications to the same person stay grouped in
one running conversation. See app/providers/base.py:ProviderResult.
"""
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from app.providers.base import NotificationProvider, ProviderResult

# Slack error codes that mean "this will never succeed, don't retry."
_NON_RETRYABLE_ERRORS = {
    "users_not_found",
    "invalid_email",
    "invalid_auth",
    "account_inactive",
    "missing_scope",
    "not_authed",
    "token_revoked",
    "channel_not_found",
}


class SlackProvider(NotificationProvider):
    name = "slack"

    def __init__(self, bot_token: str):
        self._client = WebClient(token=bot_token)

    def send(
        self,
        *,
        destination: str,
        title: str,
        message: str,
        subject: str | None = None,
        thread_key: str | None = None,
    ) -> ProviderResult:
        text = f"*{title}*\n{message}" if title else message

        try:
            lookup = self._client.users_lookupByEmail(email=destination)
            slack_user_id = lookup["user"]["id"]

            conversation = self._client.conversations_open(users=slack_user_id)
            channel_id = conversation["channel"]["id"]

            post_kwargs = {"channel": channel_id, "text": text}
            if thread_key:
                # Reply into the existing thread instead of posting a new
                # top-level DM, so every notification to this person lives
                # in one running conversation.
                post_kwargs["thread_ts"] = thread_key

            posted = self._client.chat_postMessage(**post_kwargs)
        except SlackApiError as exc:
            error_code = exc.response.get("error", "unknown_error") if exc.response is not None else "unknown_error"
            retryable = error_code == "ratelimited" or error_code not in _NON_RETRYABLE_ERRORS
            return ProviderResult(
                success=False,
                status="FAILED",
                error_message=f"Slack error: {error_code}",
                retryable=retryable,
            )

        posted_ts = posted.get("ts")
        return ProviderResult(
            success=True,
            status="SENT",
            provider_message_id=posted_ts,
            # First message in this DM becomes the thread root; a reply
            # keeps pointing at the same root it was given.
            thread_key=thread_key or posted_ts,
        )
