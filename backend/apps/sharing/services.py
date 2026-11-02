"""Partage de dossiers : code partenaire, invitation, acceptation, retrait, remarques, instantané.

Chaque transition est journalisée chez le propriétaire ET chez le partenaire. La société partenaire
ne lit jamais les tables du dossier : elle reçoit `snapshot()`, construit côté propriétaire.
"""

import secrets

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.services import record_event
from apps.core.exceptions import ApiError
from apps.organizations.business_permissions import organization_profiles

from .models import CaseShare, CaseShareNote, PartnerCode

ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sans 0/O ni 1/I : se dicte au téléphone
NOT_FOUND = ("NOT_FOUND", "Élément introuvable.", 404)


def _new_code() -> str:
    raw = "".join(secrets.choice(ALPHABET) for _ in range(8))
    return f"CT-{raw[:4]}-{raw[4:]}"


def normalize_code(value: str) -> str:
    compact = "".join(ch for ch in (value or "").upper() if ch.isalnum())
    if compact.startswith("CT"):
        compact = compact[2:]
    return f"CT-{compact[:4]}-{compact[4:8]}" if len(compact) == 8 else ""


def partner_code(organization) -> PartnerCode:
    existing = PartnerCode.objects.filter(organization=organization).first()
    if existing:
        return existing
    for _ in range(5):
        try:
            with transaction.atomic():
                return PartnerCode.objects.create(organization=organization, code=_new_code())
        except IntegrityError:
            existing = PartnerCode.objects.filter(organization=organization).first()
            if existing:
                return existing
    raise ApiError("CODE_UNAVAILABLE", "Code partenaire indisponible, réessayez.", 503)


@transaction.atomic
def regenerate_code(*, organization, actor) -> PartnerCode:
    """COL-01 : un nouveau code rend l'ancien inutilisable ; les partages existants restent."""
    current = partner_code(organization)
    previous = current.code
    for _ in range(5):
        candidate = _new_code()
        if not PartnerCode.objects.filter(code=candidate).exists():
            current.code = candidate
            current.row_version += 1
            current.save(update_fields=["code", "row_version", "updated_at"])
            record_event(organization=organization, actor=actor, event_type="partner_code.regenerated",
                         entity=current, previous={"code": previous}, current={"code": candidate})  # fmt: skip
            return current
    raise ApiError("CODE_UNAVAILABLE", "Code partenaire indisponible, réessayez.", 503)


def _both(share: CaseShare, actor, event_type: str, current: dict | None = None, previous: dict | None = None):
    for org in (share.organization, share.partner):
        record_event(organization=org, actor=actor, event_type=event_type, entity=share,
                     previous=previous, current={"case": share.case.reference, **(current or {})})  # fmt: skip


@transaction.atomic
def create_share(*, organization, actor, case, code: str, level: str, message: str = "") -> CaseShare:
    """COL-02 : le propriétaire invite une société par son code ; rien n'est visible avant acceptation."""
    if level not in CaseShare.Level.values:
        raise ApiError("VALIDATION_ERROR", "Niveau de partage inconnu.", 400, {"field": "level"})
    normalized = normalize_code(code)
    target = PartnerCode.objects.select_related("organization").filter(code=normalized).first() if normalized else None
    if target is None or not target.organization.active:
        raise ApiError("PARTNER_NOT_FOUND", "Aucune société active ne correspond à ce code.", 404, {"field": "code"})
    partner = target.organization
    if partner.pk == organization.pk:
        raise ApiError("SELF_SHARE", "Ce code est celui de votre propre société.", 400, {"field": "code"})
    if case.organization_id != organization.pk:
        raise ApiError(*NOT_FOUND)
    try:
        with transaction.atomic():
            share = CaseShare.objects.create(
                organization=organization,
                case=case,
                partner=partner,
                level=level,
                message=" ".join((message or "").split())[:500],
                created_by=actor,
            )
    except IntegrityError:
        raise ApiError("SHARE_EXISTS", "Ce dossier est déjà partagé avec cette société.", 409) from None
    _both(share, actor, "case_share.created", {"partner": partner.name, "level": level})
    return share


def _lock(share: CaseShare) -> CaseShare:
    return CaseShare.objects.select_for_update().select_related("case", "organization", "partner").get(pk=share.pk)


@transaction.atomic
def decide_share(*, share: CaseShare, actor, accept: bool) -> CaseShare:
    """COL-03 : la société invitée accepte ou refuse ; seul un partage en attente se décide."""
    share = _lock(share)
    if share.status != CaseShare.Status.PENDING:
        raise ApiError("SHARE_ALREADY_DECIDED", "Ce partage a déjà été traité.", 409)
    share.status = CaseShare.Status.ACCEPTED if accept else CaseShare.Status.REFUSED
    share.decided_by = actor
    share.decided_at = timezone.now()
    share.row_version += 1
    share.save()
    _both(share, actor, "case_share.accepted" if accept else "case_share.refused")
    return share


