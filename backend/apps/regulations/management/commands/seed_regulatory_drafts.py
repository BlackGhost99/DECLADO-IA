"""Article-to-document mapping for review. Never automatically publish requirements."""

from datetime import date

from django.core.management.base import BaseCommand

from apps.regulations.models import DocumentRequirement, DocumentType, RegulatorySource

# These mappings require review for scope, exemptions, legal effective date,
# accepted equivalences, and the national additions for each CEMAC country.
ROWS = (
    ("consumption", "2(a)", "commercial_invoice", {}),
    ("consumption", "2(b)", "customs_value_declaration", {}),
    ("consumption", "2(c)", "import_goods_declaration", {}),
    ("consumption", "2(d)", "transport_title", {}),
    ("consumption", "2(e)", "previous_customs_declaration", {"requires_previous_regime": True}),
    ("consumption", "2(f)", "packing_list", {}),
    ("consumption", "2(g)", "certificate_of_origin", {}),
    ("consumption", "2(h)", "privileged_regime_attestation", {"requires_privileged_regime": True}),
    ("transit", "3, 2(a)", "commercial_invoice", {}),
    ("transit", "3, 2(d)", "transport_title", {}),
    ("transit", "3, 2(f)", "packing_list", {}),
    ("transit", "3", "guarantee_document", {}),
    ("warehouse", "4, 2(a)", "commercial_invoice", {}),
    ("warehouse", "4, 2(c)", "import_goods_declaration", {}),
    ("warehouse", "4, 2(d)", "transport_title", {}),
    ("warehouse", "4, 2(f)", "packing_list", {}),
)


class Command(BaseCommand):
    help = "Importe en BROUILLON des exigences CEMAC pour revue juridique, sans activation"

    def handle(self, *args, **kwargs):
        source, _ = RegulatorySource.objects.get_or_create(
            reference="11/22-CEMAC-UEAC-010A-CM-38",
            defaults={
                "title": "Documents à annexer aux déclarations en détail",
                "scope": RegulatorySource.Scope.CEMAC,
                "official_url": (
                    "https://cemac.int/wp-content/uploads/2025/05/"
                    "decis-fixant-documents-annexer-declarations-detail.pdf"
                ),
                "adopted_on": date(2022, 10, 28),
                "verification_notes": "Revue juridique et dates d'applicabilité requises avant publication.",
            },
        )
        additional_types = (
            ("transport_title", "Titre de transport", "Transport document"),
            (
                "privileged_regime_attestation",
                "Attestation de régime privilégié",
                "Preferential regime evidence",
            ),
        )
        for code, fr, en in additional_types:
            DocumentType.objects.get_or_create(code=code, defaults={"label_fr": fr, "label_en": en})
        for regime, article, code, conditions in ROWS:
            DocumentRequirement.objects.get_or_create(
                source=source,
                article=article,
                document_type=DocumentType.objects.get(code=code),
                operation="import",
                regime=regime,
                defaults={
                    "conditions": conditions,
                    "published": False,
                    "verified": False,
                    "notes": "Brouillon de transcription : contrôler équivalences, dispenses et vigueur.",
                },
            )
        self.stdout.write(self.style.SUCCESS(f"{len(ROWS)} exigences candidates enregistrées ; aucune publiée."))
