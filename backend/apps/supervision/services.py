"""Tableau de supervision de la console ClairTransit (SUP-01 à SUP-06).

Ce que l'exploitant voit : l'état réel de l'antivirus et son activité, l'activité de lecture des
pièces (moteurs, types, échecs), l'activité de l'IA en ligne (fournisseur, informations demandées
et retenues, coûts), les pièces refusées et pourquoi, les actions refusées et les erreurs, par
société. Jamais : le contenu d'une pièce, son nom de fichier, une valeur lue, le texte envoyé à l'IA
ou une clé. Les compteurs portent sur la période choisie.
"""

import time
from collections import Counter
from datetime import timedelta

from django.db.models import Avg, Count, F, Max, Sum
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.cases.models import CustomsCase
from apps.core.models import BackgroundJob
from apps.documents import antivirus
from apps.extraction import ai
from apps.extraction.models import AICompletion, ExtractionRun, OrganizationAISettings
from apps.organizations.models import Organization

from . import recorder
from .models import OperationalEvent

PERIODS = (1, 7, 30)
RECENT = 30
SCAN_UNAVAILABLE_CODES = ("MALWARE_SCAN_UNAVAILABLE", "SCAN_UNAVAILABLE")
READER_LABELS = {
    "invoice": "Facture commerciale",
    "transport": "Titre de transport",
    "insurance": "Assurance",
    "freight": "Facture de fret",
    "packing": "Liste de colisage",
    "origin": "Certificat d'origine",
}
PARSER_LABELS = {
    "pdf_text": "Texte du PDF",
    "pdf_text+ocr": "Texte du PDF + OCR (Tesseract)",
    "ocr": "OCR d'image (Tesseract)",
    "xlsx": "Classeur Excel",
}


def _names() -> dict:
    return dict(Organization.objects.values_list("id", "name"))


def _event_payload(e: OperationalEvent, names: dict) -> dict:
    return {
        "id": str(e.id),
        "at": e.at,
        "category": e.category,
        "level": e.level,
        "code": e.code,
        "message": e.message,
        "organization": names.get(e.organization_id),
        "actor": (e.actor.full_name or e.actor.email) if e.actor_id else None,
        "request_id": e.request_id,
        "details": e.details,
    }


# --- Antivirus ----------------------------------------------------------------------------


def probe_antivirus() -> dict:
    """Demande sa version à clamd : répond-il, depuis quand ses signatures datent-elles ?"""
    started = time.monotonic()
    try:
        text = antivirus.version()
    except antivirus.ScanUnavailable as exc:
        return {"state": "unavailable", "message": str(exc), "checked_at": timezone.now()}
    engine, _, rest = text.partition("/")
    signatures, _, signatures_date = rest.partition("/")
    return {
        "state": "ok",
        "engine": engine.strip(),
        "signatures": signatures.strip(),
        "signatures_date": signatures_date.strip(),
        "response_ms": round((time.monotonic() - started) * 1000),
        "checked_at": timezone.now(),
    }


def self_test(actor) -> dict:
    """Essai EICAR (refus attendu) puis contenu sain (accepté attendu), par le chemin des dépôts."""
    from apps.documents.management.commands.verifier_antivirus import _SAIN, _verdict, eicar

    steps, ok = [], True
    try:
        try:
            _verdict(eicar())
        except antivirus.MalwareDetected:
            steps.append({"step": "eicar", "ok": True, "message": "Fichier d'essai EICAR détecté et refusé."})
        else:
            ok = False
            steps.append({"step": "eicar", "ok": False, "message": "EICAR n'a PAS été détecté : signatures absentes ?"})
        try:
            _verdict(_SAIN)
            steps.append({"step": "clean", "ok": True, "message": "Contenu sain accepté."})
        except antivirus.MalwareDetected:
            ok = False
            steps.append({"step": "clean", "ok": False, "message": "Contenu sain refusé : résultat incohérent."})
    except antivirus.ScanUnavailable as exc:
        ok = False
        steps.append({"step": "connect", "ok": False, "message": str(exc)})
    recorder.note(
        category="antivirus",
        level="info" if ok else "error",
        code="SELF_TEST_PASSED" if ok else "SELF_TEST_FAILED",
        message="Essai de l'antivirus réussi." if ok else "Essai de l'antivirus en échec.",
        actor=actor,
        details={"steps": steps},
    )
    return {"ok": ok, "steps": steps, "at": timezone.now()}


