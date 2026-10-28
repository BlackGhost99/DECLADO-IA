from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.audit.services import record_event
from apps.core.exceptions import ApiError, RevisionConflict

from .models import Importer, normalize_name

__all__ = ["create_importer", "find_possible_duplicates", "normalize_name", "set_ai_refusal", "update_importer"]

EDITABLE_FIELDS = ("name", "identifiers", "contacts", "address", "notes")


@transaction.atomic
def set_ai_refusal(*, organization, actor, importer_id, refused: bool, can_lift: bool) -> Importer:
    """Le refus du client protège ses pièces : tout membre peut le noter, seul un administrateur le lève."""
    importer = Importer.objects.for_organization(organization).select_for_update().filter(pk=importer_id).first()
    if importer is None:
        raise ApiError("NOT_FOUND", "Importateur introuvable.", 404)
    if refused == importer.ai_refused:
        return importer
    if not refused and not can_lift:
        raise ApiError("FORBIDDEN", "Seul un administrateur de la société peut lever le refus du client.", 403)
    importer.ai_refused = refused
    importer.ai_refused_at = timezone.now() if refused else None
    importer.ai_refused_by = actor if refused else None
    importer.row_version += 1
    importer.save()
    record_event(
        organization=organization,
        actor=actor,
        event_type="importer.ai_refusal_set" if refused else "importer.ai_refusal_lifted",
        entity=importer,
        previous={"ai_refused": not refused},
        current={"ai_refused": refused},
    )
    return importer


def find_possible_duplicates(organization, *, name: str, identifiers: dict, exclude_id=None):
    """Doublons possibles dans la même société : signalés, jamais fusionnés automatiquement."""
    query = Q(normalized_name=normalize_name(name))
    for key, value in (identifiers or {}).items():
        value = str(value).strip()
        if value:
            query |= Q(**{f"identifiers__{key}": value})
    qs = Importer.objects.for_organization(organization).filter(query)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return list(qs[:10])


def _snapshot(importer: Importer) -> dict:
    return {f: getattr(importer, f) for f in EDITABLE_FIELDS}


@transaction.atomic
def create_importer(*, organization, actor, data: dict) -> tuple[Importer, list[Importer]]:
    duplicates = find_possible_duplicates(organization, name=data["name"], identifiers=data.get("identifiers"))
    importer = Importer.objects.create(organization=organization, **{f: data[f] for f in EDITABLE_FIELDS if f in data})
    record_event(
        organization=organization,
        actor=actor,
        event_type="importer.created",
        entity=importer,
        current={"name": importer.name},
    )
    return importer, duplicates


@transaction.atomic
def update_importer(*, organization, actor, importer_id, expected_version, data: dict) -> Importer:
    if expected_version is None:
        raise ApiError("ROW_VERSION_REQUIRED", "La version de l'élément (row_version) est obligatoire.", 400)
    importer = Importer.objects.for_organization(organization).select_for_update().get(pk=importer_id)
    if importer.row_version != expected_version:
        raise RevisionConflict(expected_version, importer.row_version)
    before = _snapshot(importer)
    for field in EDITABLE_FIELDS:
        if field in data:
            setattr(importer, field, data[field])
    importer.row_version += 1
    importer.save()
    after = _snapshot(importer)
    changed = [f for f in EDITABLE_FIELDS if before[f] != after[f]]
    record_event(
        organization=organization,
        actor=actor,
        event_type="importer.updated",
        entity=importer,
        previous={f: before[f] for f in changed},
        current={f: after[f] for f in changed},
    )
    return importer
