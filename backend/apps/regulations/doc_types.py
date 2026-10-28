"""Type d'une pièce du dossier : confirmé par un agent, détecté d'après le titre, ou déduit de l'usage.

Le type confirmé (DocumentClassification) prime toujours. Un type détecté reste une proposition
affichée avec le texte qui la justifie ; il sert à choisir la lecture et à cocher la pièce dans le
contrôle documentaire comme « reçue, à vérifier », jamais comme vérifiée (LEC-07).
"""

from django.core.exceptions import ObjectDoesNotExist

from .taxonomy import TYPES

CONFIRMED, DETECTED, USAGE = "confirmed", "detected", "usage"

# Usage enregistré sur la pièce (icône, liste, lecture) selon le type de la taxonomie.
USAGE_FOR_FAMILY = {"transport": "transport", "insurance": "insurance"}
USAGE_FOR_TYPE = {
    "commercial_invoice": "invoice",
    "proforma_invoice": "invoice",
    "freight_invoice": "freight",
    "freight_receipt": "freight",
    "packing_list": "packing_list",
    "certificate_of_origin": "origin",
    "preferential_origin_proof": "origin",
}
# Seuls ces usages désignent un type sans ambiguïté ; « transport » ne prouve pas un B/L.
TYPE_FOR_USAGE = {"packing_list": "packing_list", "origin": "certificate_of_origin", "freight": "freight_invoice"}


def usage_for_type(code: str) -> str:
    spec = TYPES.get(code)
    if spec is None:
        return "other"
    return USAGE_FOR_TYPE.get(code) or USAGE_FOR_FAMILY.get(spec.family, "other")


def _agrees(link) -> bool:
    """Le type lu ne contredit pas l'usage choisi par l'agent au dépôt (ou l'usage vient du titre)."""
    detection = link.type_detection or {}
    return bool(detection.get("applied")) or link.usage in ("other", usage_for_type(link.detected_type))


def mismatch_of(link) -> dict | None:
    """Titre lu qui contredit l'usage choisi au dépôt : montré à l'agent, jamais appliqué d'office."""
    if not link.detected_type or _agrees(link):
        return None
    try:
        if link.confirmed_classification is not None:
            return None
    except ObjectDoesNotExist:
        pass
    spec = TYPES.get(link.detected_type)
    return {
        "code": link.detected_type,
        "label": spec.fr if spec else link.detected_type,
        "label_en": spec.en if spec else link.detected_type,
        "evidence": link.type_detection or {},
    }


def type_of(link) -> dict | None:
    """{code, label, source, evidence} ou None si la pièce n'a pas de type connu."""
    try:
        confirmed = link.confirmed_classification
    except ObjectDoesNotExist:
        confirmed = None
    if confirmed is not None:
        code, source, evidence = confirmed.document_type.code, CONFIRMED, {"reason": confirmed.reason}
    elif link.detected_type and _agrees(link):
        code, source, evidence = link.detected_type, DETECTED, link.type_detection or {}
    elif link.usage in TYPE_FOR_USAGE:
        code, source, evidence = TYPE_FOR_USAGE[link.usage], USAGE, {}
    else:
        return None
    spec = TYPES.get(code)
    return {
        "code": code,
        "label": spec.fr if spec else code,
        "label_en": spec.en if spec else code,
        "source": source,
        "evidence": evidence,
    }
