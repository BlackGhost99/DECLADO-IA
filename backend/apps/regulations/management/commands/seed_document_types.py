"""Populate stable document types. This never publishes a customs obligation."""

from django.core.management.base import BaseCommand

from apps.regulations.models import DocumentType
from apps.regulations.taxonomy import TYPES


class Command(BaseCommand):
    help = "Crée les types documentaires sans créer d'obligation juridique"

    def handle(self, *args, **kwargs):
        for code, spec in TYPES.items():
            DocumentType.objects.update_or_create(
                code=code, defaults={"label_fr": spec.fr, "label_en": spec.en}
            )
        self.stdout.write(self.style.SUCCESS(f"{len(TYPES)} types chargés ; aucune règle publiée."))
