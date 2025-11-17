"""
Script to test OCR directly on the PDF declaration file.
"""

import sys
from pathlib import Path

# Add the parent directory to the path so we can import from app
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.ocr_pipeline.parser import parse_declaration
from app.ocr_pipeline.processor import extract_text_from_pdf


def test_pdf_ocr(pdf_path: str):
    """
    Test the OCR processing on a PDF file.

    Args:
        pdf_path: Path to the PDF file
    """
    print(f"🔍 Testing OCR on: {pdf_path}\n")

    # Check if file exists
    if not Path(pdf_path).exists():
        print(f"❌ Error: File not found: {pdf_path}")
        return

    # Step 1: Extract text from PDF
    print("📄 Step 1: Extracting text from PDF...")
    raw_text = extract_text_from_pdf(pdf_path)

    if raw_text.startswith("Error"):
        print(f"❌ {raw_text}")
        return

    print(f"\n✅ Extracted {len(raw_text)} characters\n")

    # Step 2: Parse the extracted text
    print("🔎 Step 2: Parsing declaration data...")
    extracted_data = parse_declaration(raw_text)

    # Step 3: Display results
    print("\n" + "=" * 60)
    print("📊 EXTRACTION RESULTS")
    print("=" * 60)

    print(f"\n🔢 Declaration Number: {extracted_data.get('declaration_number', 'Not found')}")
    print(f"🏢 Bureau: {extracted_data.get('bureau', 'Not found')}")
    print(f"💰 Currency: {extracted_data.get('currency', 'Not found')}")

    print("\n👤 PARTIES:")
    print(f"   Expéditeur: {extracted_data.get('expediteur', {}).get('name', 'Not found')}")
    print(f"   Destinataire: {extracted_data.get('destinataire', {}).get('name', 'Not found')}")
    print(f"   Déclarant: {extracted_data.get('declarant', {}).get('name', 'Not found')}")

    items = extracted_data.get("items", [])
    print(f"\n📦 ITEMS ({len(items)} found):")
    for i, item in enumerate(items[:5], 1):  # Show first 5
        print(
            f"   {i}. HS: {item.get('hs_code', 'N/A')[:8]} - {item.get('description', 'N/A')[:60]}"
        )

    taxes = extracted_data.get("taxes", [])
    print(f"\n💵 TAXES ({len(taxes)} found):")
    for tax in taxes[:10]:  # Show first 10
        print(
            f"   {tax.get('type', 'N/A'):6s}: Rate={tax.get('rate', 0):6.2f}  Amount={tax.get('amount', 0):10.2f}"
        )

    print("\n" + "=" * 60)
    print("\n📝 Raw text preview (first 500 chars):")
    print("-" * 60)
    print(extracted_data.get("raw_text_preview", "")[:500])
    print("-" * 60)


if __name__ == "__main__":
    # Default to the PDF in the backend directory
    pdf_path = r"C:\Users\BlackGhost\Desktop\DECLADO-IA\backend\Déclaration.pdf"

    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]

    test_pdf_ocr(pdf_path)
