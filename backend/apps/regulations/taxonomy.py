"""Canonical documentary taxonomy v1. Codes are stable identifiers, not legal requirements.

Never infer an exact commercial document from generic OCR usage alone.
"""

from dataclasses import dataclass

from apps.core.exceptions import ApiError


@dataclass(frozen=True)
class TypeSpec:
    family: str
    fr: str
    en: str
    usage: str = "other"


FAMILIES = {
    "commercial": "Documents commerciaux",
    "transport": "Transport et logistique",
    "insurance": "Assurance",
    "origin": "Origine et conformité",
    "customs": "Documents douaniers",
    "regulatory": "Autorisations et certificats réglementaires",
    "supporting": "Justificatifs complémentaires",
}

TYPES: dict[str, TypeSpec] = {
    "commercial_invoice": TypeSpec("commercial", "Facture commerciale", "Commercial invoice", "invoice"),
    "proforma_invoice": TypeSpec("commercial", "Facture pro forma", "Pro forma invoice"),
    "freight_invoice": TypeSpec("commercial", "Facture de fret", "Freight invoice"),
    "insurance_invoice": TypeSpec("insurance", "Facture d'assurance", "Insurance invoice"),
    "purchase_order": TypeSpec("commercial", "Bon de commande", "Purchase order"),
    "sales_contract": TypeSpec("commercial", "Contrat commercial", "Sales contract"),
    "packing_list": TypeSpec("commercial", "Liste de colisage", "Packing list", "packing_list"),
    "certificate_of_inspection": TypeSpec("regulatory", "Certificat d'inspection", "Inspection certificate"),
    "insurance_certificate": TypeSpec("insurance", "Attestation ou certificat d’assurance", "Insurance certificate"),
    "insurance_policy": TypeSpec("insurance", "Police d'assurance", "Insurance policy"),
    "bill_of_lading": TypeSpec("transport", "Connaissement maritime (B/L)", "Bill of lading", "transport"),
    "sea_waybill": TypeSpec("transport", "Lettre de transport maritime", "Sea waybill", "transport"),
    "air_waybill": TypeSpec("transport", "Lettre de transport aérien (LTA)", "Air waybill", "transport"),
    "road_consignment_note": TypeSpec("transport", "Lettre de voiture", "Road consignment note", "transport"),
    "rail_consignment_note": TypeSpec("transport", "Lettre de voiture ferroviaire", "Rail consignment note", "transport"),
    "cargo_manifest": TypeSpec("transport", "Manifeste de cargaison", "Cargo manifest", "transport"),
    "delivery_note": TypeSpec("transport", "Bon de livraison", "Delivery note"),
    "freight_receipt": TypeSpec("transport", "Reçu de fret", "Freight receipt"),
    "cargo_tracking_note": TypeSpec("transport", "Bordereau de suivi de cargaison", "Cargo tracking note"),
    "certificate_of_origin": TypeSpec("origin", "Certificat d’origine", "Certificate of origin", "origin"),
    "preferential_origin_proof": TypeSpec("origin", "Justificatif d'origine préférentielle", "Preferential origin proof", "origin"),
    "certificate_of_conformity": TypeSpec("origin", "Certificat de conformité", "Certificate of conformity"),
    "customs_value_declaration": TypeSpec("customs", "Déclaration des éléments de la valeur", "Customs value declaration"),
    "import_goods_declaration": TypeSpec("customs", "Déclaration d’importation de biens", "Goods import declaration"),
    "export_goods_declaration": TypeSpec("customs", "Déclaration d'exportation", "Goods export declaration"),
    "previous_customs_declaration": TypeSpec("customs", "Déclaration du régime précédent", "Previous customs declaration"),
    "customs_payment_receipt": TypeSpec("customs", "Quittance douanière", "Customs payment receipt"),
    "guarantee_document": TypeSpec("customs", "Justificatif de garantie", "Guarantee evidence"),
    "sectoral_permit": TypeSpec("regulatory", "Autorisation ou certificat sectoriel", "Sectoral permit"),
    "import_license": TypeSpec("regulatory", "Licence d'importation", "Import license"),
    "health_certificate": TypeSpec("regulatory", "Certificat sanitaire", "Health certificate"),
    "phytosanitary_certificate": TypeSpec("regulatory", "Certificat phytosanitaire", "Phytosanitary certificate"),
    "technical_product_sheet": TypeSpec("supporting", "Fiche technique du produit", "Product technical sheet"),
    "supplier_declaration": TypeSpec("supporting", "Déclaration du fournisseur", "Supplier declaration"),
    "other_supporting_document": TypeSpec("supporting", "Autre justificatif", "Other supporting document"),
}

# Only these old usages are unambiguous; never infer bill_of_lading from transport.
LEGACY_UNAMBIGUOUS = {"packing_list": "packing_list", "origin": "certificate_of_origin"}


def require_type(code: str) -> TypeSpec:
    spec = TYPES.get(code)
    if spec is None:
        raise ApiError("INVALID_DOCUMENT_TYPE", "Type documentaire inconnu.", 422, {"document_type_code": code})
    return spec


def catalog() -> list[dict]:
    return [
        {"code": code, "family": spec.family, "label_fr": spec.fr, "label_en": spec.en, "usage": spec.usage}
        for code, spec in TYPES.items()
    ]
