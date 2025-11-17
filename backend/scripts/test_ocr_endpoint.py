"""
Script to test the OCR endpoint with a real declaration image.
"""

import sys
from pathlib import Path

import requests


def test_ocr_endpoint(image_path: str, port: int = 8000):
    """
    Test the /api/ocr/process_declaration endpoint.

    Args:
        image_path: Path to the image file to process
        port: Port where the backend server is running (default: 8000)
    """
    url = f"http://localhost:{port}/api/ocr/process_declaration"

    # Check if file exists
    if not Path(image_path).exists():
        print(f"❌ Error: File not found: {image_path}")
        return

    # Prepare the file for upload
    with open(image_path, "rb") as f:
        files = {"file": (Path(image_path).name, f, "image/jpeg")}

        print(f"📤 Uploading {image_path} to {url}...")

        try:
            response = requests.post(url, files=files, timeout=30)

            if response.status_code == 200:
                print("✅ Success!")
                result = response.json()

                print("\n📄 Extraction Results:")
                print(
                    f"   Declaration Number: {result.get('extracted_data', {}).get('declaration_number')}"
                )
                print(f"   Bureau: {result.get('extracted_data', {}).get('bureau')}")
                print(f"   Currency: {result.get('extracted_data', {}).get('currency')}")

                items = result.get("extracted_data", {}).get("items", [])
                print(f"   Items Found: {len(items)}")
                for i, item in enumerate(items[:3], 1):  # Show first 3 items
                    print(
                        f"      Item {i}: {item.get('hs_code')} - {item.get('description', 'N/A')[:50]}"
                    )

                taxes = result.get("extracted_data", {}).get("taxes", [])
                print(f"   Taxes Found: {len(taxes)}")
                for tax in taxes[:5]:  # Show first 5 taxes
                    print(f"      {tax.get('type')}: {tax.get('amount')}")

                print("\n📝 Raw Text Preview:")
                raw_preview = result.get("raw_text", "")[:300]
                print(f"   {raw_preview}...")

            else:
                print(f"❌ Error: {response.status_code}")
                print(f"   Response: {response.text}")

        except requests.exceptions.ConnectionError:
            print(f"❌ Error: Cannot connect to server at http://localhost:{port}")
            print("   Make sure the backend server is running!")
        except requests.exceptions.Timeout:
            print("❌ Error: Request timed out (OCR processing took too long)")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_ocr_endpoint.py <image_path> [port]")
        print("Example: python test_ocr_endpoint.py declaration.jpg 8000")
        sys.exit(1)

    image_path = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000

    test_ocr_endpoint(image_path, port)
