from types import SimpleNamespace

import pytest

from apps.localization.reports import summary_payload


@pytest.mark.parametrize("locale", ["fr", "en", "es", "ar"])
def test_internal_summary_languages(locale):
    rev = SimpleNamespace(
        state="draft", territory="GA",
        documents=SimpleNamespace(count=lambda: 3),
        invoices=SimpleNamespace(count=lambda: 2),
    )
    case = SimpleNamespace(reference="GA-2026-01", title="Import", current_revision=rev)
    result = summary_payload(case=case, locale=locale)
    assert result["locale"] == locale
    assert result["reference"] == "GA-2026-01"
    assert result["documents_count"] == 3
    assert result["is_official_declaration"] is False
    assert result["direction"] == ("rtl" if locale == "ar" else "ltr")


def test_unsupported_locale_rejected():
    rev = SimpleNamespace()
    case = SimpleNamespace(current_revision=rev)
    with pytest.raises(ValueError):
        summary_payload(case=case, locale="zz")
