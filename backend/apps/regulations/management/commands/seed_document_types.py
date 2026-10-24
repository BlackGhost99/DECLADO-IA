"""Vocabulaire documentaire, distinct des obligations juridiques."""
from django.core.management.base import BaseCommand

from apps.regulations.models import DocumentType

DOCUMENT_TYPES = {
    "commercial_invoice": ("Facture commerciale", "Commercial invoice"),
    "freight_invoice": ("Facture de fret", "Freight invoice"),
    "insurance_certificate": ("Attestation ou certificat d’assurance", "Insurance certificate"),
    "bill_of_lading": ("Connaissement maritime (B/L)", "Bill of lading"),
    "air_waybill": ("Lettre de transport aérien (LTA)", "Air waybill"),
    "road_consignment_note": ("Lettre de voiture", "Road consignment note"),
    "packing_list": ("Liste de colisage", "Packing list"),
    "certificate_of_origin": ("Certificat d’origine", "Certificate of origin"),
    "customs_value_declaration": ("Déclaration des éléments de la valeur", "Customs value declaration"),
    "import_goods_declaration": ("Déclaration d’importation de biens", "Goods import declaration"),
    "previous_customs_declaration": ("Déclaration du régime précédent", "Previous customs declaration"),
    "guarantee_document": ("Justificatif de garantie", "Guarantee evidence"),
    "sectoral_permit": ("Autorisation ou certificat sectoriel", "Sectoral permit"),
    "cargo_tracking_note": ("Bordereau de suivi de cargaison", "Cargo tracking note"),
}


class Command(BaseCommand):
    help = "Crée les types de documents sans publier d'obligation juridique"

    def handle(self, *args, **kwargs):
        for code, (fr, en) in DOCUMENT_TYPES.items():
            DocumentType.objects.update_or_create(code=code, defaults={"label_fr": fr, "label_en": en})
        self.stdout.write(self.style.SUCCESS(f"{len(DOCUMENT_TYPES)} types chargés ; aucune règle publiée."))
