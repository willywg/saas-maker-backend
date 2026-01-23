"""Email configuration for fastapi-mail."""

from pathlib import Path

from fastapi_mail import ConnectionConfig

from app.core.config import settings


def get_mail_config() -> ConnectionConfig:
    """Get email connection configuration.

    Dynamically handles credentials for different environments:
    - Local (Mailcatcher): No credentials needed
    - Production (Brevo): Credentials required
    """
    return ConnectionConfig(
        MAIL_USERNAME=settings.smtp_user,
        MAIL_PASSWORD=settings.smtp_password,
        MAIL_FROM=settings.smtp_from_email,
        MAIL_FROM_NAME=settings.smtp_from_name,
        MAIL_PORT=settings.smtp_port,
        MAIL_SERVER=settings.smtp_host,
        MAIL_STARTTLS=settings.smtp_tls,
        MAIL_SSL_TLS=settings.smtp_ssl,
        # False for Mailcatcher, True for Brevo
        USE_CREDENTIALS=bool(settings.smtp_user and settings.smtp_password),
        VALIDATE_CERTS=settings.smtp_tls,
        TEMPLATE_FOLDER=Path(__file__).parent.parent / "templates" / "emails",
    )
