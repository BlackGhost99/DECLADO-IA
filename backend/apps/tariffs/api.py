from rest_framework import serializers
from rest_framework.generics import ListAPIView
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.exceptions import ApiError

from . import services
from .models import (
    ImportIssue,
    ImportRun,
    LegalNote,
    NodeKind,
    PublicationState,
    RawTariffRecord,
    TariffEdition,
    TariffNode,
)

HISTORICAL_WARNING = (
    "Consultation historique : cette édition n'est pas validée comme tarif en vigueur. "
    "Ses valeurs ne s'appliquent pas automatiquement à un dossier actuel."
)
RATES_WARNING = "Observations lues dans la source, sans signification fiscale établie. Vide = inconnu (≠ 0)."


class IsReferenceManager(BasePermission):
    message = "Réservé aux gestionnaires du référentiel."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_reference_manager)


class EditionSerializer(serializers.ModelSerializer):
    source = serializers.SerializerMethodField()
    warning = serializers.SerializerMethodField()

    class Meta:
        model = TariffEdition
        fields = [
            "id",
            "label",
            "hs_version",
            "territory_scope",
            "effective_from",
            "effective_to",
            "applicability_verified",
            "publication_state",
            "published_at",
            "withdrawn_at",
            "source",
            "warning",
        ]

    def get_source(self, obj):
        src = obj.import_run.source
        return {
            "id": str(src.id),
            "title": src.title,
            "kind": src.kind,
            "kind_label": src.get_kind_display(),
            "is_derived_copy": src.is_derived_copy,
            "sha256": src.sha256,
            "publisher_claimed": src.publisher_claimed,
            "provenance_note": src.provenance_note,
        }

    def get_warning(self, obj):
        if obj.publication_state == PublicationState.OPERATIONAL:
            return None
        if obj.publication_state == PublicationState.WITHDRAWN:
            return "Édition retirée : conservée pour l'historique."
        if obj.publication_state == PublicationState.DRAFT:
            return "Brouillon en revue : non publié."
        return HISTORICAL_WARNING


def edition_brief(edition):
    return {"id": str(edition.id), "label": edition.label, "publication_state": edition.publication_state}


def node_brief(node):
    return {
        "id": str(node.id),
        "code": node.code,
        "code_display": node.code_display,
        "kind": node.kind,
        "label": node.label_clean,
        "declarable": node.declarable,
    }


class EditionListView(APIView):
    def get(self, request):
        editions = services.visible_editions(request.user)
        return Response(EditionSerializer(editions, many=True).data)


class SearchView(APIView):
    def get(self, request):
        params = request.query_params
        q = params.get("q", "")
        if not q.strip() and not params.get("code_prefix"):
            raise ApiError("QUERY_REQUIRED", "Saisissez un code, un préfixe ou des mots.", 400)
        results = services.search(
            user=request.user,
            q=q,
            edition_id=params.get("edition_id") or None,
            code_prefix=params.get("code_prefix"),
            limit=min(int(params.get("limit", 25)), 100),
        )
        return Response(
            {
                "results": [
                    {
                        **node_brief(r["node"]),
                        "reason": r["reason"],
                        "full_path": r["node"].full_path_label,
                        "validation_state": r["node"].validation_state,
                        "label_damaged": r["node"].label_damaged,
                        "edition": edition_brief(r["node"].edition),
                    }
                    for r in results
                ]
            }
        )


def _visible_node(request, node_id) -> TariffNode:
    node = (
        TariffNode.objects.select_related("edition__import_run__source", "source_record")
        .filter(pk=node_id, edition__in=services.visible_editions(request.user))
        .first()
    )
    if node is None:
        raise ApiError("NOT_FOUND", "Élément introuvable.", 404)
    return node


def _evidence(record: RawTariffRecord | None, line_no=None):
    if record is None:
        return None
    return {
        "record_id": str(record.id),
        "location": record.location_label,
        "page_index": record.page_index,
        "printed_page": record.printed_page,
        "cell_range": record.cell_range,
        "line": line_no,
    }


