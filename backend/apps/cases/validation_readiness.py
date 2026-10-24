"""Final internal validation gate. Fail closed until regulatory and tax checks exist."""
from apps.tariffs.models import PublicationState

from .models import CaseDocument


def validation_readiness(revision, assessment):
    """Extend completeness with hard evidence requirements for an operational file.

    No tax engine is connected yet: never claim fiscal validation without a
    persisted and verified calculation.
    """
    blocking = list(assessment["blocking"])
    warnings = list(assessment["warnings"])
    def issue(field, message):
        blocking.append({
            "scope": "revision",
            "id": str(revision.pk),
            "field": field,
            "message": message,
            "label": f"Révision {revision.revision_no}",
        })

    edition = revision.target_edition
    if edition is None or edition.publication_state != PublicationState.OPERATIONAL:
        issue("target_edition", "Un référentiel tarifaire opérationnel et publié est obligatoire.")
    live_docs = revision.documents.filter(replaced_by__isnull=True)
    if not live_docs.filter(usage=CaseDocument.Usage.INVOICE).exists():
        issue("documents.invoice", "Facture commerciale justificative obligatoire.")
    if live_docs.exclude(document__readability="ok").exists():
        issue("documents.readability", "Un ou plusieurs justificatifs sont illisibles.")
    if not revision.goods_lines.exists():
        issue("goods_lines", "Aucune marchandise à contrôler.")

    # Future calculation engine must persist the calculation, edition, inputs
    # fingerprint and rates before this gate can become passable.
    issue("tax_calculation", "Calcul fiscal vérifié indisponible : validation finale bloquée.")
    return {"blocking": blocking, "warnings": warnings, "complete": not blocking}
