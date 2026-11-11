"""Dépôt groupé : lecture après antivirus, proposition puis confirmation des dossiers."""

from django.db import transaction

from apps.core.exceptions import ApiError
from apps.documents import services as documents
from apps.documents.models import Document
from apps.extraction import services as extraction

from . import services
from .intake_grouping import group_shipments
from .intake_reading import analyze

MAX_DOCUMENTS = 200
NOT_FOUND = ("NOT_FOUND", "Pièce introuvable.", 404)


def upload(*, org, actor, upload, declared_mime="") -> tuple[Document, list[str]]:
    """Dépôt d'une pièce sans dossier. Un fichier identique déjà présent est réutilisé, pas doublé."""

    class _Duplicate(Exception):
        pass

    try:
        with transaction.atomic():
            document = documents.store_upload(organization=org, actor=actor, upload=upload, declared_mime=declared_mime)
            duplicates = documents.find_duplicates(org, document.sha256, exclude_id=document.id)
            if duplicates:
                documents.get_storage().discard(document.object_key)
                raise _Duplicate(duplicates[0])
    except _Duplicate as dup:
        document = dup.args[0]
    cases = sorted({link.revision.case.reference for link in document.case_links.select_related("revision__case")})
    return document, cases


def _documents(org, ids) -> list[Document]:
    if not isinstance(ids, list) or not ids or len(ids) > MAX_DOCUMENTS:
        raise ApiError("VALIDATION_ERROR", f"Indiquer de 1 à {MAX_DOCUMENTS} pièces.", 400)
    ids = [str(i) for i in ids]
    if len(set(ids)) != len(ids):
        raise ApiError("VALIDATION_ERROR", "Une pièce ne peut figurer qu'une fois.", 400)
    try:
        found = {str(d.id): d for d in Document.objects.for_organization(org).filter(pk__in=ids)}
    except Exception:
        raise ApiError(*NOT_FOUND) from None
    if len(found) != len(ids):
        raise ApiError(*NOT_FOUND)
    return [found[i] for i in ids]


def propose(*, org, document_ids) -> dict:
    return group_shipments([analyze(document) for document in _documents(org, document_ids)])


def create_cases(*, org, actor, groups) -> list[dict]:
    """Crée un dossier par groupe confirmé, y rattache ses pièces et demande leur lecture."""
    if not isinstance(groups, list) or not groups or len(groups) > MAX_DOCUMENTS:
        raise ApiError("VALIDATION_ERROR", "Indiquer au moins un dossier à créer.", 400)
    all_ids = []
    for g in groups:
        if not isinstance(g, dict) or not isinstance(g.get("document_ids"), list) or not g["document_ids"]:
            raise ApiError("VALIDATION_ERROR", "Chaque dossier doit contenir au moins une pièce.", 400)
        all_ids += [str(i) for i in g["document_ids"]]
    docs = {str(d.id): d for d in _documents(org, all_ids)}
    created, links = [], []
    with transaction.atomic():
        for g in groups:
            title = str(g.get("title") or "").strip()[:200]
            case = services.create_case(org=org, actor=actor, data={"title": title})
            revision = case.current_revision
            for doc_id in g["document_ids"]:
                link = services._link_document(org, actor, revision, docs[str(doc_id)], services.AUTO)
                links.append(link)
            services._event(
                org,
                actor,
                "case.created_from_intake",
                case,
                case,
                current={"documents": [str(i) for i in g["document_ids"]], "title": title},
            )
            created.append({"id": str(case.id), "reference": case.reference, "title": title,
                            "documents": len(g["document_ids"])})  # fmt: skip
        for link in links:
            try:
                extraction.request_extraction(
                    org=org,
                    actor=actor,
                    link_id=link.id,
                    ocr=link.document.intake_analysis.get("reading_status") == "ocr",
                )
            except ApiError:
                pass  # pièce sans lecture automatique : elle reste jointe, l'agent la traite à la main
    return created
