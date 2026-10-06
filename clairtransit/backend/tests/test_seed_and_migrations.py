from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.cases.models import CustomsCase
from apps.organizations.models import Organization


def test_no_missing_migrations(db):
    call_command("makemigrations", "--check", "--dry-run", stdout=StringIO())


def test_seed_demo_is_idempotent_and_marked_demo(db, settings, tmp_path):
    settings.DEBUG = True
    settings.PRIVATE_STORAGE_ROOT = tmp_path
    call_command("seed_demo", stdout=StringIO())
    call_command("seed_demo", stdout=StringIO())
    orgs = Organization.objects.all()
    assert orgs.count() == 2 and all(o.is_demo for o in orgs)
    [case] = CustomsCase.objects.all()
    assert case.organization.name == "Transit Alpha (démo)" and case.current_revision.mode == "demo"
    assert case.current_revision.documents.get().document.readability == "ok"


def test_seed_demo_refused_outside_debug(db, settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_demo", stdout=StringIO())
