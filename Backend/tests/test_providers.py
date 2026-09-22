"""Provider-factory and MockProvider tests (spec section 21: the service
must be able to run entirely on mock adapters without touching business
logic, and must pick a real adapter automatically once configured)."""
from app.config import Settings
from app.providers.email.provider import EmailProvider
from app.providers.factory import get_provider
from app.providers.mock import MockProvider
from app.providers.slack.provider import SlackProvider
from app.providers.teams.provider import TeamsProvider


def test_factory_falls_back_to_mock_when_unconfigured():
    settings = Settings(
        teams_webhook_url="",
        slack_bot_token="",
        smtp_username="",
        smtp_password="",
        smtp_sender_email="",
        force_mock_providers=False,
    )
    for channel in ("teams", "slack", "email"):
        assert isinstance(get_provider(channel, settings), MockProvider)


def test_factory_uses_real_providers_once_configured():
    settings = Settings(
        teams_webhook_url="https://example.com/webhook",
        slack_bot_token="xoxb-test-token",
        smtp_username="user",
        smtp_password="pass",
        smtp_sender_email="sender@example.com",
        force_mock_providers=False,
    )
    assert isinstance(get_provider("teams", settings), TeamsProvider)
    assert isinstance(get_provider("slack", settings), SlackProvider)
    assert isinstance(get_provider("email", settings), EmailProvider)


def test_force_mock_providers_overrides_real_config():
    settings = Settings(teams_webhook_url="https://example.com/webhook", force_mock_providers=True)
    assert isinstance(get_provider("teams", settings), MockProvider)


def test_mock_provider_always_succeeds():
    result = MockProvider().send(destination="x", title="t", message="m")
    assert result.success is True
    assert result.status == "SENT"
    assert result.provider_message_id.startswith("mock-")
