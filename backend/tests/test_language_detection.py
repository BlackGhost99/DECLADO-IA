from apps.extraction.language import detect_language


def test_french():
    assert detect_language("Facture fournisseur quantité montant marchandise")["locale"] == "fr"


def test_english():
    assert detect_language("Invoice supplier quantity amount freight insurance")["locale"] == "en"


def test_spanish():
    assert detect_language("Factura proveedor descripción cantidad importe seguro")["locale"] == "es"


def test_arabic():
    assert detect_language("فاتورة المورد وصف البضاعة الكمية السعر الإجمالي")["locale"] == "ar"


def test_numeric_invoice_is_unknown():
    assert detect_language("2026 001 3500 XAF 0101.21.00")["locale"] == ""


def test_ambiguous_languages_not_forced():
    assert detect_language("facture fournisseur montant invoice supplier amount")["locale"] == ""

def test_mixed_document_keeps_page_languages():
    from types import SimpleNamespace

    from apps.extraction.language import annotate_parsed

    def page(number, text):
        return SimpleNamespace(number=number, rows=[
            SimpleNamespace(index=0, text=text)
        ])

    parsed = SimpleNamespace(stats={})
    annotate_parsed(parsed, [
        page(1, "Facture fournisseur quantité montant marchandise"),
        page(2, "Invoice supplier quantity amount freight"),
        page(3, "Factura proveedor descripción cantidad importe"),
    ])
    pages = parsed.stats["language_detection"]["pages"]
    assert [item["locale"] for item in pages] == ["fr", "en", "es"]
    assert parsed.stats["language_detection"]["locale"] == ""
    assert len(parsed.stats["language_detection"]["zones"]) == 3
