"""Complément d'une pièce par l'IA en ligne (IAL-01 à IAL-10) : seules les informations non trouvées.

Ordre des contrôles, avant tout envoi :
1. un fournisseur est configuré sur le serveur et la société a activé l'IA en ligne ;
2. le client du dossier ne refuse pas la lecture par IA (prioritaire sur le réglage de la société) ;
3. le plafond mensuel de la société n'est pas atteint.
Seul le texte déjà lu de la pièce part, avec la liste des informations manquantes ; jamais le fichier.

Chaque réponse est contrôlée ici, quel que soit le fournisseur : l'extrait cité doit se retrouver
dans la pièce et contenir la valeur, sinon la proposition est écartée. Une proposition reste une
observation « Proposé par l'IA » à vérifier : elle ne remplit aucun champ du dossier sans un agent.
Chaque demande, envoyée ou non, est journalisée (AICompletion) ; les valeurs n'entrent pas dans l'audit.
"""

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.services import record_event
from apps.cases.models import CaseDocument, CaseRevision
from apps.core.exceptions import ApiError

from . import ai, readers
from .models import AICompletion, ExtractionRun, FieldCorrection, FieldObservation, OrganizationAISettings, SourceSpan
from .numbers import norm, parse_amount, parse_currency, parse_date
from .schema import Status, jsonable

logger = logging.getLogger(__name__)

# Facture commerciale : informations d'en-tête qu'on peut demander (le détail des marchandises, jamais).
INVOICE_SPECS = (
    readers.FieldSpec("supplier_name", "Fournisseur (émetteur de la facture)"),
    readers.FieldSpec("buyer_name", "Acheteur ou destinataire de la facture"),
    readers.FieldSpec("invoice_number", "N° de facture"),
    readers.FieldSpec("invoice_date", "Date de facture", "date"),
    readers.FieldSpec("currency", "Devise", "currency"),
    readers.FieldSpec("incoterm", "Incoterm et lieu"),
    readers.FieldSpec("declared_total", "Montant total de la facture", "amount"),
)
PIECES = {
    readers.INVOICE: "facture commerciale",
    readers.TRANSPORT: "titre de transport (connaissement, lettre de transport aérien ou lettre de voiture)",
    readers.INSURANCE: "pièce d'assurance (facture, attestation ou police)",
    readers.FREIGHT: "facture de fret",
}
MAX_EXCERPT = 300
PAGE_MARK = re.compile(r"^\[page (\d+)\]$")


def specs_for(reader: str) -> tuple[readers.FieldSpec, ...]:
    return INVOICE_SPECS if reader == readers.INVOICE else readers.SPECS.get(reader, ())


def entity_for(reader: str) -> str:
    return "invoice" if reader == readers.INVOICE else "document"


def settings_for(org) -> OrganizationAISettings:
    found = OrganizationAISettings.objects.for_organization(org).first()
    return found or OrganizationAISettings(organization=org)


def month_start(now: datetime | None = None) -> datetime:
    now = timezone.localtime(now or timezone.now())
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def sent_this_month(org) -> int:
    return (
        AICompletion.objects.for_organization(org)
        .filter(status=AICompletion.Status.SENT, created_at__gte=month_start())
        .count()
    )


def client_refuses(link: CaseDocument) -> bool:
    """Le refus s'applique dès que le client est rattaché au dossier."""
    importer = link.revision.case.importer
    return bool(importer and importer.ai_refused)


# --- Ce qui manque -----------------------------------------------------------------------------


def _missing(run: ExtractionRun, statuses: dict[str, str], already: set[str]) -> list[ai.FieldRequest]:
    reader = run.options.get("reader", readers.INVOICE)
    invoice = run.invoice if reader == readers.INVOICE else None
    wanted = []
    for spec in specs_for(reader):
        if statuses.get(spec.name) != Status.MISSING or spec.name in already:
            continue
        if invoice is not None and getattr(invoice, spec.name) not in (None, ""):
            continue  # déjà saisi par un agent : on ne demande rien
        wanted.append(ai.FieldRequest(spec.name, spec.label, spec.kind))
    return wanted