class NodeDetailView(APIView):
    def get(self, request, node_id):
        node = _visible_node(request, node_id)
        ancestors = []
        cursor = node.parent
        while cursor is not None:
            ancestors.insert(0, cursor)
            cursor = cursor.parent
        scope_codes = {a.code for a in ancestors + [node] if a.kind == NodeKind.CHAPTER and a.code}
        if node.code and len(node.code) >= 2:
            scope_codes.add(node.code[:2])
        sections = {a.code_display.removeprefix("Section ") for a in ancestors if a.kind == NodeKind.SECTION}
        notes = LegalNote.objects.filter(edition=node.edition).filter(
            scope_type="chapter", scope_ref__in=scope_codes
        ) | LegalNote.objects.filter(edition=node.edition, scope_type="section", scope_ref__in=sections)
        visible = services.visible_editions(request.user)
        related_notes = LegalNote.objects.filter(
            edition__in=visible.exclude(pk=node.edition_id), scope_type="chapter", scope_ref__in=scope_codes
        ).select_related("edition", "source_record")
        other_editions = (
            TariffNode.objects.filter(edition__in=visible.exclude(pk=node.edition_id), code=node.code).select_related(
                "edition"
            )
            if node.code
            else []
        )
        children = node.children.order_by("code", "display_order")[:300]

        def note_payload(n):
            return {
                "id": str(n.id),
                "scope_type": n.scope_type,
                "scope_ref": n.scope_ref,
                "heading": n.heading,
                "text": n.text_raw,
                "edition": edition_brief(n.edition),
                "evidence": _evidence(n.source_record),
            }

        issue_filter = {"node": node}
        return Response(
            {
                **node_brief(node),
                "label_raw": node.label_raw,
                "label_damaged": node.label_damaged,
                "label_available": bool(node.label_clean),
                "validation_state": node.validation_state,
                "full_path": node.full_path_label,
                "edition": EditionSerializer(node.edition).data,
                "ancestors": [node_brief(a) for a in ancestors],
                "children": [node_brief(c) for c in children],
                "evidence": _evidence(node.source_record),
                "occurrences": [
                    _evidence(o.source_record, o.line_no) | {"raw_code": o.raw_code}
                    for o in node.occurrences.select_related("source_record")
                ],
                "rate_observations": {
                    "warning": RATES_WARNING,
                    "items": [
                        {
                            "column": r.column,
                            "raw_value": r.raw_value,
                            "value": None if r.value is None else format(r.value.normalize(), "f"),
                            "quality": r.quality,
                        }
                        for r in node.rate_observations.all()
                    ],
                },
                "notes": [note_payload(n) for n in notes.select_related("edition", "source_record")],
                "related_notes": [note_payload(n) for n in related_notes],
                "same_code_in_other_editions": [
                    {**node_brief(o), "edition": edition_brief(o.edition)} for o in other_editions
                ],
                "issues": [
                    {
                        "id": str(i.id),
                        "category": i.category,
                        "severity": i.severity,
                        "message": i.message,
                        "state": i.state,
                    }
                    for i in ImportIssue.objects.filter(**issue_filter)
                ],
                "corrections": [
                    {
                        "field": c.field,
                        "previous": c.previous,
                        "current": c.current,
                        "reason": c.reason,
                        "evidence": c.evidence,
                        "actor": c.actor.email,
                        "at": c.at,
                    }
                    for c in node.corrections.select_related("actor")
                ],
            }
        )


class RecordView(APIView):
    """Preuve : contenu brut de la ligne ou de la page source."""

    def get(self, request, record_id):
        record = (
            RawTariffRecord.objects.select_related("run__source", "run__edition")
            .filter(pk=record_id, run__edition__in=services.visible_editions(request.user))
            .first()
        )
        if record is None:
            raise ApiError("NOT_FOUND", "Élément introuvable.", 404)
        source = record.run.source
        return Response(
            {
                **_evidence(record),
                "source": {
                    "title": source.title,
                    "kind": source.kind,
                    "is_derived_copy": source.is_derived_copy,
                    "sha256": source.sha256,
                },
                "header": RawTariffRecord.objects.filter(run=record.run, ordinal=1)
                .values_list("raw_cells", flat=True)
                .first()
                if record.cell_range
                else None,
                "raw_cells": record.raw_cells,
                "raw_text": record.raw_text,
            }
        )


