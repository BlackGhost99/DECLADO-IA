from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.organizations.models import Organization


def test_no_missing_migrations(db):
    call_command("makemigrations", "--check", "--dry-run", stdout=StringIO())


def test_seed_demo_is_idempotent_and_marked_demo(db, settings):
    settings.DEBUG = True
    call_command("seed_demo", stdout=StringIO())
    call_command("seed_demo", stdout=StringIO())
    orgs = Organization.objects.all()
    assert orgs.count() == 2 and all(o.is_demo for o in orgs)


def test_seed_demo_refused_outside_debug(db, settings):
    settings.DEBUG = False
    with pytest.raises(CommandError):
        call_command("seed_demo", stdout=StringIO())
