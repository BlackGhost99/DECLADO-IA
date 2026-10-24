from types import SimpleNamespace
from unittest.mock import MagicMock

from apps.cases.validation_readiness import validation_readiness


def test_missing_tax_engine_is_a_hard_block():
    documents = MagicMock()
    documents.filter.return_value = documents
    documents.exclude.return_value.exists.return_value = False
    documents.exists.return_value = True
    goods = MagicMock()
    goods.exists.return_value = True
    edition = SimpleNamespace(publication_state="operational")
    revision = SimpleNamespace(
        pk="test", revision_no=1, target_edition=edition,
        documents=documents, goods_lines=goods,
    )
    result = validation_readiness(revision, {"blocking": [], "warnings": [], "complete": True})
    assert result["complete"] is False
    assert any(item["field"] == "tax_calculation" for item in result["blocking"])


def test_historical_tariff_is_blocked():
    documents = MagicMock()
    documents.filter.return_value = documents
    documents.exclude.return_value.exists.return_value = False
    documents.exists.return_value = True
    goods = MagicMock()
    goods.exists.return_value = True
    revision = SimpleNamespace(
        pk="test", revision_no=1,
        target_edition=SimpleNamespace(publication_state="consultation"),
        documents=documents, goods_lines=goods,
    )
    result = validation_readiness(revision, {"blocking": [], "warnings": [], "complete": True})
    assert any(item["field"] == "target_edition" for item in result["blocking"])
