"""Email service for sending transactional emails."""

import logging
from datetime import datetime

from fastapi_mail import FastMail, MessageSchema, MessageType

from app.core.config import settings
from app.core.email import get_mail_config

logger = logging.getLogger(__name__)

# Role labels in Spanish
ROLE_LABELS = {
    "owner": "Propietario",
    "admin": "Administrador",
    "member": "Miembro",
}


def _get_common_template_vars() -> dict:
    """Get common template variables for all emails."""
    return {
        "app_name": settings.app_name,
        "year": datetime.now().year,
    }


async def send_welcome_email(
    email_to: str,
    user_name: str | None,
    organization_name: str,
    dashboard_url: str,
) -> None:
    """Send welcome email to new user.

    Args:
        email_to: Recipient email address
        user_name: User's full name (or None)
        organization_name: Name of the organization
        dashboard_url: URL to the dashboard
    """
    try:
        conf = get_mail_config()
        template_vars = _get_common_template_vars()
        template_vars.update({
            "greeting": "¡Bienvenido",
            "user_name": user_name or email_to.split("@")[0],
            "organization_name": organization_name,
            "dashboard_url": dashboard_url,
        })

        message = MessageSchema(
            subject=f"¡Bienvenido a {conf.MAIL_FROM_NAME}!",
            recipients=[email_to],
            template_body=template_vars,
            subtype=MessageType.html,
        )

        fm = FastMail(conf)
        await fm.send_message(message, template_name="welcome.html")
        logger.info(f"Welcome email sent to {email_to}")
    except Exception as e:
        # Don't propagate error - this is a background task
        logger.error(f"Failed to send welcome email to {email_to}: {e}")


async def send_invitation_email(
    email_to: str,
    organization_name: str,
    inviter_name: str,
    role: str,
    invite_url: str,
    expires_at: str,
) -> None:
    """Send invitation email to join organization.

    Args:
        email_to: Recipient email address
        organization_name: Name of the organization
        inviter_name: Name of the person sending the invitation
        role: Role being assigned (admin, member)
        invite_url: Full URL to accept the invitation
        expires_at: Formatted expiration date string
    """
    try:
        conf = get_mail_config()
        role_label = ROLE_LABELS.get(role, role)

        template_vars = _get_common_template_vars()
        template_vars.update({
            "organization_name": organization_name,
            "inviter_name": inviter_name,
            "role_label": role_label,
            "invite_url": invite_url,
            "expires_at": expires_at,
        })

        message = MessageSchema(
            subject=f"Invitación a {organization_name} - {conf.MAIL_FROM_NAME}",
            recipients=[email_to],
            template_body=template_vars,
            subtype=MessageType.html,
        )

        fm = FastMail(conf)
        await fm.send_message(message, template_name="invitation.html")
        logger.info(f"Invitation email sent to {email_to}")
    except Exception as e:
        # Don't propagate error - this is a background task
        logger.error(f"Failed to send invitation email to {email_to}: {e}")


async def send_password_reset_email(
    email_to: str,
    user_name: str | None,
    reset_url: str,
    expire_minutes: int,
) -> None:
    """Send password reset link."""
    try:
        conf = get_mail_config()
        template_vars = _get_common_template_vars()
        template_vars.update({
            "user_name": user_name or email_to.split("@")[0],
            "reset_url": reset_url,
            "expire_minutes": expire_minutes,
        })

        message = MessageSchema(
            subject=f"Restablecer contraseña - {conf.MAIL_FROM_NAME}",
            recipients=[email_to],
            template_body=template_vars,
            subtype=MessageType.html,
        )

        fm = FastMail(conf)
        await fm.send_message(message, template_name="password_reset.html")
        logger.info(f"Password reset email sent to {email_to}")
    except Exception as e:
        logger.error(f"Failed to send password reset email to {email_to}: {e}")
