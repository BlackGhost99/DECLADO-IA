"""Identité globale d'un utilisateur. Les droits métier passent par Membership (organizations)."""

import uuid

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create(self, email, password, **extra):
        if not email:
            raise ValueError("Adresse e-mail obligatoire")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra["is_staff"] = True
        extra["is_superuser"] = True
        return self._create(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    """Un compte désactivé conserve ses décisions historiques (pas de suppression)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=200, blank=True)
    interface_locale = models.CharField(
        max_length=2, default="fr",
        choices=[("fr", "Français"), ("en", "English"), ("es", "Español"), ("ar", "العربية")]
    )
    is_active = models.BooleanField(default=True)
    # Administration technique de la plateforme : n'ouvre aucun accès métier aux pièces.
    is_staff = models.BooleanField(default=False)
    # Gestionnaire du référentiel tarifaire (permission distincte, hors société).
    is_reference_manager = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "utilisateur"

    def save(self, *args, **kwargs):
        self.email = (self.email or "").strip().lower()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email
