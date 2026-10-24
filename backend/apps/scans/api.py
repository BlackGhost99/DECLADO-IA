"""API de numérisation (NUM-01 à NUM-08). Lecture : tout membre actif ; écriture : déclarant ou validateur."""

from django.http import HttpResponse
from PIL import Image
from rest_framework import serializers
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cases.api import CanEdit, case_document_payload, get_case, user_brief
from apps.cases.models import CaseDocument
from apps.core.exceptions import ApiError
from apps.documents.storage import get_storage
from apps.organizations.permissions import HasActiveOrganization

from . import imaging, services
from .models import ScanBatch, ScanPage


def _page_payload(page: ScanPage, number: int | None) -> dict:
    return {
        "id": str(page.id),
        "number": number,
        "source_name": page.source.document.original_name,
        "source_page": page.source_page,
        "state": page.state,
        "state_label": page.get_state_display(),
        "rotation": page.rotation,
        "blank": page.blank,
        "hard_to_read": page.hard_to_read,
        "removed": page.removed,
        "removed_label": page.get_removed_display() if page.removed else "",
        "replaces_id": str(page.replaces.id) if hasattr(page, "replaces") else None,
        "title": page.title,
        "reference": page.reference,
        "page_marker": page.page_marker,
        "text_origin": page.text_origin,
        "notes": page.notes,
        "piece_id": str(page.piece_id) if page.piece_id else None,
        "has_image": bool(page.image_key),
    }


def batch_summary(batch: ScanBatch) -> dict:
    pages = [p for p in batch.pages.all() if p.removed != ScanPage.Removal.REPLACED]
    job = batch.job
    return {
        "id": str(batch.id),
        "case_id": str(batch.case_id),
        "source": batch.source,
        "source_label": batch.get_source_display(),
        "label": batch.label,
        "state": batch.state,
        "state_label": batch.get_state_display(),
        "created_by": user_brief(batch.created_by),
        "created_at": batch.created_at,
        "attached_at": batch.attached_at,
        "job": None
        if job is None
        else {"state": job.state, "phase": job.phase, "progress": job.progress, "error_message": job.error_message},
        "counts": {
            "pages": len(pages),
            "pending": sum(p.state == ScanPage.State.PENDING for p in pages),
            "kept": sum(not p.removed for p in pages),
            "unclassified": sum(not p.removed and p.piece_id is None for p in pages),
            "blank_removed": sum(p.removed == ScanPage.Removal.BLANK for p in pages),
            "hard_to_read": sum(not p.removed and p.hard_to_read for p in pages),
            "pieces": len({p.piece_id for p in pages if p.piece_id and not p.removed}),
        },
    }


def batch_payload(batch: ScanBatch) -> dict:
    data = batch_summary(batch)
    ordered = list(batch.pages.select_related("source__document", "replaced_by").order_by("position"))
    visible = [p for p in ordered if p.removed != ScanPage.Removal.REPLACED]
    numbers = {p.id: n for n, p in enumerate(visible, start=1)}
    links = {
        lk.id: lk
        for lk in CaseDocument.objects.filter(scan_piece__batch=batch).select_related(
            "document__uploaded_by", "added_by"
        )
    }
    data["sources"] = [
        {
            "id": str(s.id),
            "name": s.document.original_name,
            "page_count": s.page_count,
            "error": s.error,
        }
        for s in batch.sources.select_related("document")
    ]
    data["pieces"] = [
        {
            "id": str(piece.id),
            "ordinal": piece.ordinal,
            "usage": piece.usage,
            "usage_label": piece.get_usage_display(),
            "reason": piece.reason,
            "usage_by_user": piece.usage_by_user,
            "page_ids": [str(p.id) for p in visible if p.piece_id == piece.id and not p.removed],
            "case_document": case_document_payload(links[piece.case_document_id]) if piece.case_document_id else None,
        }
        for piece in batch.pieces.order_by("ordinal")
    ]
    data["pages"] = [_page_payload(p, numbers.get(p.id)) for p in visible]
    data["max_pages"] = services.max_pages()
    return data


def _batch(request, batch_id) -> ScanBatch:
    return services.batch_for(request.organization, batch_id)


class BatchInput(serializers.Serializer):
    source = serializers.ChoiceField(choices=ScanBatch.Source.choices)
    label = serializers.CharField(max_length=200, required=False, allow_blank=True)


class CaseBatchesView(APIView):
    permission_classes = [CanEdit]

    def get(self, request, case_id):
        case = get_case(request, case_id)
        qs = services.batches(request.organization).filter(case=case).prefetch_related("pages")
        return Response({"results": [batch_summary(b) for b in qs], "max_pages": services.max_pages()})

    def post(self, request, case_id):
        case = get_case(request, case_id)
        data = BatchInput(data=request.data)
        data.is_valid(raise_exception=True)
        batch = services.create_batch(
            org=request.organization,
            actor=request.user,
            case=case,
            source=data.validated_data["source"],
            label=data.validated_data.get("label", ""),
        )
        return Response(batch_payload(services.batch_for(request.organization, batch.id)), status=201)


