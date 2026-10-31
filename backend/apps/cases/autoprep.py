"""Préparation automatique du dossier après la lecture d'une facture.

But : l'agent n'a plus à remplir le formulaire à la main. Après chaque lecture réussie, et
seulement pour ce qui est encore vide :
- l'édition du référentiel : la plus récente publiée et visible (opérationnelle d'abord) ;
- la date de déclaration prévue : aujourd'hui ;
- le régime : celui du dernier dossier de la société ;
- l'origine du dossier : seulement si la facture l'imprime (« Country of origin », « Made in ») ;
- une marchandise par ligne facturée libre, puis le contrôle de son code.

Rien n'est inventé : sans preuve dans la pièce, l'origine reste vide. La date, le régime et
l'édition sont des propositions marquées « à confirmer » (CaseRevision.prefilled) jusqu'à ce
qu'un agent les enregistre. Tout est journalisé.
"""

import logging
import re

from django.db import transaction
from django.utils import timezone

from apps.extraction.numbers import parse_country
from apps.tariffs import services as tariffs
from apps.tariffs.models import PublicationState

from . import services
from .models import CaseRevision

logger = logging.getLogger(__name__)

MADE_IN = re.compile(r"\bmade\s+in\s+([A-Za-z][A-Za-z .\-]{1,30}?)(?=[\n,;.)]|\s{2,}|$)", re.IGNORECASE | re.MULTILINE)


def default_edition(actor):
    editions = tariffs.visible_editions(actor).exclude(publication_state=PublicationState.WITHDRAWN)
    editions = editions.filter(published_at__isnull=False)
    return (
        editions.filter(publication_state=PublicationState.OPERATIONAL).order_by("-published_at").first()
        or editions.order_by("-published_at").first()
    )


def last_regime(revision: CaseRevision) -> str:
    previous = (
        CaseRevision.objects.for_organization(revision.organization)
        .exclude(case_id=revision.case_id)
        .exclude(regime="")
        .order_by("-created_at")
        .first()
    )
    return previous.regime if previous else ""


def printed_origin(run) -> tuple[str, str]:
    """(code pays, preuve) lus sur la facture ; ("", "") si la pièce ne dit rien ou se contredit."""
    from apps.extraction.models import FieldObservation

    obs = FieldObservation.objects.filter(run=run, entity_key="document", field_name="country_of_origin").first()
    if obs is not None and obs.raw_value:
        code = parse_country(obs.raw_value).value
        if code:
            return code, f"« {obs.raw_value} » lu à côté du libellé pays d'origine"
    found = {}
    for match in MADE_IN.finditer(run.read_text or ""):
        code = parse_country(match.group(1).strip()).value
        if code:
            found.setdefault(code, match.group(0).strip())
    if len(found) == 1:
        [(code, text)] = found.items()
        return code, f"« {text} » imprimé sur la facture"
    return "", ""


def after_invoice_read(run, invoice) -> dict:
    """Appelée dans la transaction de la lecture ; un échec ici n'annule pas la lecture."""
    try:
        with transaction.atomic():
            return _prepare(run, invoice)
    except Exception:
        logger.exception("Préparation automatique après la lecture %s : échec, dossier laissé tel quel", run.id)
        return {}


def _prepare(run, invoice) -> dict:
    org, actor = run.organization, run.created_by
    revision = CaseRevision.objects.select_for_update(of=("self",)).select_related("case").get(pk=invoice.revision_id)
    if not revision.is_editable:
        return {}
    filled, proposed = {}, list(revision.prefilled)
    if not revision.target_edition_id:
        edition = default_edition(actor)
        if edition is not None:
            revision.target_edition = edition
            filled["target_edition"] = edition.label
            proposed.append("target_edition")
    if not revision.planned_declaration_date:
        revision.planned_declaration_date = timezone.localdate()
        filled["planned_declaration_date"] = revision.planned_declaration_date.isoformat()
        proposed.append("planned_declaration_date")
    if not revision.regime:
        regime = last_regime(revision)
        if regime:
            revision.regime = regime
            filled["regime"] = regime
            proposed.append("regime")
    evidence = ""
    if not revision.origin_country:
        code, evidence = printed_origin(run)
        if code:
            revision.origin_country = code
            filled["origin_country"] = code
    if filled:
        revision.prefilled = sorted(set(proposed))
        revision.row_version += 1
        revision.save()

    goods = services.goods_lines_from_invoice(org=org, actor=actor, invoice_id=invoice.id)
    checked = 0
    if revision.target_edition_id:
        for line in goods:
            services.run_code_check(org=org, actor=actor, goods_id=line.id)
            checked += 1
    report = {"filled": filled, "goods_created": len(goods), "codes_checked": checked}
    if evidence:
        report["origin_evidence"] = evidence
    if filled or goods:
        services._event(org, actor, "revision.prepared_automatically", revision, revision.case, None, report)
    return report


def classify_after_reading(run) -> int:
    """Hors transaction, après la lecture : l'IA départage les codes incomplets ou absents.

    Seulement si la société a activé l'IA en ligne en mode automatique ; chaque échec est journalisé
    et laisse la marchandise telle quelle, avec ses propositions."""
    from . import ai_choice
    from .models import GoodsLine

    if run.invoice_id is None or not ai_choice.available(run.organization, auto=True):
        return 0
    goods = GoodsLine.objects.filter(sources__invoice_line__invoice_id=run.invoice_id).distinct()
    asked = 0
    for line in goods.order_by("ordinal"):
        check = services.latest_check(line)
        if check is None or check.state not in ai_choice.NEEDS_CODE or services.current_decision(line):
            continue
        try:
            if ai_choice.choose(org=run.organization, actor=run.created_by, goods_id=line.id, trigger="auto"):
                asked += 1
        except Exception:
            logger.exception("Choix de code par l'IA pour la marchandise %s : échec", line.id)
    return asked
