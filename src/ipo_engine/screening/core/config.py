"""Application settings loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Secrets are only read from the environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = Field(default="development", alias="APP_ENV")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    # json: one JSON object per line (for log shippers); text: one readable line per record.
    log_format: Literal["json", "text"] = Field(default="json", alias="LOG_FORMAT")
    # A Prometheus /metrics endpoint (admin role only). Off by default; counters are per process.
    metrics_enabled: bool = Field(default=False, alias="METRICS_ENABLED")
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"], alias="CORS_ORIGINS"
    )

    # Authentication. API_KEYS entries: "<user_id>|<role>|<key or sha256=hex>", comma separated.
    # Roles: viewer, analyst, reviewer, admin. API_KEY (legacy) maps to an analyst principal.
    api_key: str | None = Field(default=None, alias="API_KEY")
    api_keys: str | None = Field(default=None, alias="API_KEYS")
    # Production refuses to start with no API keys, because no keys means every caller is an admin.
    # This is the explicit opt-out (e.g. behind a trusted gateway that authenticates for the API).
    allow_unauthenticated: bool = Field(default=False, alias="ALLOW_UNAUTHENTICATED")
    # Accounts mode: people sign in, belong to organisations, and see only their organisation's
    # cases. Off by default, so the offline single-user and API-key modes are unchanged.
    accounts_enabled: bool = Field(default=False, alias="ACCOUNTS_ENABLED")
    # Browser sessions (accounts mode). The cookie is HttpOnly and SameSite=Lax; it is Secure in
    # production or when TRUST_HTTPS is set. A session ends after SESSION_DAYS, or after
    # SESSION_IDLE_HOURS without a request.
    session_days: int = Field(default=14, ge=1, le=90, alias="SESSION_DAYS")
    session_idle_hours: int = Field(default=72, ge=1, le=24 * 90, alias="SESSION_IDLE_HOURS")
    # "invite": only people with an invitation (or already added) can sign in. "open": anyone with a
    # verified Google address gets an account and an organisation of their own.
    signup_mode: Literal["invite", "open"] = Field(default="invite", alias="SIGNUP_MODE")
    # Optional Google sign-in. Leave the client id empty to keep it off. PUBLIC_BASE_URL is the
    # address people use to reach the app (the redirect URI is derived from it and must be
    # registered with Google as <PUBLIC_BASE_URL>/api/v1/auth/callback/google).
    google_client_id: str | None = Field(default=None, alias="GOOGLE_CLIENT_ID")
    google_client_secret: str | None = Field(default=None, alias="GOOGLE_CLIENT_SECRET")
    oidc_issuer: str = Field(default="https://accounts.google.com", alias="OIDC_ISSUER")
    public_base_url: str = Field(default="http://localhost:3000", alias="PUBLIC_BASE_URL")
    invitation_days: int = Field(default=7, ge=1, le=60, alias="INVITATION_DAYS")
    # Optional: only these email domains may sign in (comma separated), e.g. "acme.com".
    allowed_email_domains: Annotated[list[str], NoDecode] = Field(
        default_factory=list, alias="ALLOWED_EMAIL_DOMAINS"
    )
    # Set only when TLS is terminated in front of the API: turns on Strict-Transport-Security.
    trust_https: bool = Field(default=False, alias="TRUST_HTTPS")

    database_url: str = Field(
        default="sqlite:///./data/app/ipo_due_diligence.db",
        validation_alias=AliasChoices("DATABASE_URL", "REPORT_DATABASE_URL"),
    )
    data_dir: Path = Field(default=Path("./data/app"), alias="DATA_DIR")

    ruleset_version: str = Field(default="2.0.0", alias="RULESET_VERSION")
    regulatory_validation_confirmed: bool = Field(
        default=False, alias="REGULATORY_VALIDATION_CONFIRMED"
    )
    regulatory_validation_reference: str | None = Field(
        default=None, alias="REGULATORY_VALIDATION_REFERENCE"
    )

    # Document processing limits.
    max_upload_size_mb: int = Field(default=50, ge=1, le=500, alias="MAX_UPLOAD_SIZE_MB")
    max_pdf_pages: int = Field(default=1500, ge=1, alias="MAX_PDF_PAGES")
    max_ocr_pages: int = Field(default=60, ge=0, alias="MAX_OCR_PAGES")
    ocr_enabled: bool = Field(default=True, alias="OCR_ENABLED")
    ocr_dpi: int = Field(default=200, ge=72, le=400, alias="OCR_DPI")
    processing_timeout_s: int = Field(default=900, ge=10, alias="PROCESSING_TIMEOUT_S")
    worker_threads: int = Field(default=2, ge=1, le=16, alias="WORKER_THREADS")
    retain_documents: bool = Field(default=True, alias="RETAIN_DOCUMENTS")
    retention_days: int = Field(default=90, ge=1, alias="RETENTION_DAYS")
    rate_limit_per_minute: int = Field(default=30, ge=1, alias="UPLOAD_RATE_LIMIT_PER_MINUTE")

    @field_validator("allowed_email_domains", mode="before")
    @classmethod
    def split_domains(cls, value: Any) -> Any:
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        return value

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_origins(cls, value: Any) -> Any:
        """Accept a comma-separated string as well as a list."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def google_enabled(self) -> bool:
        return bool(self.accounts_enabled and self.google_client_id and self.google_client_secret)

    @property
    def cookie_secure(self) -> bool:
        return self.is_production or self.trust_https

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_key or self.api_keys or self.accounts_enabled)

    @property
    def document_dir(self) -> Path:
        return self.data_dir / "documents"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
