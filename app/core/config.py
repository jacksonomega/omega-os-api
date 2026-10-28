from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def parse_cors_origins(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return []
        if cleaned.startswith("[") and cleaned.endswith("]"):
            import json

            parsed = json.loads(cleaned)
            return [str(item).strip() for item in parsed if str(item).strip()]
        return [origin.strip() for origin in cleaned.split(",") if origin.strip()]
    return value


CorsOriginsList = Annotated[list[str], BeforeValidator(parse_cors_origins)]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="Omega OS API", alias="APP_NAME")
    app_env: str = Field(default="production", alias="APP_ENV")
    debug: bool = Field(default=False, alias="DEBUG")
    api_v1_prefix: str = Field(default="/v1", alias="API_V1_PREFIX")

    database_url: str = Field(
        default="postgresql+asyncpg://omega:omega_super_secret_db_pass@localhost:5432/omega_os",
        alias="DATABASE_URL",
    )

    cors_origins: CorsOriginsList = Field(
        default=[
            "https://os.omega-studio.tech",
            "https://omega-studio.tech",
            "http://localhost:4200",
        ],
        alias="CORS_ORIGINS",
    )

    jwt_secret_key: str = Field(
        default="change_this_to_a_64_char_random_hex_secret_in_production_omega_os",
        alias="JWT_SECRET_KEY",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_expires_seconds: int = Field(default=28800, alias="JWT_EXPIRES_SECONDS")
    password_salt: str = Field(default="omega-os-v1", alias="PASSWORD_SALT")

    partner_jackson_password: str = Field(
        default="omega-jackson-2026",
        alias="PARTNER_JACKSON_PASSWORD",
    )
    partner_yassin_password: str = Field(
        default="omega-yassin-2026",
        alias="PARTNER_YASSIN_PASSWORD",
    )

    n8n_secret_api_key: str = Field(
        default="omega_n8n_secret_api_key_change_in_prod",
        alias="N8N_SECRET_API_KEY",
    )

    n8n_webhook_secret: str = Field(
        default="omega_n8n_outbound_webhook_signing_secret",
        alias="N8N_WEBHOOK_SECRET",
    )
    n8n_webhook_client_closed: str = Field(
        default="",
        alias="N8N_WEBHOOK_CLIENT_CLOSED",
    )
    n8n_webhook_margin_alert: str = Field(
        default="",
        alias="N8N_WEBHOOK_MARGIN_ALERT",
    )
    n8n_webhook_urgent_task: str = Field(
        default="",
        alias="N8N_WEBHOOK_URGENT_TASK",
    )
    n8n_webhook_timeout_seconds: float = Field(
        default=5.0,
        alias="N8N_WEBHOOK_TIMEOUT_SECONDS",
    )

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", alias="OPENAI_MODEL")
    openai_base_url: str = Field(
        default="https://api.openai.com/v1",
        alias="OPENAI_BASE_URL",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
