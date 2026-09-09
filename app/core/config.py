from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # App
    app_name: str = "SaaS Template"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 8090

    # Database
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    postgres_user: str = "postgres"
    postgres_password: str = ""
    postgres_db: str = "saas_template"

    # Security
    internal_api_key: str | None = None

    # CORS
    cors_origins: str = "*"
    cors_allow_credentials: bool = True

    # JWT Authentication
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # Invitation System
    invite_token_expire_days: int = 7
    frontend_url: str = "http://localhost:5190"

    # Password Reset
    password_reset_token_expire_minutes: int = 30

    # Email verification
    email_verification_token_expire_hours: int = 48
    # If true, users cannot log in until they confirm their email (invited users are
    # verified automatically). Default false: login works, the UI shows a banner.
    require_email_verification: bool = False

    # Rate limiting (in-memory, per process). Applied to auth endpoints only.
    # Format: "<count>/<period>", e.g. "10/minute", "100/hour".
    rate_limit_enabled: bool = True
    rate_limit_auth: str = "10/minute"

    # Email SMTP Configuration
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@example.com"
    smtp_from_name: str = "SaaS Template"
    smtp_tls: bool = False
    smtp_ssl: bool = False

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @model_validator(mode="after")
    def _validate_secrets(self) -> Settings:
        if not self.jwt_secret_key or self.jwt_secret_key == "your_secret_key_here":
            raise ValueError(
                "JWT_SECRET_KEY no está configurado. Genera uno con: openssl rand -hex 32"
            )
        if len(self.jwt_secret_key) < 32:
            raise ValueError("JWT_SECRET_KEY debe tener al menos 32 caracteres")
        return self


settings = Settings()