class ImportRunSerializer(serializers.ModelSerializer):
    source = serializers.CharField(source="source.title")
    source_kind = serializers.CharField(source="source.kind")
    edition_id = serializers.UUIDField(source="edition.id")
    open_issues = serializers.IntegerField()

    class Meta:
        model = ImportRun
        fields = [
            "id",
            "source",
            "source_kind",
            "importer_name",
            "importer_version",
            "status",
            "started_at",
            "finished_at",
            "counts",
            "coverage",
            "edition_id",
            "open_issues",
        ]


class ImportRunListView(ListAPIView):
    permission_classes = [IsReferenceManager]
    serializer_class = ImportRunSerializer

    def get_queryset(self):
        from django.db.models import Count, Q

        return (
            ImportRun.objects.select_related("source", "edition")
            .annotate(open_issues=Count("issues", filter=Q(issues__state=ImportIssue.State.OPEN)))
            .order_by("-started_at")
        )


class IssueSerializer(serializers.ModelSerializer):
    evidence = serializers.SerializerMethodField()
    node = serializers.SerializerMethodField()

    class Meta:
        model = ImportIssue
        fields = [
            "id",
            "category",
            "severity",
            "message",
            "details",
            "state",
            "resolution",
            "resolution_reason",
            "resolved_at",
            "evidence",
            "node",
        ]

    def get_evidence(self, obj):
        return _evidence(obj.record, (obj.details or {}).get("line"))

    def get_node(self, obj):
        return node_brief(obj.node) if obj.node else None


class IssueListView(ListAPIView):
    permission_classes = [IsReferenceManager]
    serializer_class = IssueSerializer

    def get_queryset(self):
        qs = ImportIssue.objects.filter(run_id=self.kwargs["run_id"]).select_related("record", "node")
        for field in ("category", "severity", "state"):
            if value := self.request.query_params.get(field):
                qs = qs.filter(**{field: value})
        return qs.order_by("severity", "category", "created_at")


class ResolveIssueSerializer(serializers.Serializer):
    resolution = serializers.ChoiceField(choices=ImportIssue.Resolution.choices)
    reason = serializers.CharField()
    evidence = serializers.CharField(required=False, allow_blank=True, default="")
    correction = serializers.DictField(required=False)


class ResolveIssueView(APIView):
    permission_classes = [IsReferenceManager]

    def post(self, request, issue_id):
        data = ResolveIssueSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        issue = (
            ImportIssue.objects.select_for_update(of=("self",))
            .select_related("node__edition")
            .filter(pk=issue_id)
            .first()
        )
        if issue is None:
            raise ApiError("NOT_FOUND", "Élément introuvable.", 404)
        issue = services.resolve_issue(issue=issue, actor=request.user, **data.validated_data)
        return Response(IssueSerializer(issue).data)


class PublishSerializer(serializers.Serializer):
    mode = serializers.ChoiceField(choices=[PublicationState.CONSULTATION, PublicationState.OPERATIONAL])


class PublishEditionView(APIView):
    permission_classes = [IsReferenceManager]

    def post(self, request, edition_id):
        data = PublishSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        edition = TariffEdition.objects.filter(pk=edition_id).first()
        if edition is None:
            raise ApiError("NOT_FOUND", "Élément introuvable.", 404)
        edition = services.publish_edition(edition=edition, actor=request.user, mode=data.validated_data["mode"])
        return Response(EditionSerializer(edition).data)


class WithdrawEditionView(APIView):
    permission_classes = [IsReferenceManager]

    def post(self, request, edition_id):
        edition = TariffEdition.objects.filter(pk=edition_id).first()
        if edition is None:
            raise ApiError("NOT_FOUND", "Élément introuvable.", 404)
        edition = services.withdraw_edition(
            edition=edition, actor=request.user, reason=str(request.data.get("reason", ""))
        )
        return Response(EditionSerializer(edition).data)


class TariffImportView(APIView):
    """Import d'un tarif (.xlsx ou .csv) depuis l'écran ; un classeur SWD apporte aussi les taxes."""

    permission_classes = [IsReferenceManager]
    parser_classes = [MultiPartParser]

    def post(self, request):
        from .uploads import import_upload

        upload = request.FILES.get("file")
        if upload is None:
            raise ApiError("VALIDATION_ERROR", "Choisissez un fichier .xlsx ou .csv.", 400)
        return Response(
            import_upload(actor=request.user, upload=upload, label=str(request.data.get("label", ""))), status=201
        )