def antivirus_section(since, names) -> dict:
    events = OperationalEvent.objects.filter(category=OperationalEvent.Category.ANTIVIRUS)
    in_period = events.filter(at__gte=since)
    last_test = events.filter(code__in=("SELF_TEST_PASSED", "SELF_TEST_FAILED")).select_related("actor").first()
    return {
        "probe": probe_antivirus(),
        "mode": "fail_closed",
        "counts": {
            "clean": AuditEvent.objects.filter(event_type="document.stored", at__gte=since).count(),
            "malware": in_period.filter(code="MALWARE_DETECTED").count(),
            "unavailable": in_period.filter(code__in=SCAN_UNAVAILABLE_CODES).count(),
        },
        "last_clean_at": AuditEvent.objects.filter(event_type="document.stored").aggregate(m=Max("at"))["m"],
        "last_test": _event_payload(last_test, names) if last_test else None,
        "events": [_event_payload(e, names) for e in events.select_related("actor")[:RECENT]],
    }


# --- Lecture des pièces ------------------------------------------------------------------


def ocr_engine() -> dict:
    try:
        import pytesseract

        version = str(pytesseract.get_tesseract_version())
        languages = sorted(lang for lang in pytesseract.get_languages(config="") if lang != "osd")
    except Exception:  # absent, mal installé ou introuvable : l'OCR est indisponible
        return {"available": False, "version": "", "languages": []}
    return {"available": True, "version": version, "languages": languages}


def reading_section(since, names) -> dict:
    runs = ExtractionRun.objects.filter(created_at__gte=since)
    statuses = Counter(dict(runs.values_list("status").annotate(n=Count("id"))))
    by_reader: Counter = Counter()
    by_reader_failed: Counter = Counter()
    for options, status in runs.values_list("options", "status"):
        reader = (options or {}).get("reader", "invoice")
        by_reader[reader] += 1
        if status == ExtractionRun.Status.FAILED:
            by_reader_failed[reader] += 1
    by_parser = dict(runs.values_list("parser").annotate(n=Count("id")))
    duration = runs.filter(finished_at__isnull=False).aggregate(d=Avg(F("finished_at") - F("created_at")))["d"]
    failures = (
        ExtractionRun.objects.filter(status=ExtractionRun.Status.FAILED)
        .select_related("case_document__revision__case")
        .order_by("-created_at")[:RECENT]
    )
    return {
        "engines": {
            "pdf_text": True,
            "xlsx": True,
            "ocr": ocr_engine(),
            "ai": ai.provider_info(),
        },
        "counts": {
            "total": sum(statuses.values()),
            "succeeded": statuses.get(ExtractionRun.Status.SUCCEEDED, 0),
            "failed": statuses.get(ExtractionRun.Status.FAILED, 0),
            "running": statuses.get(ExtractionRun.Status.RUNNING, 0) + statuses.get(ExtractionRun.Status.QUEUED, 0),
            "average_seconds": round(duration.total_seconds(), 1) if duration else None,
        },
        "by_reader": [
            {
                "reader": r,
                "label": READER_LABELS.get(r, r),
                "count": n,
                "failed": by_reader_failed.get(r, 0),
            }
            for r, n in by_reader.most_common()
        ],
        "by_parser": [
            {"parser": p, "label": PARSER_LABELS.get(p, p), "count": n}
            for p, n in sorted(by_parser.items(), key=lambda kv: -kv[1])
        ],
        "failures": [
            {
                "id": str(r.id),
                "at": r.created_at,
                "organization": names.get(r.organization_id),
                "case_reference": r.case_document.revision.case.reference,
                "reader": READER_LABELS.get(r.options.get("reader", "invoice"), r.options.get("reader")),
                "parser": PARSER_LABELS.get(r.parser, r.parser),
                "attempt": r.attempt,
                "error_code": r.error_code,
                "error_message": r.error_message,
            }
            for r in failures
        ],
    }


# --- IA en ligne ---------------------------------------------------------------------------


def ai_section(since, names) -> dict:
    items = AICompletion.objects.filter(created_at__gte=since)
    statuses = dict(items.values_list("status").annotate(n=Count("id")))
    sent = items.filter(status=AICompletion.Status.SENT)
    totals = sent.aggregate(
        input_tokens=Sum("input_tokens"),
        output_tokens=Sum("output_tokens"),
        cost=Sum("cost_estimate"),
        latency=Avg("latency_ms"),
        chars=Sum("sent_chars"),
    )
    requested, found, rejected = Counter(), Counter(), Counter()
    for req, fnd, rej in items.values_list("requested", "found", "rejected"):
        requested.update(req or [])
        found.update(fnd or [])
        rejected.update((r or {}).get("field", "") for r in rej or [])
    recent = items.select_related("created_by").order_by("-created_at")[:RECENT]
    return {
        "provider": ai.provider_info(),
        "organizations_enabled": OrganizationAISettings.objects.filter(enabled=True).count(),
        "counts": {s: statuses.get(s, 0) for s in AICompletion.Status.values},
        "status_labels": dict(AICompletion.Status.choices),
        "totals": {
            "input_tokens": totals["input_tokens"],
            "output_tokens": totals["output_tokens"],
            "cost_estimate": format(totals["cost"], "f") if totals["cost"] is not None else None,
            "average_latency_ms": round(totals["latency"]) if totals["latency"] is not None else None,
            "sent_chars": totals["chars"],
        },
        "fields": [
            {"field": f, "requested": n, "found": found.get(f, 0), "rejected": rejected.get(f, 0)}
            for f, n in requested.most_common(15)
        ],
        "recent": [
            {
                "id": str(r.id),
                "at": r.created_at,
                "organization": names.get(r.organization_id),
                "status": r.status,
                "status_label": r.get_status_display(),
                "trigger": r.get_trigger_display(),
                "provider": r.provider,
                "model": r.model,
                "free_tier": r.free_tier,
                "requested": r.requested,
                "found": r.found,
                "rejected": r.rejected,
                "sent_chars": r.sent_chars,
                "latency_ms": r.latency_ms,
                "error_code": r.error_code,
                "error_message": r.error_message,
            }
            for r in recent
        ],
    }


