from __future__ import annotations

from functools import lru_cache
from typing import Annotated
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BeforeValidator, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _strip_quotes(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in ('"', "'"):
        cleaned = cleaned[1:-1].strip()
    return cleaned


def parse_cors_origins(value: str | list[str]) -> list[str]:
    if isinstance(value, str):
        cleaned = _strip_quotes(value)
        if not cleaned:
            return []
        if cleaned.startswith("[") and cleaned.endswith("]"):
            import json

            parsed = json.loads(cleaned)
            return [_strip_quotes(str(item)) for item in parsed if _strip_quotes(str(item))]
        return [_strip_quotes(origin) for origin in cleaned.split(",") if _strip_quotes(origin)]
    return value


def normalize_async_database_url(url: str) -> str:
    """
    Normaliza cualquier URL de PostgreSQL (`postgres://`, `postgresql://`, `postgresql+psycopg2://`)
    al driver `postgresql+asyncpg://` y limpia comillas o parámetros incompatibles con `asyncpg`
    (como `sslmode=disable` que Easypanel incluye por defecto en sus Internal URLs).
    """
    cleaned = _strip_quotes(url)
    if cleaned.startswith("sqlite://"):
        return "sqlite+aiosqlite://" + cleaned[len("sqlite://") :]
    if cleaned.startswith("postgres://"):
        cleaned = "postgresql+asyncpg://" + cleaned[len("postgres://") :]
    elif cleaned.startswith("postgresql://"):
        cleaned = "postgresql+asyncpg://" + cleaned[len("postgresql://") :]
    elif cleaned.startswith("postgresql+psycopg"):
        _, rest = cleaned.split("://", 1)
        cleaned = f"postgresql+asyncpg://{rest}"

    parts = urlsplit(cleaned)
    if parts.query:
        query_params = dict(parse_qsl(parts.query, keep_blank_values=True))
        sslmode = query_params.pop("sslmode", None)
        query_params.pop("channel_binding", None)
        if sslmode and "ssl" not in query_params and sslmode != "disable":
            query_params["ssl"] = (
                "require" if sslmode in ("require", "verify-ca", "verify-full") else sslmode
            )
        new_query = urlencode(query_params)
        cleaned = urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))

    return cleaned


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

    # Variables individuales de PostgreSQL
    postgres_user: str = Field(default="omega", alias="POSTGRES_USER")
    postgres_password: str = Field(
        default="omega_super_secret_db_pass", alias="POSTGRES_PASSWORD"
    )
    postgres_host: str = Field(default="db", alias="POSTGRES_HOST")
    postgres_port: int = Field(default=5432, alias="POSTGRES_PORT")
    postgres_db: str = Field(default="omega_os", alias="POSTGRES_DB")

    database_url: str = Field(default="", alias="DATABASE_URL")
    sqlite_fallback_url: str = Field(
        default="sqlite+aiosqlite:///./omega_os_fallback.db",
        alias="SQLITE_FALLBACK_URL",
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

    @model_validator(mode="after")
    def build_and_normalize_database_url(self) -> Settings:
        self.jwt_secret_key = _strip_quotes(self.jwt_secret_key)
        self.partner_jackson_password = _strip_quotes(self.partner_jackson_password)
        self.partner_yassin_password = _strip_quotes(self.partner_yassin_password)
        self.n8n_secret_api_key = _strip_quotes(self.n8n_secret_api_key)
        self.n8n_webhook_secret = _strip_quotes(self.n8n_webhook_secret)
        self.openai_api_key = _strip_quotes(self.openai_api_key)

        if not self.database_url or not _strip_quotes(self.database_url):
            self.database_url = (
                f"postgresql+asyncpg://{_strip_quotes(self.postgres_user)}:"
                f"{_strip_quotes(self.postgres_password)}"
                f"@{_strip_quotes(self.postgres_host)}:{self.postgres_port}/"
                f"{_strip_quotes(self.postgres_db)}"
            )
        else:
            self.database_url = normalize_async_database_url(self.database_url)
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
