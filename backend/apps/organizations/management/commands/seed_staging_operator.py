"""Idempotent staging-only platform administrator bootstrap.

Credentials are supplied via Render environment variables, never in source.
"""
import os

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from apps.accounts.models import User
from apps.audit.services import record_event


class Command(BaseCommand):
    help = "Initialise le super-administrateur du staging avec des variables Render."

    @transaction.atomic
    def handle(self, *args, **options):
        if settings.DEBUG or os.environ.get("APP_ENV", "").lower() != "staging":
            raise CommandError("Commande réservée au staging public non-debug.")
        if not getattr(settings, "STAGING_SIMPLE_LOGIN", False):
            raise CommandError("Configuration staging attendue.")

        email = os.environ.get("STAGING_OPERATOR_EMAIL", "").strip().lower()
        password = os.environ.get("STAGING_OPERATOR_PASSWORD", "")
        if not email or not password:
            raise CommandError("STAGING_OPERATOR_EMAIL et STAGING_OPERATOR_PASSWORD sont requis.")
        try:
            validate_email(email)
        except ValidationError as exc:
            raise CommandError("Adresse de l'exploitant invalide.") from exc

        user, created = User.objects.get_or_create(email=email)
        desired = {
            "full_name": "Super-administrateur DECLADO IA (staging)",
            "is_platform_operator": True,
            "is_reference_manager": True,
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        }
        updates = []
        for key, value in desired.items():
            if getattr(user, key) != value:
                setattr(user, key, value)
                updates.append(key)
        if not user.check_password(password):
            user.set_password(password)
            updates.append("password")
        if updates:
            user.save(update_fields=updates)
        if created:
            record_event(organization=None, actor=user, event_type="platform.staging_operator_created", entity=user)
        self.stdout.write(self.style.SUCCESS("Super-administrateur staging prêt."))
