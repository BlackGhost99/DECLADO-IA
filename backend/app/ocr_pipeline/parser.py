"""
This module will contain the logic to parse the raw text extracted by the OCR
and transform it into a structured Pydantic model.
"""

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Party:
    """Represents a party (expediteur, destinataire, declarant)"""

    name: Optional[str] = None
    address: Optional[str] = None
    identifier: Optional[str] = None


@dataclass
class Item:
    """Represents an item in the declaration"""

    description: Optional[str] = None
    hs_code: Optional[str] = None
    quantity: Optional[float] = None
    gross_weight: Optional[float] = None
    net_weight: Optional[float] = None
    price: Optional[float] = None
    statistical_value: Optional[float] = None
    origin_country: Optional[str] = None


@dataclass
class Tax:
    """Represents a tax/duty line item"""

    type: Optional[str] = None  # DDI, TCI, TVA, etc.
    base: Optional[float] = None
    rate: Optional[float] = None
    amount: Optional[float] = None


@dataclass
class DeclarationData:
    """Main data structure for a customs declaration"""

    declaration_number: Optional[str] = None
    bureau: Optional[str] = None
    reference_douane: Optional[str] = None
    destinataire: Party = field(default_factory=Party)
    expediteur: Party = field(default_factory=Party)
    declarant: Party = field(default_factory=Party)
    transport_mode: Optional[str] = None
    country_origin: Optional[str] = None
    country_destination: Optional[str] = None
    currency: Optional[str] = None
    total_amount: Optional[float] = None
    items: List[Item] = field(default_factory=list)
    taxes: List[Tax] = field(default_factory=list)
    raw_text_preview: Optional[str] = None


def extract_declaration_number(text: str) -> Optional[str]:
    """Extract declaration number (Box 1) - format like OW110"""
    patterns = [
        r"DECLARATION[:\s]*([A-Z]{2}\d+)",
        r"\b([A-Z]{2}\d{3,6})\b",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).upper()
    return None


