from pydantic_settings import BaseSettings


class Settings(BaseSettings):
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
    frontend_url: str = "http://localhost:5173"

    # Password Reset
    password_reset_token_expire_minutes: int = 30

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