def missing_fields(run: ExtractionRun) -> list[ai.FieldRequest]:
    """Informations « non trouvées » par la lecture, pas encore proposées ni saisies."""
    if run.status != ExtractionRun.Status.SUCCEEDED:
        return []
    reader = run.options.get("reader", readers.INVOICE)
    entity = entity_for(reader)
    statuses, already = {}, set()
    for obs in run.observations.filter(entity_key=entity):
        if obs.origin_type == FieldObservation.Origin.AI:
            already.add(obs.field_name)
        else:
            statuses[obs.field_name] = obs.status
    already |= set(
        FieldCorrection.objects.filter(observation__run=run, observation__entity_key=entity).values_list(
            "field_name", flat=True
        )
    )
    # Déjà demandées à l'IA sur cette lecture : elle a répondu « non trouvé » ou sa proposition a été
    # écartée. On ne redemande pas : l'agent saisit la valeur.
    for asked in run.ai_completions.filter(status=AICompletion.Status.SENT).values_list("requested", flat=True):
        already |= set(asked or [])
    return _missing(run, statuses, already)


# --- Demande au fournisseur --------------------------------------------------------------------


@dataclass
class Outcome:
    status: str
    requested: list[ai.FieldRequest]
    accepted: list[dict] = field(default_factory=list)
    rejected: list[dict] = field(default_factory=list)
    completion: ai.Completion | None = None
    sent_chars: int = 0
    latency_ms: int | None = None
    error_code: str = ""
    error_message: str = ""


def gate(org, link: CaseDocument) -> str | None:
    """Statut de refus si la demande ne doit pas partir, sinon None."""
    if client_refuses(link):
        return AICompletion.Status.CLIENT_REFUSED
    cap = settings_for(org).monthly_cap
    if sent_this_month(org) >= cap:
        return AICompletion.Status.CAP_REACHED
    return None


def ask(run: ExtractionRun, link: CaseDocument, fields: list[ai.FieldRequest], text: str) -> Outcome:
    """Contrôles, envoi et vérification ; n'écrit rien en base (appelé hors transaction)."""
    if refused := gate(run.organization, link):
        return Outcome(refused, fields)
    reader = run.options.get("reader", readers.INVOICE)
    sent = text[: settings.AI_MAX_TEXT_CHARS]
    start = time.monotonic()
    try:
        provider = ai.get_provider()
        completion = provider.complete_fields(text=sent, piece=PIECES.get(reader, "pièce"), fields=fields)
    except ai.AIUnavailable as exc:
        return Outcome(
            AICompletion.Status.FAILED,
            fields,
            sent_chars=len(sent),
            latency_ms=int((time.monotonic() - start) * 1000),
            error_code=getattr(exc, "code", "AI_DISABLED"),
            error_message=getattr(exc, "message", str(exc))[:300],
        )
    accepted, rejected = validate(completion.items, fields, text)
    return Outcome(
        AICompletion.Status.SENT,
        fields,
        accepted,
        rejected,
        completion,
        sent_chars=len(sent),
        latency_ms=int((time.monotonic() - start) * 1000),
    )


def _page_of(text: str, excerpt: str) -> int | None:
    page, target = None, norm(excerpt)
    for line in text.splitlines():
        if m := PAGE_MARK.match(line.strip()):
            page = int(m.group(1))
        elif target and norm(line) and (target in norm(line) or norm(line) in target):
            return page
    return page


def _parse(kind: str, value: str):
    if kind == "amount":
        return parse_amount(value)
    if kind == "date":
        return parse_date(value)
    if kind == "currency":
        return parse_currency(value)
    return None


