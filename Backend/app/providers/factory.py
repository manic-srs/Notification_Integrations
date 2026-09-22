"""
Turns a channel name ("teams" / "email" / "slack") into a configured
NotificationProvider instance - the one place that knows whether real
credentials are available. The service layer never sees this decision, it
just calls provider.send(...).
"""
from app.config import Settings
from app.providers.base import NotificationProvider
from app.providers.email.provider import EmailProvider
from app.providers.mock import MockProvider
from app.providers.slack.provider import SlackProvider
from app.providers.teams.provider import TeamsProvider

SUPPORTED_CHANNELS = ("teams", "email", "slack")


def get_provider(channel: str, settings: Settings) -> NotificationProvider:
    channel = channel.lower()

    if channel == "teams":
        if settings.teams_configured:
            return TeamsProvider(webhook_url=settings.teams_webhook_url)
        return MockProvider()

    if channel == "slack":
        if settings.slack_configured:
            return SlackProvider(bot_token=settings.slack_bot_token)
        return MockProvider()

    if channel == "email":
        if settings.email_configured:
            return EmailProvider(
                host=settings.smtp_host,
                port=settings.smtp_port,
                username=settings.smtp_username,
                password=settings.smtp_password,
                sender_email=settings.smtp_sender_email,
            )
        return MockProvider()

    raise ValueError(f"Unsupported channel: {channel}")
