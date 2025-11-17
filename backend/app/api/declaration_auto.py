"""
API: Déclaration automatique à partir de 3 documents (facture, transport, assurance)

Étapes:
- OCR des documents (image/PDF) via pipeline existante
- Extraction heuristique des champs clés (incoterm, hs, montants, devise)
- HS: utilise texte de facture → HS présent ou suggestion ML si absent
- Calcul douanier via Rules Engine (CustomsCalculator)
- Retourne les champs extraits + résultat détaillé du calcul

Remarques:
- Cette première version vise un flux simple 1-ligne: quantité=1, prix unitaire = total facture
- Si des détails de lignes sont détectés ultérieurement, on pourra éclater par article
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.ml.hs_classifier_service import get_classifier_service
from app.ocr_pipeline import pipeline as ocr_pipeline
from app.ocr_pipeline.parser import extract_hs_codes
from app.rules_engine import CalculationInput, CustomsCalculator
from app.security.antivirus import scan_file

router = APIRouter(prefix="/api/declaration", tags=["Declaration Auto"])


INCOTERM_RE = re.compile(r"\b(FOB|CIF|CFR|EXW|FCA|CPT|CIP|DAP|DDP|DAT)\b", re.IGNORECASE)
INVOICE_NO_RE = re.compile(r"\b(INVOICE\s*(NO|N°|NUMBER)[:\s-]*([A-Z0-9\-/.]+))\b", re.IGNORECASE)
ORIGIN_RE = re.compile(r"\b(Country\s*of\s*Origin|Origine)[:\s-]*([A-Z]{2})\b", re.IGNORECASE)
QTY_RE = re.compile(r"\b(Qty|Quantit[eé])[:\s]*([0-9]+)\b", re.IGNORECASE)


class ExtractedDoc(BaseModel):
    kind: str
    text_sample: str | None = None
    amounts: list[float] = []
    currencies: list[str] = []
    incoterm: str | None = None
    invoice_number: str | None = None
    hs_codes: list[str] = []
    origin_country: str | None = None


class AutoDeclarationResponse(BaseModel):
    extracted: dict[str, ExtractedDoc]
    calculation_input: dict[str, Any]
    calculation_result: dict[str, Any]
    export_hint: dict[str, Any] = Field(
        default_factory=dict, description="Suggestion de payload pour /api/export"
    )


def _save_upload_to_tmp(upload: UploadFile) -> str:
    suffix = os.path.splitext(upload.filename or "")[1] or ""
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    with open(tmp_path, "wb") as f:
        shutil.copyfileobj(upload.file, f)
    return tmp_path


def _run_ocr_from_any(file: UploadFile | None, local_path: str | None, label: str) -> dict:
    """Run OCR pipeline for given file upload or local path, with AV scan and errors."""
    if not file and not local_path:
        raise HTTPException(status_code=400, detail=f"{label}: fournir un fichier ou un chemin")

    src_path = None
    tmp_path = None
    try:
        if file is not None:
            tmp_path = _save_upload_to_tmp(file)
            src_path = tmp_path
        else:
            src_path = local_path
            if not src_path or not os.path.exists(src_path):
                raise HTTPException(status_code=404, detail=f"{label}: fichier introuvable")

        # Antivirus
        is_clean, av_msg = scan_file(src_path)
        if not is_clean:
            raise HTTPException(status_code=400, detail=f"{label}: Antivirus: {av_msg}")

        # OCR
        return ocr_pipeline.run_document(src_path, lang="eng+fra")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


def _text_from_ocr_result(res: dict) -> str:
    pages = res.get("pages", [])
    return "\n".join(p.get("text", "") for p in pages)


def _extract_incoterm(text: str) -> str | None:
    m = INCOTERM_RE.search(text)
    return m.group(1).upper() if m else None


def _extract_invoice_number(text: str) -> str | None:
    m = INVOICE_NO_RE.search(text)
    if m:
        return m.group(3).strip()
    # fallback: simple INV- pattern
    m2 = re.search(r"\bINV[-\s]?[A-Z0-9/.-]+\b", text, flags=re.IGNORECASE)
    return m2.group(0) if m2 else None


def _extract_origin(text: str) -> str | None:
    m = ORIGIN_RE.search(text)
    if m:
        return m.group(2).upper()
    # Try explicit ISO-2 hints like (CN), (FR)
    m2 = re.search(r"\(([A-Z]{2})\)\s*Origin", text)
    return m2.group(1).upper() if m2 else None


def _extract_qty(text: str) -> int | None:
    m = QTY_RE.search(text)
    if m:
        try:
            return int(m.group(2))
        except Exception:
            return None
    return None


@router.post("/auto", response_model=AutoDeclarationResponse)
async def auto_declaration(
    # Facture commerciale
    invoice: UploadFile | None = File(default=None),
    invoice_path: str | None = Form(default=None),
    # Facture de transport
    transport: UploadFile | None = File(default=None),
    transport_path: str | None = Form(default=None),
    # Attestation / Police d'assurance
    insurance: UploadFile | None = File(default=None),
    insurance_path: str | None = Form(default=None),
    # Overrides facultatifs
    hs_override: str | None = Form(default=None),
    origin_country: str | None = Form(default=None),
    destination_country: str | None = Form(default="CM"),
):
    """
    Reçoit 3 documents (fichiers ou chemins locaux), extrait les informations essentielles,
    calcule automatiquement DD/TVA/Autres taxes et retourne le tout.
    """

    import logging

    logger = logging.getLogger(__name__)
    logger.info(
        f"auto_declaration called: invoice={invoice}, transport={transport}, insurance={insurance}"
    )
    logger.info(
        f"Paths: invoice_path={invoice_path}, transport_path={transport_path}, insurance_path={insurance_path}"
    )

    if not invoice and not invoice_path:
        raise HTTPException(status_code=400, detail="Facture obligatoire (fichier ou chemin)")

    try:
        # 1) OCR des 3 documents
        inv_res = _run_ocr_from_any(invoice, invoice_path, "Facture")
        trp_res = (
            _run_ocr_from_any(transport, transport_path, "Transport")
            if (transport or transport_path)
            else None
        )
        ins_res = (
            _run_ocr_from_any(insurance, insurance_path, "Assurance")
            if (insurance or insurance_path)
            else None
        )

        inv_text = _text_from_ocr_result(inv_res)
        inv_norm = inv_res.get("normalized", {})

        # 2) Extraction champs facture
        incoterm = _extract_incoterm(inv_text) or (
            inv_norm.get("incoterm") if isinstance(inv_norm.get("incoterm"), str) else None
        )
        inv_no = _extract_invoice_number(inv_text)
        inv_hs_list = extract_hs_codes(inv_text)
        currencies = inv_norm.get("currencies", []) or []
        amounts = inv_norm.get("amounts", []) or []
        inv_total = max(amounts) if amounts else None
        qty = _extract_qty(inv_text) or 1

        # 3) Transport / Assurance montants
        freight = None
        insurance_amt = None
        if trp_res:
            trp_norm = trp_res.get("normalized", {})
            trp_amts = trp_norm.get("amounts", []) or []
            freight = max(trp_amts) if trp_amts else None
        if ins_res:
            ins_norm = ins_res.get("normalized", {})
            ins_amts = ins_norm.get("amounts", []) or []
            insurance_amt = max(ins_amts) if ins_amts else None

        # 4) Devise & incoterm défauts
        currency = (currencies[0] if currencies else None) or "EUR"
        incoterm = (incoterm or "CIF").upper()

        # 5) HS: si absent, ML sur snippet de texte
        hs_code = inv_hs_list[0] if inv_hs_list else None
        # Option 1: ML si non trouvé
        if not hs_code:
            snippet = inv_text[:300]
            clf = get_classifier_service()
            hs_guess = clf.suggest_hs_code(snippet)
            hs_code = hs_guess.get("hs_code") if hs_guess else None
        # Option 2: Override manuel si fourni
        if (not hs_code or hs_code == "unknown") and hs_override:
            only_digits = re.sub(r"\D", "", hs_override)[:6]
            if len(only_digits) >= 4:
                hs_code = only_digits
        if not hs_code or hs_code == "unknown":
            raise HTTPException(
                status_code=422, detail="Impossible d'extraire ou de suggérer le code HS"
            )

        # 6) Origine
        origin = (origin_country or _extract_origin(inv_text) or "CN").upper()
        dest = (destination_country or "CM").upper()

        # 7) Prix unitaire et quantité: on suppose 1 ligne (prix total)
        if not inv_total:
            raise HTTPException(status_code=422, detail="Total de facture introuvable")

        unit_price = inv_total  # 1 ligne → prix unitaire = total

        # 8) Construire input et calculer (normaliser en Decimal pour éviter les mélanges float/Decimal)
        def _to_decimal(val: Any) -> Decimal | None:
            if val is None:
                return None
            if isinstance(val, Decimal):
                return val
            try:
                # Utiliser str() pour éviter les imprécisions binaires des floats
                return Decimal(str(val))
            except Exception:
                return None

        calc_input = CalculationInput(
            invoice_number=inv_no or "INV-AUTO",
            hs_code=str(hs_code),
            description="Extraction automatique facture",  # TODO: améliorer avec description détectée
            quantity=_to_decimal(qty) or Decimal("1"),
            unit_price=_to_decimal(unit_price) or Decimal("0"),
            currency=currency,
            incoterm=incoterm,
            origin_country=origin,
            destination_country=dest,
            freight_cost=_to_decimal(freight),
            insurance_cost=_to_decimal(insurance_amt),
            exchange_rate=None,
            exemption_code=None,
        )

        calc = CustomsCalculator()
        result = calc.calculate(calc_input)

        # 9) Construire réponse
        extracted = {
            "invoice": ExtractedDoc(
                kind="invoice",
                text_sample=inv_text[:400],
                amounts=amounts,
                currencies=currencies,
                incoterm=incoterm,
                invoice_number=inv_no,
                hs_codes=inv_hs_list,
                origin_country=origin,
            ),
        }
        if trp_res:
            trp_text = _text_from_ocr_result(trp_res)
            trp_norm = trp_res.get("normalized", {})
            extracted["transport"] = ExtractedDoc(
                kind="transport",
                text_sample=trp_text[:300],
                amounts=trp_norm.get("amounts", []) or [],
                currencies=trp_norm.get("currencies", []) or [],
            )
        if ins_res:
            ins_text = _text_from_ocr_result(ins_res)
            ins_norm = ins_res.get("normalized", {})
            extracted["insurance"] = ExtractedDoc(
                kind="insurance",
                text_sample=ins_text[:300],
                amounts=ins_norm.get("amounts", []) or [],
                currencies=ins_norm.get("currencies", []) or [],
            )

        # Export hint to call /api/export
        export_hint = {
            "format": "pdf",
            "calculation": {
                "invoice_number": calc_input.invoice_number,
                "hs_code": calc_input.hs_code,
                "description": calc_input.description,
                "quantity": str(calc_input.quantity),
                "unit_price": str(calc_input.unit_price),
                "currency": calc_input.currency,
                "incoterm": calc_input.incoterm,
                "origin_country": calc_input.origin_country,
                "destination_country": calc_input.destination_country,
                "freight_cost": str(calc_input.freight_cost) if calc_input.freight_cost else None,
                "insurance_cost": (
                    str(calc_input.insurance_cost) if calc_input.insurance_cost else None
                ),
            },
            "meta": {
                "declaration_number": result.calculation_id,
                "customs_office": "CM-DLA",
            },
        }

        return AutoDeclarationResponse(
            extracted=extracted,
            calculation_input={
                "invoice_number": calc_input.invoice_number,
                "hs_code": calc_input.hs_code,
                "description": calc_input.description,
                "quantity": str(calc_input.quantity),
                "unit_price": str(calc_input.unit_price),
                "currency": calc_input.currency,
                "incoterm": calc_input.incoterm,
                "origin_country": calc_input.origin_country,
                "destination_country": calc_input.destination_country,
                "freight_cost": str(calc_input.freight_cost) if calc_input.freight_cost else None,
                "insurance_cost": (
                    str(calc_input.insurance_cost) if calc_input.insurance_cost else None
                ),
            },
            calculation_result=result.to_dict(),
            export_hint=export_hint,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur auto-déclaration: {str(e)}") from e
