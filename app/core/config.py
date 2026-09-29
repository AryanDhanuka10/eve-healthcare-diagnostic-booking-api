"""Centralised, environment-driven configuration (no secrets in source code)."""

from functools import lru_cache

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "EVE Healthcare Diagnostic Booking API"
    environment: str = "development"
    log_level: str = "INFO"

    # e.g. postgresql+psycopg://user:password@localhost:5432/eve
    database_url: str

    # Required, no default: the app must refuse to start without real secrets.
    jwt_secret_key: SecretStr = Field(min_length=32)
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, gt=0)

    webhook_secret: SecretStr = Field(min_length=16)
    webhook_tolerance_seconds: int = Field(default=300, gt=0)

    # JSON list, e.g. CORS_ORIGINS=["http://localhost:3000"]. Empty = CORS disabled.
    cors_origins: list[str] = []

    # Payment simulator knobs (see README "Payment flow").
    payment_success_rate: float = Field(default=0.8, ge=0, le=1)
    allow_simulation_override: bool = True

    # Booking appointment window.
    booking_min_lead_minutes: int = Field(default=30, ge=0)
    booking_max_advance_days: int = Field(default=180, gt=0)


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # values come from the environment