def validate(items: list, fields: list[ai.FieldRequest], text: str) -> tuple[list[dict], list[dict]]:
    """Contrôle de sortie : rien n'est réparé. Une proposition sans preuve retrouvable est écartée."""
    asked = {f.name: f for f in fields}
    haystack = norm(text)
    accepted, rejected, seen = [], [], set()
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or str(item.get("field")) not in asked:
            rejected.append({"field": str(item.get("field", ""))[:40] if isinstance(item, dict) else "",
                             "reason": "Information non demandée : ignorée."})  # fmt: skip
            continue
        name = str(item["field"])
        if name in seen:
            rejected.append({"field": name, "reason": "Réponse en double : ignorée."})
            continue
        seen.add(name)
        if item.get("found") is not True:
            continue  # « non trouvé » : réponse acceptable, rien à proposer
        value, excerpt = str(item.get("value") or "").strip(), str(item.get("excerpt") or "").strip()
        if not value or not excerpt or len(excerpt) > MAX_EXCERPT:
            rejected.append({"field": name, "reason": "Valeur ou extrait manquant : proposition écartée."})
            continue
        if norm(excerpt) not in haystack:
            rejected.append({"field": name, "reason": "Extrait introuvable dans la pièce : proposition écartée."})
            continue
        if norm(value) not in norm(excerpt):
            rejected.append({"field": name, "reason": "Valeur absente de l'extrait cité : proposition écartée."})
            continue
        spec = asked[name]
        reading = _parse(spec.kind, value)
        if reading is not None and reading.status not in (Status.OK, Status.AMBIGUOUS):
            rejected.append({"field": name, "reason": f"Valeur illisible pour ce champ : {reading.note or value}"})
            continue
        accepted.append({
            "field": name,
            "label": spec.label,
            "raw": value[:500],
            "parsed": reading.value if reading is not None else value[:500],
            "status": reading.status if reading is not None else Status.OK,
            "note": reading.note if reading is not None else "",
            "excerpt": excerpt,
            "page": _page_of(text, excerpt),
        })  # fmt: skip
    return accepted, rejected


# --- Enregistrement ----------------------------------------------------------------------------


def save(run: ExtractionRun, link: CaseDocument, outcome: Outcome, *, actor, trigger: str) -> AICompletion:
    """Dans la transaction de l'appelant : propositions, journal et audit (sans les valeurs)."""
    org, reader = run.organization, run.options.get("reader", readers.INVOICE)
    info = ai.provider_info()
    model = outcome.completion.model if outcome.completion else (info["model"] or "")
    for item in outcome.accepted:
        span = SourceSpan.objects.create(
            organization=org, document=run.document, page_index=item["page"], excerpt=item["excerpt"][:200]
        )
        excerpt = item["excerpt"][:200]
        notes = [f"Proposé par l'IA ({info['label']}, {model}) d'après l'extrait « {excerpt} ». À vérifier."]
        if item["note"]:
            notes.append(item["note"])
        FieldObservation.objects.create(
            organization=org,
            run=run,
            entity_key=entity_for(reader),
            field_name=item["field"],
            label=item["label"][:120],
            raw_value=item["raw"],
            parsed_value=jsonable(item["parsed"]),
            status=item["status"],
            origin_type=FieldObservation.Origin.AI,
            notes=notes,
            source_span=span,
            invoice=run.invoice if reader == readers.INVOICE else None,
        )
    completion = outcome.completion
    usage_in = completion.input_tokens if completion else None
    usage_out = completion.output_tokens if completion else None
    sent = outcome.status in (AICompletion.Status.SENT, AICompletion.Status.FAILED) and outcome.sent_chars > 0
    record = AICompletion.objects.create(
        organization=org,
        run=run,
        case_document=link,
        status=outcome.status,
        trigger=trigger,
        provider=(info["name"] or "") if sent else "",
        model=model if sent else "",
        free_tier=info["free_tier"] if sent else False,
        requested=[f.name for f in outcome.requested],
        found=[item["field"] for item in outcome.accepted],
        rejected=outcome.rejected,
        sent_chars=outcome.sent_chars,
        input_tokens=usage_in,
        output_tokens=usage_out,
        cost_estimate=ai.estimate_cost(usage_in, usage_out) if outcome.status == AICompletion.Status.SENT else None,
        latency_ms=outcome.latency_ms,
        error_code=outcome.error_code,
        error_message=outcome.error_message,
        created_by=actor,
    )
    record_event(
        organization=org,
        actor=actor,
        event_type="document.ai_completion",
        entity=record,
        current={
            "run": str(run.id),
            "status": outcome.status,
            "trigger": trigger,
            "provider": record.provider,
            "model": record.model,
            "requested": record.requested,
            "found": record.found,
            "rejected": len(record.rejected),
        },
        scope=link.revision.case.scope,
    )
    return record


