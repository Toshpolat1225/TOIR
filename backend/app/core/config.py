from functools import cached_property
from typing import Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: str = "development"
    postgres_db: str
    postgres_user: str
    postgres_password: SecretStr
    database_host: str = "postgres"
    database_port: int = 5432
    jwt_secret: SecretStr
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    cors_origins: str
    api_docs_enabled: bool = True
    wialon_ingest_token: SecretStr | None = None
    wialon_host: str | None = "https://gps.agmk.uz"
    wialon_token: SecretStr | None = None
    wialon_sync_interval_minutes: int = Field(default=2, ge=1, le=1440)
    wialon_sync_enabled: bool = False

    @field_validator("wialon_host", mode="before")
    @classmethod
    def normalize_wialon_host(cls, value: object) -> str | None:
        if value is None:
            return None
        host = str(value).strip().rstrip("/")
        if not host:
            return None
        parsed = urlsplit(host)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError("WIALON_HOST must be an HTTPS base URL without credentials or query")
        return host

    @field_validator("wialon_token", mode="before")
    @classmethod
    def normalize_wialon_token(cls, value: object) -> object:
        if value is None or not str(value).strip():
            return None
        return str(value).strip()

    @field_validator("wialon_sync_interval_minutes", mode="before")
    @classmethod
    def default_empty_wialon_interval(cls, value: object) -> object:
        return 2 if value is None or not str(value).strip() else value

    @field_validator("wialon_sync_enabled", mode="before")
    @classmethod
    def default_empty_wialon_enabled(cls, value: object) -> object:
        return False if value is None or not str(value).strip() else value

    @field_validator("jwt_secret")
    @classmethod
    def validate_jwt_secret(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value().encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 bytes")
        return value

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if not origins:
            raise ValueError("CORS_ORIGINS must contain at least one origin")
        for origin in origins:
            parsed = urlsplit(origin)
            if (
                origin == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError("CORS_ORIGINS must contain exact HTTP(S) origins")
        return ",".join(origins)

    @model_validator(mode="after")
    def validate_token_settings(self) -> Self:
        if self.jwt_algorithm != "HS256":
            raise ValueError("JWT_ALGORITHM must be HS256")
        if self.access_token_expire_minutes <= 0:
            raise ValueError("ACCESS_TOKEN_EXPIRE_MINUTES must be positive")
        if self.refresh_token_expire_days <= 0:
            raise ValueError("REFRESH_TOKEN_EXPIRE_DAYS must be positive")
        return self

    @property
    def allowed_cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def wialon_pull_enabled(self) -> bool:
        return (
            self.wialon_sync_enabled
            and self.wialon_host is not None
            and self.wialon_token is not None
            and bool(self.wialon_token.get_secret_value())
        )

    @cached_property
    def sqlalchemy_database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.database_host,
            port=self.database_port,
            database=self.postgres_db,
        )


settings = Settings()
