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
