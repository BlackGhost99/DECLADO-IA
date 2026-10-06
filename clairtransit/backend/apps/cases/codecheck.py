"""Contrôle d'un code présent (COD-02 à COD-05), selon l'algorithme du §8 de la conception.

Déterministe et sans IA. `recognized` signifie « retrouvé dans l'édition cible », jamais
« classement validé » : seule une décision humaine attribuée confirme le code.
"""

import hashlib
import json

from apps.tariffs.models import ImportIssue, PublicationState, TariffEdition, TariffNode

from .models import CodeCheck, CodeObservation, GoodsLine

S = CodeCheck.State
BLOCKING_OPERATIONAL = "blocking_for_operational_calculation"
# Territoires couverts par une édition annoncée pour un périmètre plus large.
TERRITORY_SCOPES = {"GA": {"GA", "CEMAC"}}


def active_observations(goods_line: GoodsLine) -> list[CodeObservation]:
    return list(
        CodeObservation.objects.filter(
            organization=goods_line.organization,
            invoice_line__goods_sources__goods_line=goods_line,
            superseded_at__isnull=True,
        )
        .select_related("invoice_line__invoice", "evidence_document")
        .order_by("invoice_line__invoice__ordinal", "invoice_line__ordinal", "created_at")
    )


def code_inputs_hash(goods_line: GoodsLine, edition_id) -> str:
    """Empreinte des données dont dépend le contrôle : leur modification rend contrôle et décision périmés."""
    payload = {
        "edition": str(edition_id),
        "description": goods_line.description,
        "attributes": goods_line.attributes,
        "origin": goods_line.origin_country,
        "observations": [
            [str(o.id), o.raw_code, o.normalized_code, o.code_kind] for o in active_observations(goods_line)
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _finding(code: str, severity: str, message: str, **details) -> dict:
    return {"code": code, "severity": severity, "message": message, **({"details": details} if details else {})}


def _declarable_descendants(edition: TariffEdition, prefix: str, limit: int = 60) -> list[dict]:
    nodes = TariffNode.objects.filter(edition=edition, code__startswith=prefix, declarable=True).order_by("code")
    return [
        {"id": str(n.id), "code": n.code, "code_display": n.code_display, "label": n.label_clean} for n in nodes[:limit]
    ]


def applicability(edition: TariffEdition, revision) -> tuple[str, list[dict]]:
    findings = []
    if edition.publication_state != PublicationState.OPERATIONAL or not edition.applicability_verified:
        findings.append(
            _finding(
                "HISTORICAL_REFERENCE",
                BLOCKING_OPERATIONAL,
                "Édition publiée pour consultation historique : applicabilité actuelle non vérifiée.",
                edition_state=edition.publication_state,
            )
        )
    date = revision.planned_declaration_date
    if (
        date
        and edition.effective_from
        and (date < edition.effective_from or (edition.effective_to and date >= edition.effective_to))
    ):
        findings.append(
            _finding(
                "DATE_OUTSIDE_EDITION",
                BLOCKING_OPERATIONAL,
                "La date de déclaration prévue est hors de la période de validité de l'édition.",
            )
        )
    if edition.territory_scope not in TERRITORY_SCOPES.get(revision.territory, {revision.territory}):
        findings.append(
            _finding(
                "TERRITORY_MISMATCH",
                BLOCKING_OPERATIONAL,
                f"Édition « {edition.territory_scope} » ; dossier « {revision.territory} ».",
            )
        )
    return ("unverified" if findings else "verified"), findings


def evaluate(goods_line: GoodsLine, edition: TariffEdition, visible_editions) -> dict:
    """Retourne état, nœud, observation retenue et constats, sans rien enregistrer."""
    observations = active_observations(goods_line)
    customs = [o for o in observations if o.code_kind == CodeObservation.Kind.CUSTOMS]
    ambiguous = [o for o in observations if o.code_kind == CodeObservation.Kind.AMBIGUOUS]
    supplier = [o for o in observations if o.code_kind == CodeObservation.Kind.SUPPLIER]
    findings: list[dict] = []
    node = None
    observation = customs[0] if customs else (ambiguous[0] if ambiguous else None)

    references = {line.source_reference for line in goods_line_lines(goods_line) if line.source_reference}
    if supplier or references:
        findings.append(
            _finding(
                "SUPPLIER_REFERENCE_NOT_CUSTOMS",
                "info",
                "Référence fournisseur présente : elle n'est pas assimilée à un code douanier.",
                references=sorted(references | {o.raw_code for o in supplier}),
            )
        )

    if not customs and not ambiguous:
        state = S.MISSING
        findings.append(
            _finding("NO_CUSTOMS_CODE", "review", "Aucun code douanier observé : rechercher dans le référentiel.")
        )
    elif not customs:
        state = S.AMBIGUOUS
        findings.append(
            _finding(
                "AMBIGUOUS_FIELD",
                "review",
                f"Le champ « {observation.field_label} » ne permet pas de savoir s'il s'agit d'un code douanier.",
                raw_code=observation.raw_code,
            )
        )
    elif len({o.normalized_code for o in customs}) > 1:
        state = S.AMBIGUOUS
        findings.append(
            _finding(
                "CONFLICTING_CODES",
                "review",
                "Plusieurs codes douaniers différents sont rattachés à cette marchandise.",
                codes=[o.raw_code for o in customs],
            )
        )
    elif observation.normalized_code is None:
        state = S.NOT_FOUND
        findings.append(
            _finding(
                "MALFORMED_CODE",
                "review",
                f"« {observation.raw_code} » n'est pas un code numérique : original conservé, aucune réparation.",
            )
        )
    else:
        code = observation.normalized_code
        node = (
            TariffNode.objects.filter(edition=edition, code=code)
            .order_by("-declarable", "display_order")
            .select_related("edition")
            .first()
        )
        descendants = _declarable_descendants(edition, code)
        if node is not None and node.declarable:
            state = S.RECOGNIZED
        elif node is not None or descendants:
            state = S.INCOMPLETE
            findings.append(
                _finding(
                    "SUBDIVISIONS_REQUIRED",
                    "review",
                    "Code non déclarable tel quel dans cette édition : choisir une subdivision. "
                    "Aucun zéro n'est ajouté automatiquement.",
                    subdivisions=descendants,
                )
            )
        else:
            elsewhere = list(
                TariffNode.objects.filter(edition__in=visible_editions.exclude(pk=edition.pk), code=code)
                .select_related("edition")
                .order_by("edition__label")
            )
            if elsewhere:
                state = S.EDITION_MISMATCH
                findings.append(
                    _finding(
                        "FOUND_IN_OTHER_EDITION",
                        "review",
                        "Code absent de l'édition cible, présent ailleurs : correspondance documentée requise.",
                        editions=[
                            {"id": str(n.edition_id), "label": n.edition.label, "node_id": str(n.id)} for n in elsewhere
                        ],
                    )
                )
            else:
                state = S.NOT_FOUND
                prefix = next(
                    (
                        code[:n]
                        for n in range(len(code) - 1, 1, -1)
                        if TariffNode.objects.filter(edition=edition, code=code[:n]).exists()
                    ),
                    None,
                )
                findings.append(
                    _finding(
                        "CODE_NOT_FOUND",
                        "review",
                        "Code introuvable dans l'édition cible : original conservé, recherche proposée.",
                        nearest_existing_prefix=prefix,
                    )
                )
        if node is not None:
            for issue in ImportIssue.objects.filter(node=node, state=ImportIssue.State.OPEN).order_by("created_at")[
                :10
            ]:
                findings.append(
                    _finding("SOURCE_ISSUE", "review", issue.message, category=issue.category, issue_id=str(issue.id))
                )
            if node.label_damaged:
                findings.append(_finding("DAMAGED_LABEL", "review", "Libellé abîmé dans la source : lire la preuve."))
            if state == S.RECOGNIZED:
                findings.append(
                    _finding(
                        "CONSISTENCY_RULES_NOT_ENCODED",
                        "info",
                        "Aucune règle de cohérence marchandise/code n'est encore encodée : "
                        "notes et exclusions du chapitre à vérifier lors de la confirmation.",
                    )
                )

    return {"state": state, "node": node, "observation": observation, "findings": findings}


def goods_line_lines(goods_line: GoodsLine):
    from .models import InvoiceLine

    return InvoiceLine.objects.filter(goods_sources__goods_line=goods_line, organization=goods_line.organization)
