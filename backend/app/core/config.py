from pathlib import Path
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
    audit_retention_days: int = Field(default=365, ge=30, le=3650)
    position_history_retention_days: int = Field(default=180, ge=7, le=3650)  # the track behind the map is thinned, still ~30k rows/day
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
    # Weighing scales (Vesovoy): the Windows collector pushes with this token; unset = the ingest endpoint is closed.
    scales_ingest_token: SecretStr | None = None
    scales_utc_offset_hours: int = Field(default=5, ge=-12, le=14)  # the scale PCs store local (Tashkent) time without a zone
    scales_traction_tare_min_t: float = Field(default=115.0, gt=0)  # tare at/above this = traction unit (without GTK); measured: units 1-2 cluster at 115-140 t, dump cars at 60-115 t
    scales_carriage_order: str = Field(default="asc", pattern="^(asc|desc)$")  # dump car by scale position <-> GTK carriage by ord (confirmed: asc)
    scales_gtk_tolerance_min: int = Field(default=15, ge=0, le=120)  # GTK membership is observed every ~10 min
    scales_silent_warn_hours: int = Field(default=6, ge=1, le=240)
    scales_silent_alert_hours: int = Field(default=24, ge=1, le=720)
    wialon_host: str | None = "https://gps.agmk.uz"
    wialon_token: SecretStr | None = None
    wialon_sync_interval_minutes: int = Field(default=2, ge=1, le=1440)
    wialon_sync_enabled: bool = False
    gtk_host: str | None = None
    gtk_user: str | None = None
    gtk_password: SecretStr | None = None
    gtk_page_path: str = "/railway/__railway_train/"
    gtk_page_query: str = "EnterprisesControlRB=1"
    gtk_sync_enabled: bool = False
    gtk_sync_interval_minutes: int = Field(default=10, ge=5, le=1440)
    # Wialon units report as rarely as every ~3 h; 30 min held 363 of 491 segments.
    wagon_mileage_max_bracket_gap_min: int = Field(default=240, ge=1)
    wagon_mileage_idle_min_minutes: int = Field(default=30, ge=1)
    wagon_mileage_engine_enabled: bool = False
    # D8 policy: when true, the same administrator may propose and approve an
    # opening balance. Default false (maker != checker).
    opening_balance_allow_self_approval: bool = False
    # Active Directory (LDAPS) login. Off by default.
    ad_auth_enabled: bool = False
    ad_servers: str = "dc-r.agmk.uz,dc.agmk.uz"
    ad_domain: str = "agmk.uz"
    ad_base_dn: str = "DC=agmk,DC=uz"
    ad_ca_file: str = str(
        Path(__file__).resolve().parents[1] / "certs" / "agmk-DC-R-CA-3.crt"
    )
    ad_connect_timeout: int = Field(default=5, ge=1, le=30)
    ad_receive_timeout: int = Field(default=10, ge=1, le=60)
    daily_km_estimate: int = Field(default=200, gt=0)
    # "Tirik reja" planning engine (see docs and maintenance_engine.py). Defaults are the proposal's values.
    maintenance_pace_window_days: int = Field(default=30, ge=7, le=180)
    maintenance_pace_min_days: int = Field(default=7, ge=1, le=60)
    maintenance_pace_shrink_k: int = Field(default=7, ge=1, le=60)
    maintenance_stale_hours: int = Field(default=24, ge=1, le=720)  # no Wialon message for this long = unreliable forecast
    maintenance_merge_pct: int = Field(default=15, ge=0, le=100)  # lower rank due this close (% of its interval) joins the visit
    maintenance_min_early_pct: int = Field(default=70, ge=1, le=100)  # opportunistic offer from this share of the interval
    maintenance_deferral_escalation: int = Field(default=2, ge=1, le=10)  # postponements before admin approval is required
    maintenance_job_enabled: bool = True
    maintenance_job_interval_minutes: int = Field(default=60, ge=1, le=1440)

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

    @field_validator("gtk_host", mode="before")
    @classmethod
    def normalize_gtk_host(cls, value: object) -> str | None:
        if value is None or not str(value).strip():
            return None
        host = str(value).strip().rstrip("/")
        parsed = urlsplit(host)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError("GTK_HOST must be an HTTP(S) base URL without credentials or path")
        return host

    @field_validator("gtk_user", mode="before")
    @classmethod
    def normalize_gtk_user(cls, value: object) -> str | None:
        if value is None or not str(value).strip():
            return None
        return str(value).strip()

    @field_validator("gtk_password", mode="before")
    @classmethod
    def normalize_gtk_password(cls, value: object) -> object:
        if value is None or not str(value).strip():
            return None
        return value

    @field_validator("gtk_page_path", mode="before")
    @classmethod
    def default_empty_gtk_page_path(cls, value: object) -> str:
        return "/railway/__railway_train/" if value is None or not str(value).strip() else str(value)

    @field_validator("gtk_page_query", mode="before")
    @classmethod
    def default_empty_gtk_page_query(cls, value: object) -> str:
        return "EnterprisesControlRB=1" if value is None or not str(value).strip() else str(value)

    @field_validator("gtk_sync_enabled", mode="before")
    @classmethod
    def default_empty_gtk_enabled(cls, value: object) -> object:
        return False if value is None or not str(value).strip() else value

    @field_validator("gtk_sync_interval_minutes", mode="before")
    @classmethod
    def default_empty_gtk_interval(cls, value: object) -> object:
        return 10 if value is None or not str(value).strip() else value

    @property
    def gtk_credentials_configured(self) -> bool:
        return bool(
            self.gtk_host
            and self.gtk_user
            and self.gtk_password
            and self.gtk_password.get_secret_value()
        )

    @property
    def gtk_pull_enabled(self) -> bool:
        return self.gtk_sync_enabled and self.gtk_credentials_configured

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
