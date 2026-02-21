"""App configuration."""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment."""

    database_url: str = "sqlite:///./ap_anomaly.db"  # Use postgresql://... for production
    qbo_client_id: str = ""
    qbo_client_secret: str = ""
    qbo_redirect_uri: str = "http://localhost:8000/api/auth/qbo/callback"
    qbo_environment: str = "sandbox"  # sandbox | production

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
