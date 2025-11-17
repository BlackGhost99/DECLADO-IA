from xml.etree import ElementTree as ET

from app.exports.csv_json import calculation_to_csv, calculation_to_json
from app.exports.esad import build_esad_xml
from app.exports.pdf import build_calculation_pdf
from app.rules_engine import CalculationInput, CustomsCalculator


def _sample_input() -> CalculationInput:
    return CalculationInput(
        invoice_number="INV-TEST-001",
        hs_code="6109",
        description="T-shirts en coton",
        quantity=100,
        unit_price=5,
        currency="EUR",
        incoterm="CIF",
        origin_country="CN",
        destination_country="CM",
    )


def test_export_pdf_bytes():
    calc = CustomsCalculator()
    res = calc.calculate(_sample_input())
    pdf = build_calculation_pdf(res, extra_meta={"declarant_name": "Test"})
    assert isinstance(pdf, (bytes, bytearray)) and len(pdf) > 1000


def test_export_xml_parseable():
    calc = CustomsCalculator()
    res = calc.calculate(_sample_input())
    xml_bytes = build_esad_xml(
        res,
        {
            "declaration_number": "SAD-TEST-0001",
            "declarant_name": "DECLADO-IA",
            "exporter_name": "ACME",
            "importer_name": "Client SA",
            "customs_office": "CM-DLA",
            "country": "CM",
        },
    )
    # parseable
    root = ET.fromstring(xml_bytes)
    assert root.tag == "eSAD"
    assert root.find("Header/DeclarationNumber") is not None


def test_export_csv_basic():
    calc = CustomsCalculator()
    res = calc.calculate(_sample_input())
    csv_text = calculation_to_csv(res)
    assert "calculation_id,invoice_number,hs_code" in csv_text.splitlines()[0]
    assert res.input_data.invoice_number in csv_text


def test_export_json_basic():
    calc = CustomsCalculator()
    res = calc.calculate(_sample_input())
    js = calculation_to_json(res)
    assert '"calculation_id"' in js
