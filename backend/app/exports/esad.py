"""XML de type eSAD (déclaration en détail simplifiée), à partir d'un calcul."""

from __future__ import annotations

from datetime import date
from xml.etree import ElementTree as ET

from app.rules_engine import CalculationResult


def _text(parent: ET.Element, tag: str, value) -> ET.Element:
    el = ET.SubElement(parent, tag)
    el.text = "" if value is None else str(value)
    return el


def build_esad_xml(result: CalculationResult, meta: dict | None = None) -> bytes:
    meta = meta or {}
    data = result.to_dict()
    root = ET.Element("eSAD", {"version": "1.0"})

    header = ET.SubElement(root, "Header")
    _text(header, "DeclarationNumber", meta.get("declaration_number") or data["calculation_id"])
    _text(header, "DeclarationDate", meta.get("declaration_date") or date.today().isoformat())
    _text(header, "CustomsOffice", meta.get("customs_office"))
    _text(header, "Country", meta.get("country") or result.input_data.destination_country)
    _text(header, "Declarant", meta.get("declarant_name"))
    _text(header, "Exporter", meta.get("exporter_name"))
    _text(header, "Importer", meta.get("importer_name"))
    _text(header, "CalculationId", data["calculation_id"])

    item = ET.SubElement(root, "Item")
    for tag, key in (
        ("InvoiceNumber", "invoice_number"),
        ("HSCode", "hs_code"),
        ("Description", "description"),
        ("Quantity", "quantity"),
        ("UnitPrice", "unit_price"),
        ("Currency", "currency"),
        ("Incoterm", "incoterm"),
        ("OriginCountry", "origin_country"),
    ):
        _text(item, tag, data["input"][key])
    _text(item, "CIFValue", data["incoterms_conversion"]["cif_value"])
    _text(item, "TaxableBase", data["taxable_base"])

    taxes = ET.SubElement(root, "Taxes")
    breakdown = data["tax_breakdown"]
    duty = _text(taxes, "CustomsDuty", breakdown["customs_duty_amount"])
    duty.set("rate", breakdown["customs_duty_rate"])
    vat = _text(taxes, "VAT", breakdown["vat_amount"])
    vat.set("rate", breakdown["vat_rate"])
    vat.set("base", breakdown["vat_base"])
    for name, amount in breakdown["other_taxes"].items():
        _text(taxes, "OtherTax", amount).set("code", name)
    _text(taxes, "TotalTaxes", breakdown["total_taxes"])
    _text(taxes, "TotalAmount", breakdown["total_amount"])

    documents = ET.SubElement(root, "RequiredDocuments")
    for doc in result.required_documents:
        _text(documents, "Document", doc)
    warnings = ET.SubElement(root, "Warnings")
    for warning in result.warnings:
        _text(warnings, "Warning", warning)

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)
