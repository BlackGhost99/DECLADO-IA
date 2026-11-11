"""Public staging uses distinct, stable, synthetic demo identities and no real memberships."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings

from apps.accounts.models import User
from apps.organizations.management.commands.seed_demo import USERS, staging_password
from apps.organizations.models import Membership, Organization, Role

SEED = "a-synthetic-private-test-key-with-more-than-32-characters"


@pytest.fixture
def staging_demo_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("STAGING_DEMO_PASSWORD_SEED", SEED)


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_staging_demo_has_8_agents_and_unique_passwords(staging_demo_env):
    call_command("seed_demo", no_case=True, hide_password=True)
    assert User.objects.filter(email__in=[email for email, *_ in USERS]).count() == 12
    alpha = Organization.objects.get(name="Transit Alpha (démo)")
    beta = Organization.objects.get(name="Transit Bêta (démo)")
    assert alpha.is_demo and beta.is_demo
    assert Membership.objects.filter(organization=alpha).count() == 6  # 4 agents + admin + shared
    assert Membership.objects.filter(organization=beta).count() == 6

    for email, _name, _roles in USERS:
        user = User.objects.get(email=email)
        assert user.check_password(staging_password(SEED, email))
        assert not user.is_superuser and not user.is_platform_operator
    assert len({staging_password(SEED, email) for email, *_ in USERS}) == 12

    admin = User.objects.get(email="admin@alpha.demo")
    assert Membership.objects.get(user=admin, organization=alpha).roles == [Role.ORG_ADMIN]
    assert not admin.memberships.filter(organization=beta).exists()
    multi = User.objects.get(email="multi@demo.demo")
    assert Membership.objects.get(user=multi, organization=alpha).roles == [Role.DECLARANT]
    assert Membership.objects.get(user=multi, organization=beta).roles == [Role.DECLARANT]


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_staging_seed_resets_existing_accounts_and_keeps_memberships(staging_demo_env):
    call_command("seed_demo", no_case=True, hide_password=True)
    admin = User.objects.get(email="admin@beta.demo")
    admin.set_password("obsolete-staging-password")
    admin.save(update_fields=["password"])
    call_command("seed_demo", no_case=True, hide_password=True)
    admin.refresh_from_db()
    assert admin.check_password(staging_password(SEED, admin.email))
    assert admin.memberships.count() == 1
    assert User.objects.filter(email__in=[email for email, *_ in USERS]).count() == 12


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_staging_seed_rejects_accounts_belonging_to_non_demo_societies(staging_demo_env):
    real_org = Organization.objects.create(name="Société réelle", is_demo=False)
    user = User.objects.create_user(email="declarant@alpha.demo", password="unchanged-password")
    Membership.objects.create(organization=real_org, user=user, roles=[Role.DECLARANT])
    with pytest.raises(CommandError, match="droits réels"):
        call_command("seed_demo", no_case=True, hide_password=True)
    user.refresh_from_db()
    assert user.check_password("unchanged-password")


@pytest.mark.django_db
@override_settings(DEBUG=True)
def test_staging_seed_requires_a_server_side_secret(staging_demo_env, monkeypatch):
    monkeypatch.delenv("STAGING_DEMO_PASSWORD_SEED")
    with pytest.raises(CommandError, match="STAGING_DEMO_PASSWORD_SEED"):
        call_command("seed_demo", no_case=True, hide_password=True)