@transaction.atomic
def revoke_share(*, share: CaseShare, actor, reason: str = "") -> CaseShare:
    """COL-04 : le propriétaire retire un partage en attente ou accepté ; l'accès cesse aussitôt."""
    share = _lock(share)
    if share.status not in (CaseShare.Status.PENDING, CaseShare.Status.ACCEPTED):
        raise ApiError("SHARE_CLOSED", "Ce partage n'est plus actif.", 409)
    previous = {"status": share.status}
    share.status = CaseShare.Status.REVOKED
    share.revoked_at = timezone.now()
    share.row_version += 1
    share.save()
    _both(share, actor, "case_share.revoked", {"reason": (reason or "").strip()[:500]}, previous)
    return share


@transaction.atomic
def add_note(*, share: CaseShare, organization, actor, text: str) -> CaseShareNote:
    """COL-05 : remarque des deux côtés, seulement sur un partage accepté « lecture et remarques »."""
    share = _lock(share)
    if not share.is_open:
        raise ApiError("SHARE_CLOSED", "Ce partage n'est plus actif.", 409)
    if share.level != CaseShare.Level.COMMENT:
        raise ApiError("SHARE_READ_ONLY", "Ce partage est en lecture seule.", 403)
    text = (text or "").strip()[:2000]
    if not text:
        raise ApiError("VALIDATION_ERROR", "La remarque est vide.", 400, {"field": "text"})
    note = CaseShareNote.objects.create(share=share, author=actor, author_organization=organization, text=text)
    _both(share, actor, "case_share.note_added", {"by": organization.name})
    return note


def record_view(*, share: CaseShare, actor) -> None:
    """COL-06 : chaque consultation par le partenaire est notée chez le propriétaire et chez lui."""
    _both(share, actor, "case_share.viewed")


def share_payload(share: CaseShare, viewer) -> dict:
    owner_side = viewer.pk == share.organization_id
    other = share.partner if owner_side else share.organization
    return {
        "id": str(share.pk),
        "case_reference": share.case.reference,
        "case_title": share.case.title,
        "direction": "outgoing" if owner_side else "incoming",
        "organization": {"name": other.name, "profiles": organization_profiles(other)},
        "level": share.level,
        "status": share.status,
        "message": share.message,
        "created_at": share.created_at,
        "created_by": share.created_by.full_name or share.created_by.email,
        "decided_at": share.decided_at,
        "revoked_at": share.revoked_at,
        "row_version": share.row_version,
        # L'identifiant du dossier ne sert qu'au propriétaire (ses propres écrans).
        "case_id": str(share.case_id) if owner_side else None,
    }


def _dec(value):
    return None if value is None else str(value)


def snapshot(share: CaseShare) -> dict:
    """Ce que voit le partenaire : état, pièces (sans contenu), factures, marchandises, codes retenus."""
    from apps.cases import services as case_services

    case = share.case
    revision = case.current_revision
    documents = revision.documents.select_related("document").order_by("created_at")
    goods = []
    for line in revision.goods_lines.all():
        decision = case_services.current_decision(line)
        goods.append(
            {
                "ordinal": line.ordinal,
                "description": line.description,
                "origin_country": line.origin_country,
                "code": decision.selected_code if decision else None,
            }
        )
    return {
        "reference": case.reference,
        "title": case.title,
        "owner": share.organization.name,
        "importer": case.importer.name if case.importer else None,
        "state": revision.state,
        "state_label": revision.get_state_display(),
        "revision_no": revision.revision_no,
        "regime": revision.regime,
        "transport_mode": revision.transport_mode,
        "entry_office": revision.entry_office,
        "customs_declaration_number": revision.customs_declaration_number,
        "lodged_on": revision.lodged_on,
        "documents": [
            {
                "usage": d.usage,
                "usage_label": d.get_usage_display(),
                "name": d.document.original_name,
                "added_at": d.created_at,
            }  # fmt: skip
            for d in documents
        ],
        "invoices": [
            {
                "number": i.invoice_number,
                "supplier": i.supplier_name,
                "date": i.invoice_date,
                "currency": i.currency,
                "incoterm": i.incoterm,
                "total": _dec(i.declared_total),
            }  # fmt: skip
            for i in revision.invoices.all().order_by("ordinal")
        ],
        "goods": goods,
    }


def notes_payload(share: CaseShare, viewer) -> list[dict]:
    return [
        {
            "id": str(n.pk),
            "text": n.text,
            "author": n.author.full_name or n.author.email,
            "organization": n.author_organization.name,
            "own": n.author_organization_id == viewer.pk,
            "created_at": n.created_at,
        }
        for n in share.notes.select_related("author", "author_organization")
    ]
