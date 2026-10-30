"""Séparation exploitant/société : droits réels, isolation, conflits et journalisation."""

import pytest
from cryptography.fernet import Fernet

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.extraction.models import OrganizationAISettings
from tests.conftest import PASSWORD
from tests.test_onboarding import _enroll


@pytest.fixture
def operator(world, session, settings):
    settings.MFA_ENCRYPTION_KEY = Fernet.generate_key().decode()
    User.objects.create_user(email="owner@test.test", password=PASSWORD, is_platform_operator=True)
    s = session("owner@test.test")
    # Les nouveaux endpoints conservent le garde MFA de la plateforme.
    assert s.get("/api/v1/platform/ai-settings").json()["code"] == "MFA_REQUIRED"
    _enroll(s)
    return s


def test_platform_only_summary_and_quota(world, session, settings, operator):
    url = "/api/v1/platform/ai-settings"
    quota = f"/api/v1/platform/organizations/{world['org_b'].pk}/ai-quota"
    for email in ("admin@a.test", "admin@b.test", "declarant@a.test"):
        s = session(email)
        assert s.get(url).status_code == 403
        assert s.put(quota, {"monthly_cap": 400, "row_version": 0}).status_code == 403
    settings.AI_PROVIDER, settings.AI_API_KEY = "gemini", "secret-test-never-returned"
    summary = operator.get(url)
    assert summary.status_code == 200
    assert summary.json()["provider"]["configured"] is True
    assert "secret-test-never-returned" not in summary.content.decode()
    assert len(summary.json()["organizations"]) == 2
    for org in summary.json()["organizations"]:
        assert set(org) == {"id", "name", "monthly_cap", "row_version", "usage"}
    changed = operator.put(quota, {"monthly_cap": 400, "row_version": 0})
    assert changed.status_code == 200, changed.content
    assert changed.json()["monthly_cap"] == 400
    config = OrganizationAISettings.objects.for_organization(world["org_b"]).get()
    assert config.enabled is False  # attribuer un quota n'autorise jamais les envois
    assert operator.put(quota, {"monthly_cap": 900, "row_version": 0}).status_code == 409
    assert not OrganizationAISettings.objects.for_organization(world["org_a"]).exists()
    event = AuditEvent.objects.get(event_type="platform.ai_quota_updated")
    assert event.organization_id == world["org_b"].pk and event.scope == "platform"
    assert event.current == {"monthly_cap": 400}
    assert operator.put(quota, {"monthly_cap": -1, "row_version": config.row_version}).status_code == 400


def test_org_admin_cannot_raise_cap_but_can_activate(world, session, settings, operator):
    org_url = "/api/v1/organization/ai-settings"
    admin = session("admin@a.test")
    settings.AI_PROVIDER, settings.AI_API_KEY = "gemini", "test-only"
    result = admin.put(org_url, {"enabled": True, "mode": "auto", "monthly_cap": 9999, "row_version": 0})
    assert result.status_code == 403 and result.json()["code"] == "AI_CAP_OPERATOR_ONLY"
    assert not OrganizationAISettings.objects.for_organization(world["org_a"]).exists()
    quota = f"/api/v1/platform/organizations/{world['org_a'].pk}/ai-quota"
    assigned = operator.put(quota, {"monthly_cap": 50, "row_version": 0}).json()
    assert admin.put(org_url, {"enabled": True, "mode": "auto", "row_version": 0}).status_code == 409
    activated = admin.put(org_url, {"enabled": True, "mode": "on_demand", "row_version": assigned["row_version"]})
    assert activated.status_code == 200
    assert activated.json()["enabled"] is True and activated.json()["monthly_cap"] == 50
    assert session("admin@b.test").get(org_url).json()["enabled"] is False
    # Un exploitant sans affiliation ne peut pas consentir a la place de la société.
    assert operator.put(org_url, {"enabled": True, "mode": "auto", "row_version": 0}).status_code == 403


def test_django_superuser_is_not_platform_operator(world, session):
    User.objects.create_superuser(email="django@test.test", password=PASSWORD)
    assert session("django@test.test").get("/api/v1/platform/ai-settings").status_code == 403
