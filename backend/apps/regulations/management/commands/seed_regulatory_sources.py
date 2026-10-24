"""Source CEMAC enregistrée en brouillon ; l'applicabilité doit être validée."""
from datetime import date

from django.core.management.base import BaseCommand
from apps.regulations.models import RegulatorySource


class Command(BaseCommand):
    help = "Enregistre la référence 11/22, non vérifiée et sans obligations activées"

    def handle(self, *args, **kwargs):
        source, _ = RegulatorySource.objects.get_or_create(
            reference="11/22-CEMAC-UEAC-010A-CM-38",
            defaults={
                "title": "Documents à annexer aux déclarations en détail",
                "scope": RegulatorySource.Scope.CEMAC,
                "official_url": "https://cemac.int/wp-content/uploads/2025/05/decis-fixant-documents-annexer-declarations-detail.pdf",
                "adopted_on": date(2022, 10, 28),
                "verification_notes": "Applicabilité et entrée en vigueur à vérifier avant publication.",
            },
        )
        self.stdout.write(f"Source enregistrée : {source.reference} (aucune règle publiée).")