# --- Points d'entrée ---------------------------------------------------------------------------


def auto_outcome(run: ExtractionRun, parsed, *, progress=None) -> Outcome | None:
    """Après une lecture, mode automatique : None quand l'IA ne doit pas intervenir. Ne lève jamais."""
    try:
        org = run.organization
        if not ai.is_enabled():
            return None
        config = settings_for(org)
        if not config.enabled or config.mode != OrganizationAISettings.Mode.AUTO:
            return None
        statuses = {name: value.status for name, value in parsed.header.items()}
        fields = _missing(run, statuses, set())
        if not fields or not parsed.text.strip():
            return None
        if progress is not None:
            progress("complément par l'IA", 0, 1)
        return ask(run, run.case_document, fields, parsed.text)
    except Exception:  # l'IA ne fait jamais échouer une lecture
        logger.exception("Complément IA automatique impossible pour %s", run.id)
        return None


def complete_on_demand(*, org, actor, link_id) -> AICompletion:
    link = (
        CaseDocument.objects.for_organization(org).select_related("revision__case__importer").filter(pk=link_id).first()
    )
    if link is None:
        raise ApiError("NOT_FOUND", "Pièce introuvable.", 404)
    if not ai.is_enabled():
        raise ApiError("AI_NOT_CONFIGURED", "L'IA en ligne n'est pas configurée sur ce serveur.", 409)
    if not settings_for(org).enabled:
        raise ApiError("AI_DISABLED", "L'IA en ligne n'est pas activée pour cette société.", 409)
    run = (
        ExtractionRun.objects.for_organization(org)
        .filter(case_document=link, status=ExtractionRun.Status.SUCCEEDED)
        .select_related("invoice", "document")
        .order_by("-attempt")
        .first()
    )
    if run is None:
        raise ApiError("NOT_READ", "Lire la pièce avant de demander un complément.", 409)
    fields = missing_fields(run)
    if not fields:
        raise ApiError("NOTHING_MISSING", "Aucune information manquante à demander.", 409)
    if not run.read_text.strip():
        raise ApiError("NO_TEXT", "Aucun texte lu sur cette pièce : rien à envoyer.", 409)
    outcome = ask(run, link, fields, run.read_text)
    with transaction.atomic():
        from .services import _require_editable

        _require_editable(CaseRevision.objects.select_for_update(of=("self",)).get(pk=link.revision_id))
        return save(run, link, outcome, actor=actor, trigger=AICompletion.Trigger.ON_DEMAND)


def summary(run: ExtractionRun) -> dict | None:
    record = run.ai_completions.order_by("-created_at").first()
    if record is None:
        return None
    return {
        "status": record.status,
        "status_label": record.get_status_display(),
        "trigger": record.trigger,
        "provider": record.provider or None,
        "provider_label": ai.PROVIDERS.get(record.provider, {}).get("label"),
        "model": record.model or None,
        "free_tier": record.free_tier,
        "requested": len(record.requested),
        "found": len(record.found),
        "rejected": len(record.rejected),
        "error_message": record.error_message or None,
        "created_at": record.created_at,
    }


