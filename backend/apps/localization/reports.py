"""Localized operational summaries; official tariff wording remains unmodified.

This is a preparation summary, never a customs declaration or legal translation.
"""

from datetime import date

SUPPORTED = ("fr", "en", "es", "ar")
MESSAGES = {
    "fr": {
        "title": "Résumé du dossier",
        "reference": "Référence",
        "status": "Statut",
        "documents": "Documents",
        "invoices": "Factures",
        "note": "Document préparatoire interne : ne constitue pas une validation douanière.",
    },
    "en": {
        "title": "Case summary",
        "reference": "Reference",
        "status": "Status",
        "documents": "Documents",
        "invoices": "Invoices",
        "note": "Internal preparatory document: not customs clearance approval.",
    },
    "es": {
        "title": "Resumen del expediente",
        "reference": "Referencia",
        "status": "Estado",
        "documents": "Documentos",
        "invoices": "Facturas",
        "note": "Documento interno preparatorio: no constituye aprobación aduanera.",
    },
    "ar": {
        "title": "ملخص الملف",
        "reference": "المرجع",
        "status": "الحالة",
        "documents": "المستندات",
        "invoices": "الفواتير",
        "note": "وثيقة تحضيرية داخلية، وليست موافقة من الجمارك.",
    },
}


def summary_payload(*, case, locale: str) -> dict:
    if locale not in SUPPORTED:
        raise ValueError("Unsupported locale")
    revision = case.current_revision
    labels = MESSAGES[locale]
    return {
        "locale": locale,
        "direction": "rtl" if locale == "ar" else "ltr",
        "labels": labels,
        "reference": case.reference,
        "case_title": case.title,
        "state_code": revision.state,
        # Official legal wording is never translated here.
        "territory": revision.territory,
        "documents_count": revision.documents.count(),
        "invoices_count": revision.invoices.count(),
        "generated_on": date.today().isoformat(),
        "is_official_declaration": False,
    }
