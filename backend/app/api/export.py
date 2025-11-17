"""
API endpoints pour les exports (PDF, XML eSAD, CSV, JSON)
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from app.api.customs_calculation import CalculateRequest
from app.exports.csv_json import calculation_to_csv
from app.exports.esad import build_esad_xml
from app.exports.pdf import build_calculation_pdf
from app.rules_engine import CalculationInput, CustomsCalculator

router = APIRouter(prefix="/api/export", tags=["Export"])


class ExportMeta(BaseModel):
    declaration_number: str | None = None
    declarant_name: str | None = None
    exporter_name: str | None = None
    importer_name: str | None = None
    customs_office: str | None = None
    country: str | None = None
    declaration_date: str | None = Field(default=None, description="YYYY-MM-DD")


class ExportRequest(BaseModel):
    format: Literal["pdf", "xml_esad", "csv", "json"] = Field(..., description="Format d'export")
    calculation: CalculateRequest
    meta: ExportMeta | None = None


_calculator: CustomsCalculator | None = None


def get_calculator() -> CustomsCalculator:
    global _calculator
    if _calculator is None:
        _calculator = CustomsCalculator()
    return _calculator


@router.post("")
async def export_result(req: ExportRequest):
    # Construire l'input du calcul
    try:
        c = req.calculation
        calc_input = CalculationInput(
            invoice_number=c.invoice_number,
            hs_code=c.hs_code,
            description=c.description,
            quantity=c.quantity,
            unit_price=c.unit_price,
            currency=c.currency,
            incoterm=c.incoterm,
            origin_country=c.origin_country,
            destination_country=c.destination_country,
            freight_cost=c.freight_cost,
            insurance_cost=c.insurance_cost,
            exchange_rate=c.exchange_rate,
            exemption_code=c.exemption_code,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Requête export invalide: {e}") from e

    # Calculer
    calc = get_calculator()
    result = calc.calculate(calc_input)

    # Dispatcher sur format
    fmt = req.format
    filename_base = f"export_{result.calculation_id}"

    if fmt == "json":
        return JSONResponse(content=result.to_dict())

    if fmt == "csv":
        csv_text = calculation_to_csv(result)
        return PlainTextResponse(
            csv_text,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.csv"},
        )

    if fmt == "xml_esad":
        meta = (req.meta or ExportMeta()).model_dump(exclude_none=True)
        xml_bytes = build_esad_xml(result, meta)
        return StreamingResponse(
            iter([xml_bytes]),
            media_type="application/xml",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.xml"},
        )

    if fmt == "pdf":
        pdf_bytes = build_calculation_pdf(
            result, extra_meta=(req.meta or ExportMeta()).model_dump(exclude_none=True)
        )
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename={filename_base}.pdf"},
        )

    raise HTTPException(status_code=400, detail=f"Format non supporté: {fmt}")
