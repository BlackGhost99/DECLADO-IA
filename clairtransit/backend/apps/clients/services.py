from django.db import transaction
from django.db.models import Q

from apps.audit.services import record_event
from apps.core.exceptions import ApiError, RevisionConflict

from .models import Importer, normalize_name

__all__ = ["create_importer", "find_possible_duplicates", "normalize_name", "update_importer"]

EDITABLE_FIELDS = ("name", "identifiers", "contacts", "address", "notes")


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
