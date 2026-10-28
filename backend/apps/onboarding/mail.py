"""Envoi facultatif du lien d'invitation par e-mail.

Le lien copiable reste la voie de secours : sans serveur SMTP, ou si l'adresse de l'interface
n'est joignable que depuis ce PC, rien n'est envoyé et l'écran le dit. Le jeton n'apparaît que
dans l'e-mail lui-même, jamais dans le journal d'activité.
"""

import ipaddress
import logging
from urllib.parse import urlsplit

from django.conf import settings
from django.core.mail import send_mail

from apps.audit.services import record_event

from .models import Invitation

logger = logging.getLogger(__name__)

# Statuts rendus à l'interface.
SENT, FAILED, DISABLED, LOCAL_ADDRESS, NO_ADDRESS = "sent", "failed", "disabled", "local_address", "no_address"

_MESSAGES = {
    "fr": (
        "Invitation à rejoindre {org} sur ClairTransit",
        "Bonjour {name},\n\n{org} vous invite à rejoindre son espace ClairTransit.\n\n"
        "Ouvrez ce lien pour choisir votre mot de passe (valable 72 heures, une seule fois) :\n{link}\n\n"
        "Personne ne vous demandera ce mot de passe. Si vous n'attendiez pas cette invitation, ignorez ce message.",
    ),
    "en": (
        "Invitation to join {org} on ClairTransit",
        "Hello {name},\n\n{org} invites you to join its ClairTransit workspace.\n\n"
        "Open this link to choose your password (valid for 72 hours, single use):\n{link}\n\n"
        "Nobody will ever ask you for this password. If you were not expecting this invitation, ignore this message.",
    ),
    "es": (
        "Invitación para unirse a {org} en ClairTransit",
        "Hola {name}:\n\n{org} le invita a unirse a su espacio ClairTransit.\n\n"
        "Abra este enlace para elegir su contraseña (válido 72 horas, un solo uso):\n{link}\n\n"
        "Nadie le pedirá nunca esta contraseña. Si no esperaba esta invitación, ignore este mensaje.",
    ),
    "ar": (
        "دعوة للانضمام إلى {org} على ClairTransit",
        "مرحبًا {name}،\n\nتدعوك {org} للانضمام إلى مساحتها على ClairTransit.\n\n"
        "افتح هذا الرابط لاختيار كلمة المرور (صالح 72 ساعة، لمرة واحدة):\n{link}\n\n"
        "لن يطلب منك أحد كلمة المرور هذه أبدًا. إذا لم تكن تنتظر هذه الدعوة، فتجاهل هذه الرسالة.",
    ),
}


def app_url(request) -> str:
    """Adresse publique configurée, sinon l'origine de la page si elle est déclarée de confiance."""
    if settings.PUBLIC_APP_URL:
        return settings.PUBLIC_APP_URL
    origin = request.headers.get("Origin", "")
    return origin if origin in settings.CSRF_TRUSTED_ORIGINS else ""


def _local_only(url: str) -> bool:
    host = urlsplit(url).hostname or ""
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def send_invitation_email(*, invitation: Invitation, token: str, base_url: str, actor) -> str:
    if not settings.INVITATION_EMAIL_ENABLED:
        return DISABLED
    if not base_url:
        return NO_ADDRESS
    if _local_only(base_url):
        # Un lien 127.0.0.1 n'ouvrirait que le PC de l'invité, pas ce serveur.
        return LOCAL_ADDRESS
    organization = invitation.organization
    subject, body = _MESSAGES.get(organization.default_locale, _MESSAGES["fr"])
    values = {
        "org": organization.name,
        "name": invitation.full_name or invitation.email,
        "link": f"{base_url.rstrip('/')}/#/activation/{token}",
    }
    try:
        send_mail(subject.format(**values), body.format(**values), None, [invitation.email])
    except Exception:
        logger.warning("Invitation e-mail not sent", exc_info=True)
        record_event(organization=organization, actor=actor, event_type="invitation.email_failed", entity=invitation)
        return FAILED
    record_event(organization=organization, actor=actor, event_type="invitation.email_sent", entity=invitation)
    return SENT