# --- Pièces refusées, actions refusées, erreurs --------------------------------------------


def rejections_section(since, names) -> list[dict]:
    items = (
        OperationalEvent.objects.filter(at__gte=since, category=OperationalEvent.Category.DOCUMENT)
        | OperationalEvent.objects.filter(
            at__gte=since,
            category=OperationalEvent.Category.ANTIVIRUS,
            code__in=("MALWARE_DETECTED", *SCAN_UNAVAILABLE_CODES),
        )
    ).select_related("actor")
    return [_event_payload(e, names) for e in items.order_by("-at")[:RECENT]]


def incidents_section(since, names) -> dict:
    events = (
        OperationalEvent.objects.filter(
            at__gte=since, category__in=(OperationalEvent.Category.REQUEST, OperationalEvent.Category.SERVER)
        )
        .select_related("actor")
        .order_by("-at")
    )
    jobs = BackgroundJob.objects.filter(state=BackgroundJob.State.FAILED, created_at__gte=since).exclude(
        kind="extraction"  # déjà dans les échecs de lecture
    )
    return {
        "server_errors": events.filter(category=OperationalEvent.Category.SERVER).count(),
        "refused_actions": events.filter(category=OperationalEvent.Category.REQUEST).count(),
        "events": [_event_payload(e, names) for e in events[:RECENT]],
        "failed_jobs": [
            {
                "id": str(j.id),
                "at": j.created_at,
                "organization": names.get(j.organization_id),
                "kind": j.kind,
                "phase": j.phase,
                "attempts": j.attempts,
                "error_code": j.error_code,
                "error_message": j.error_message,
            }
            for j in jobs.order_by("-created_at")[:RECENT]
        ],
    }


# --- Par société ---------------------------------------------------------------------------


def organizations_section(since) -> list[dict]:
    def per_org(qs, field="organization_id"):
        return dict(qs.values_list(field).annotate(n=Count("id")))

    cases = per_org(CustomsCase.objects.filter(created_at__gte=since))
    stored = per_org(AuditEvent.objects.filter(event_type="document.stored", at__gte=since))
    runs = ExtractionRun.objects.filter(created_at__gte=since)
    read_ok = per_org(runs.filter(status=ExtractionRun.Status.SUCCEEDED))
    read_failed = per_org(runs.filter(status=ExtractionRun.Status.FAILED))
    refused = per_org(
        OperationalEvent.objects.filter(
            at__gte=since, category__in=(OperationalEvent.Category.DOCUMENT, OperationalEvent.Category.ANTIVIRUS)
        )
    )
    errors = per_org(
        OperationalEvent.objects.filter(
            at__gte=since, category__in=(OperationalEvent.Category.REQUEST, OperationalEvent.Category.SERVER)
        )
    )
    ai_sent = per_org(AICompletion.objects.filter(created_at__gte=since, status=AICompletion.Status.SENT))
    last = dict(AuditEvent.objects.values_list("organization_id").annotate(m=Max("at")))
    out = []
    for org in Organization.objects.order_by("name", "id"):
        out.append(
            {
                "id": str(org.id),
                "name": org.name,
                "is_demo": org.is_demo,
                "cases": cases.get(org.id, 0),
                "documents": stored.get(org.id, 0),
                "readings": read_ok.get(org.id, 0),
                "reading_failures": read_failed.get(org.id, 0),
                "rejected_documents": refused.get(org.id, 0),
                "errors": errors.get(org.id, 0),
                "ai_sent": ai_sent.get(org.id, 0),
                "last_activity": last.get(org.id),
            }
        )
    return out


def dashboard(days: int) -> dict:
    since = timezone.now() - timedelta(days=days)
    names = _names()
    return {
        "period_days": days,
        "since": since,
        "generated_at": timezone.now(),
        "antivirus": antivirus_section(since, names),
        "reading": reading_section(since, names),
        "ai": ai_section(since, names),
        "rejections": rejections_section(since, names),
        "incidents": incidents_section(since, names),
        "organizations": organizations_section(since),
    }