# --- Décision de l'agent sur une information -------------------------------------------------


def _typed(field_name: str, parsed):
    from datetime import date
    from decimal import Decimal, InvalidOperation

    if parsed is None:
        return None
    if field_name == "declared_total":
        try:
            return Decimal(str(parsed))
        except InvalidOperation:
            return None
    if field_name == "invoice_date":
        try:
            return date.fromisoformat(str(parsed))
        except ValueError:
            return None
    return str(parsed)


def decide(*, org, actor, run_id, field_name: str, action: str, value: str = "", reason: str = "") -> dict:
    """« accept » retient la proposition de l'IA ; « set » enregistre la valeur saisie par l'agent
    (titre de transport, assurance, fret). Pour une facture, la proposition acceptée remplit la fiche
    facture comme une correction attribuée ; une autre valeur se corrige dans la fiche facture."""
    from apps.cases import services as case_services

    from .services import _require_editable

    run = (
        ExtractionRun.objects.for_organization(org)
        .select_related("case_document__revision__case", "invoice")
        .filter(pk=run_id)
        .first()
    )
    if run is None:
        raise ApiError("NOT_FOUND", "Lecture introuvable.", 404)
    reader = run.options.get("reader", readers.INVOICE)
    spec = next((s for s in specs_for(reader) if s.name == field_name), None)
    if spec is None:
        raise ApiError("UNKNOWN_FIELD", "Information inconnue pour ce type de pièce.", 400)
    if action not in ("accept", "set"):
        raise ApiError("VALIDATION_ERROR", "Action attendue : accept ou set.", 400)
    entity = entity_for(reader)
    with transaction.atomic():
        revision = CaseRevision.objects.select_for_update(of=("self",)).get(pk=run.case_document.revision_id)
        _require_editable(revision)
        observations = list(run.observations.filter(entity_key=entity, field_name=field_name).order_by("created_at"))
        proposal = next((o for o in reversed(observations) if o.origin_type == FieldObservation.Origin.AI), None)
        read = next((o for o in observations if o.origin_type != FieldObservation.Origin.AI), None)
        if action == "accept" and proposal is None:
            raise ApiError("NO_PROPOSAL", "Aucune proposition de l'IA pour cette information.", 409)
        if entity == "invoice":
            if action != "accept":
                raise ApiError("USE_INVOICE_FORM", "Corriger cette information dans la fiche facture.", 400)
            typed = _typed(field_name, proposal.parsed_value)
            if typed is None or proposal.status != Status.OK or run.invoice is None:
                raise ApiError(
                    "PROPOSAL_UNREADABLE", "Proposition à vérifier : saisir la valeur dans la fiche facture.", 409
                )
            case_services.update_invoice(
                org=org,
                actor=actor,
                invoice_id=run.invoice_id,
                expected=run.invoice.row_version,
                data={field_name: typed, "correction_reason": reason or "Proposition de l'IA acceptée."},
            )
            entered = {"raw": proposal.raw_value, "from_ai": True}
        else:
            text = proposal.raw_value if action == "accept" else (value or "").strip()
            if not text:
                raise ApiError("VALIDATION_ERROR", "Saisir une valeur.", 400)
            source = proposal or read
            FieldCorrection.objects.create(
                organization=org,
                field_name=field_name,
                previous={"raw": source.raw_value if source else None},
                current={"raw": text[:500], "from_ai": action == "accept"},
                observation=source,
                reason=(reason or ("Proposition de l'IA acceptée." if action == "accept" else ""))[:500],
                actor=actor,
            )
            entered = {"raw": text[:500], "from_ai": action == "accept"}
        record_event(
            organization=org,
            actor=actor,
            event_type="document.field_entered",
            entity=run,
            current={"field": field_name, "value": entered["raw"], "from_ai": entered["from_ai"]},
            scope=revision.case.scope,
        )
    return entered
