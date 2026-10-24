"""The legal draft import is idempotent and never grants operational applicability."""

import pytest
from django.core.management import call_command

from apps.regulations.models import DocumentRequirement, DocumentType, RegulatorySource


@pytest.mark.django_db
def test_cemac_draft_import_is_safe():
    call_command("seed_regulatory_drafts")
    call_command("seed_regulatory_drafts")
    source = RegulatorySource.objects.get(reference="11/22-CEMAC-UEAC-010A-CM-38")
    rules = DocumentRequirement.objects.filter(source=source)
    assert rules.count() == 16
    assert not rules.filter(published=True).exists()
    assert not rules.filter(verified=True).exists()
    assert source.verified_on is None
    assert DocumentType.objects.filter(code="transport_title").exists()
