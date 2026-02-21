"""
App configuration — all credentials from environment (OWASP: no hardcoded secrets).

Load from .env via pydantic_settings. In production, set ENVIRONMENT=production
so required secrets are validated at startup.
"""
from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment. No defaults for secrets in production."""

    database_url: str = "sqlite:///./ap_anomaly.db"  # Use postgresql://... for production
    qbo_client_id: str = ""
    qbo_client_secret: str = ""
    qbo_redirect_uri: str = "http://localhost:8000/api/auth/qbo/callback"
    qbo_environment: str = "sandbox"  # sandbox | production
    environment: str = "development"  # development | production — production validates secrets

    # Alert thresholds (avoid fatigue)
    alert_min_amount: float = 500.0
    alert_sigma_threshold: float = 2.0
    duplicate_day_window: int = 7
    baseline_days: int = 90

    # SMTP email alerts
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_from_email: str = ""

    # Rate limiting (OWASP API Security: prevent abuse and brute force)
    rate_limit_requests_per_minute_ip: int = 100
    rate_limit_requests_per_minute_user: int = 100

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @model_validator(mode="after")
    def validate_production_secrets(self):
        """Fail fast in production if required credentials are missing (key rotation / .env)."""
        if self.environment != "production":
            return self
        if not (self.qbo_client_id and self.qbo_client_secret):
            raise ValueError(
                "In production, QBO_CLIENT_ID and QBO_CLIENT_SECRET must be set in .env"
            )
        if self.smtp_user and not self.smtp_password:
            raise ValueError(
                "In production, SMTP_PASSWORD must be set when SMTP_USER is set"
            )
        return self


settings = Settings()
