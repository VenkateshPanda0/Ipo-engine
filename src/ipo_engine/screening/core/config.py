"""Application settings loaded from environment variables (and an optional .env file)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

#: settings that may be supplied as ``<NAME>_FILE=/run/secrets/...`` (Docker and Kubernetes secrets)
SECRET_FILE_SETTINGS = (
    "API_KEY",
    "API_KEYS",
    "DATABASE_URL",
    "GOOGLE_CLIENT_SECRET",
    "WEBHOOK_SIGNING_KEY",
    "S3_ACCESS_KEY_ID",
    "S3_SECRET_ACCESS_KEY",
    "SMTP_PASSWORD",
)


class Settings(BaseSettings):
    """Runtime configuration: the environment, and secrets from files (SECRET_FILE_SETTINGS)."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def read_secret_files(cls, data: Any) -> Any:
        """``NAME_FILE`` points at a file holding the value, so a secret need not sit in the
        environment (where ``docker inspect`` or a crash dump would show it). A value given directly
        wins over a file; an unreadable file is a configuration error, not a silent default."""
        if not isinstance(data, dict):
            return data
        data = dict(data)
        for name in SECRET_FILE_SETTINGS:
            path = os.environ.get(f"{name}_FILE")
            if not path or name in data or name in os.environ:
                continue
            try:
                data[name] = Path(path).read_text(encoding="utf-8").rstrip("\r\n")
            except OSError as exc:
                raise ValueError(
                    f"{name}_FILE={path}: cannot read the file ({exc.strerror})"
                ) from exc
        return data

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
    # Webhooks need a server secret: each endpoint's signing secret is derived from it, so none is
    # stored. Leave it unset to keep webhooks off. Plain-http / private targets are for development.
    webhook_signing_key: str | None = Field(default=None, alias="WEBHOOK_SIGNING_KEY")
    allow_private_webhook_targets: bool = Field(
        default=False, alias="ALLOW_PRIVATE_WEBHOOK_TARGETS"
    )
    webhook_max_attempts: int = Field(default=6, ge=1, le=20, alias="WEBHOOK_MAX_ATTEMPTS")
    # Optional e-mail (invitations). Without SMTP_HOST the admin copies the invitation link instead.
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, ge=1, le=65535, alias="SMTP_PORT")
    smtp_user: str | None = Field(default=None, alias="SMTP_USER")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_from: str | None = Field(default=None, alias="SMTP_FROM")
    smtp_security: Literal["starttls", "ssl", "none"] = Field(
        default="starttls", alias="SMTP_SECURITY"
    )
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
    worker_threads: int = Field(default=2, ge=0, le=16, alias="WORKER_THREADS")
    # Where uploaded PDFs are kept: a folder under DATA_DIR, or an S3-compatible bucket.
    storage_backend: Literal["file", "s3"] = Field(default="file", alias="STORAGE_BACKEND")
    s3_bucket: str | None = Field(default=None, alias="S3_BUCKET")
    s3_region: str = Field(default="us-east-1", alias="S3_REGION")
    s3_endpoint: str | None = Field(default=None, alias="S3_ENDPOINT")  # MinIO, R2, ...
    s3_access_key_id: str | None = Field(default=None, alias="S3_ACCESS_KEY_ID")
    s3_secret_access_key: str | None = Field(default=None, alias="S3_SECRET_ACCESS_KEY")
    s3_prefix: str = Field(default="", alias="S3_PREFIX")
    retain_documents: bool = Field(default=True, alias="RETAIN_DOCUMENTS")
    retention_days: int = Field(default=90, ge=1, alias="RETENTION_DAYS")
    rate_limit_per_minute: int = Field(default=30, ge=1, alias="UPLOAD_RATE_LIMIT_PER_MINUTE")
    # Request rate limit per signed-in user (0 = off). The upload limit above is separate.
    api_rate_limit_per_minute: int = Field(default=0, ge=0, alias="API_RATE_LIMIT_PER_MINUTE")
    # "memory": counted per process. "database": counted in the shared database, so several API
    # processes enforce one limit between them.
    rate_limit_store: Literal["memory", "database"] = Field(
        default="memory", alias="RATE_LIMIT_STORE"
    )
    # "local": this process extracts the documents it receives. "queue": uploads wait in the
    # database and any process running workers (the API itself, or `ipo worker`) claims them, so
    # API and workers can scale and restart independently. WORKER_THREADS=0 makes an API process
    # queue-only.
    job_mode: Literal["local", "queue"] = Field(default="local", alias="JOB_MODE")
    job_lease_seconds: int = Field(default=120, ge=10, le=3600, alias="JOB_LEASE_SECONDS")
    job_max_attempts: int = Field(default=3, ge=1, le=20, alias="JOB_MAX_ATTEMPTS")

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