class BatchDetailView(APIView):
    permission_classes = [CanEdit]

    def get(self, request, batch_id):
        return Response(batch_payload(_batch(request, batch_id)))


class BatchFilesView(APIView):
    """POST multipart : un ou plusieurs champs « files » (PDF, PNG, JPEG, TIFF)."""

    permission_classes = [CanEdit]
    parser_classes = [MultiPartParser]

    def post(self, request, batch_id):
        uploads = request.FILES.getlist("files")
        batch = services.add_files(org=request.organization, actor=request.user, batch_id=batch_id, uploads=uploads)
        return Response(batch_payload(services.batch_for(request.organization, batch.id)), status=201)


class BatchPhotoView(APIView):
    """POST multipart : file, et piece_id (pièce en cours) ou usage (nouvelle pièce)."""

    permission_classes = [CanEdit]
    parser_classes = [MultiPartParser]

    def post(self, request, batch_id):
        upload = request.FILES.get("file")
        if upload is None:
            raise ApiError("VALIDATION_ERROR", "Aucune photo reçue.", 400)
        page = services.add_photo(
            org=request.organization,
            actor=request.user,
            batch_id=batch_id,
            upload=upload,
            piece_id=request.data.get("piece_id") or None,
            usage=request.data.get("usage", ""),
        )
        batch = services.batch_for(request.organization, page.batch_id)
        return Response({"page_id": str(page.id), "batch": batch_payload(batch)}, status=201)


class BatchActionView(APIView):
    """POST : finish (fin de la prise de vue), attach (rattacher au dossier) ou cancel (abandonner)."""

    permission_classes = [CanEdit]
    parser_classes = [JSONParser]
    actions = {"finish": services.finish_capture, "attach": services.attach, "cancel": services.cancel}

    def post(self, request, batch_id, action):
        handler = self.actions.get(action)
        if handler is None:
            raise ApiError("NOT_FOUND", "Élément introuvable.", 404)
        batch = handler(org=request.organization, actor=request.user, batch_id=batch_id)
        return Response(batch_payload(services.batch_for(request.organization, batch.id)))


class PageInput(serializers.Serializer):
    rotation = serializers.IntegerField(required=False)
    removed = serializers.BooleanField(required=False)
    piece_id = serializers.CharField(required=False, allow_null=True)
    usage = serializers.ChoiceField(choices=CaseDocument.Usage.choices, required=False)


class PageDetailView(APIView):
    permission_classes = [CanEdit]
    parser_classes = [JSONParser]

    def patch(self, request, page_id):
        data = PageInput(data=request.data)
        data.is_valid(raise_exception=True)
        page = services.update_page(
            org=request.organization, actor=request.user, page_id=page_id, data=dict(data.validated_data)
        )
        return Response(batch_payload(services.batch_for(request.organization, page.batch_id)))


class PageSplitView(APIView):
    permission_classes = [CanEdit]

    def post(self, request, page_id):
        piece = services.split_at(org=request.organization, actor=request.user, page_id=page_id)
        return Response(batch_payload(services.batch_for(request.organization, piece.batch_id)))


class PageReplaceView(APIView):
    permission_classes = [CanEdit]
    parser_classes = [MultiPartParser]

    def post(self, request, page_id):
        upload = request.FILES.get("file")
        if upload is None:
            raise ApiError("VALIDATION_ERROR", "Aucun fichier reçu.", 400)
        page = services.replace_page(org=request.organization, actor=request.user, page_id=page_id, upload=upload)
        return Response(batch_payload(services.batch_for(request.organization, page.batch_id)), status=201)


class PageImageView(APIView):
    """Image de la page (taille réduite avec ?size=thumb), tournée comme l'agent l'a choisi."""

    permission_classes = [HasActiveOrganization]

    def get(self, request, page_id):
        page = services.page_for(request.organization, page_id)
        if not page.image_key:
            raise ApiError("IMAGE_UNAVAILABLE", "Page pas encore lue.", 404)
        with get_storage().open(page.image_key) as fh:
            image = Image.open(fh)
            image.load()
        side = imaging.THUMB_SIDE if request.query_params.get("size") == "thumb" else None
        response = HttpResponse(imaging.jpeg_bytes(image, rotation=page.rotation, side=side), content_type="image/jpeg")
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class PieceInput(serializers.Serializer):
    usage = serializers.ChoiceField(choices=CaseDocument.Usage.choices)


class PieceDetailView(APIView):
    permission_classes = [CanEdit]
    parser_classes = [JSONParser]

    def patch(self, request, piece_id):
        data = PieceInput(data=request.data)
        data.is_valid(raise_exception=True)
        piece = services.update_piece(
            org=request.organization, actor=request.user, piece_id=piece_id, usage=data.validated_data["usage"]
        )
        return Response(batch_payload(services.batch_for(request.organization, piece.batch_id)))


class PieceJoinView(APIView):
    permission_classes = [CanEdit]

    def post(self, request, piece_id):
        piece = services.join_previous(org=request.organization, actor=request.user, piece_id=piece_id)
        return Response(batch_payload(services.batch_for(request.organization, piece.batch_id)))