def extract_bureau(text: str) -> Optional[str]:
    """Extract customs bureau name"""
    patterns = [
        r"B\.([A-Z][A-Z\s\-]+)",
        r"bureau[:\s]+([A-Z][A-Z\s\-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def extract_party_info(text: str, box_keywords: List[str]) -> Party:
    """
    Extract party information (name, address, identifier) based on box keywords.
    Box keywords help locate the right section in the text.
    """
    party = Party()

    # Try to find the section by keywords
    for keyword in box_keywords:
        idx = text.lower().find(keyword.lower())
        if idx != -1:
            # Extract a chunk of text after the keyword (approx 300 chars)
            chunk = text[idx : idx + 300]

            # Extract name (usually on first line after keyword)
            lines = chunk.split("\n")
            if len(lines) > 1:
                party.name = lines[1].strip()[:100]

            # Try to find address
            address_match = re.search(r"([A-Z][A-Za-z\s,\-\.]+(?:\n[A-Za-z\s,\-\.]+){0,2})", chunk)
            if address_match:
                party.address = address_match.group(1).strip()[:200]

            break

    return party


def extract_hs_codes(text: str) -> List[str]:
    """Extract HS codes from the document - typically 8-10 digit codes"""
    hs_codes = []
    # HS codes are typically 6-10 digits
    matches = re.findall(r"\b(\d{6,10})\b", text)
    for match in matches:
        if match not in hs_codes and len(match) >= 6:
            hs_codes.append(match)
    return hs_codes


def extract_items(text: str) -> List[Item]:
    """
    Extract item information from Box 31 onwards.
    This is complex as items span multiple boxes.
    """
    items = []

    # Extract HS codes first
    hs_codes = extract_hs_codes(text)

    # Look for description patterns
    # Descriptions often follow patterns like "Points et elements" or start with capital letters
    description_pattern = r"([A-Z][a-z]+(?:\s+[a-z]+){2,10})"
    descriptions = re.findall(description_pattern, text)

    # Extract numeric values that could be weights, prices
    amounts = re.findall(r"(\d+[.,]\d{2,3})", text)

    # Create items based on what we found
    for i, hs_code in enumerate(hs_codes[:5]):  # Limit to first 5 items
        item = Item()
        item.hs_code = hs_code

        if i < len(descriptions):
            item.description = descriptions[i]

        if i < len(amounts):
            try:
                item.price = float(amounts[i].replace(",", "."))
            except ValueError:
                pass

        items.append(item)

    return items


def extract_taxes(text: str) -> List[Tax]:
    """Extract tax information from Box 47"""
    taxes = []

    # Common tax types in CEMAC
    tax_types = ["DDI", "TCI", "TVA", "OAD", "CA", "CS$", "CAF"]

    for tax_type in tax_types:
        # Look for pattern: TAX_TYPE ... amount ... rate ... total
        pattern = rf"{tax_type}\s+[\d.,]+\s+([\d.,]+)\s+([\d.,]+)"
        matches = re.findall(pattern, text)

        for match in matches:
            tax = Tax()
            tax.type = tax_type
            try:
                tax.rate = float(match[0].replace(",", "."))
                tax.amount = float(match[1].replace(",", "."))
            except ValueError:
                pass
            taxes.append(tax)

    return taxes


def extract_currency(text: str) -> Optional[str]:
    """Extract currency code"""
    currency_pattern = r"\b(XAF|USD|EUR|GBP|FCFA)\b"
    match = re.search(currency_pattern, text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return None


def parse_declaration(raw_text: str) -> Dict[str, Any]:
    """
    Parses the raw text from OCR to extract structured data from a customs declaration.

    Args:
        raw_text: The string content extracted from the document image/PDF.

    Returns:
        A dictionary with the extracted declaration data.
    """
    data = DeclarationData()

    # Extract basic information
    data.declaration_number = extract_declaration_number(raw_text)
    data.bureau = extract_bureau(raw_text)
    data.currency = extract_currency(raw_text)

    # Extract party information
    data.expediteur = extract_party_info(raw_text, ["Expediteur", "Exportateur", "Box 2"])
    data.destinataire = extract_party_info(raw_text, ["Destinataire", "Box 8"])
    data.declarant = extract_party_info(raw_text, ["Declarant", "Representant", "Box 14"])

    # Extract items and taxes
    data.items = extract_items(raw_text)
    data.taxes = extract_taxes(raw_text)

    # Store a preview of the raw text for debugging
    data.raw_text_preview = raw_text[:500] if len(raw_text) > 500 else raw_text

    # Convert to dictionary for JSON serialization
    result = {
        "declaration_number": data.declaration_number,
        "bureau": data.bureau,
        "currency": data.currency,
        "expediteur": {
            "name": data.expediteur.name,
            "address": data.expediteur.address,
            "identifier": data.expediteur.identifier,
        },
        "destinataire": {
            "name": data.destinataire.name,
            "address": data.destinataire.address,
            "identifier": data.destinataire.identifier,
        },
        "declarant": {
            "name": data.declarant.name,
            "address": data.declarant.address,
            "identifier": data.declarant.identifier,
        },
        "items": [
            {
                "description": item.description,
                "hs_code": item.hs_code,
                "quantity": item.quantity,
                "gross_weight": item.gross_weight,
                "net_weight": item.net_weight,
                "price": item.price,
                "statistical_value": item.statistical_value,
                "origin_country": item.origin_country,
            }
            for item in data.items
        ],
        "taxes": [
            {"type": tax.type, "base": tax.base, "rate": tax.rate, "amount": tax.amount}
            for tax in data.taxes
        ],
        "raw_text_preview": data.raw_text_preview,
    }

    print(f"✅ Extracted Declaration: {data.declaration_number}")
    print(f"   Bureau: {data.bureau}")
    print(f"   Items found: {len(data.items)}")
    print(f"   Taxes found: {len(data.taxes)}")

    return result
