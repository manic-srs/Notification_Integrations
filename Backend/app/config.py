"""
Centralized configuration, loaded from environment variables / a local .env
file. Nothing in here is ever logged or returned by the API - see
app/security.py for the redaction helper used everywhere secrets could
otherwise leak.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database (MySQL only - no ORM, connected directly via PyMySQL) 
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "notification_db"

    # Teams 
    teams_webhook_url: str = ""

    # Slack 
    slack_bot_token: str = ""

    # Email / SMTP 
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_sender_email: str = ""

    # Providers 
    force_mock_providers: bool = False

    # Retry policy 
    retry_max_attempts: int = 3
    retry_backoff_base_seconds: float = 2.0

    # Webhook security 
    webhook_shared_secret: str = "change-me"

    # CORS 
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # --- capability checks used by the provider factory -----
    @property
    def teams_configured(self) -> bool:
        return bool(self.teams_webhook_url) and not self.force_mock_providers

    @property
    def slack_configured(self) -> bool:
        return bool(self.slack_bot_token) and not self.force_mock_providers

    @property
    def email_configured(self) -> bool:
        return (
            bool(self.smtp_username and self.smtp_password and self.smtp_sender_email)
            and not self.force_mock_providers
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
