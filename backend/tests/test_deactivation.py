"""ACC-03 / T02 : désactivation sans effacer les décisions passées, accès coupés immédiatement."""

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.organizations.models import Membership
from apps.organizations.services import deactivate_user


def test_deactivated_membership_loses_access_immediately(world, session):
    victim = session("declarant@a.test")
    created = victim.post("/api/v1/importers", {"name": "Créé avant désactivation"})
    assert created.status_code == 201

    member = Membership.objects.get(user__email="declarant@a.test")
    assert session("admin@a.test").post(f"/api/v1/organization/members/{member.id}/deactivate").status_code == 200

    resp = victim.get("/api/v1/importers")
    assert resp.status_code == 403
    assert resp.json()["code"] == "NO_ACTIVE_ORGANIZATION"
    assert victim.post("/api/v1/me/active-organization", {"organization_id": str(world["org_a"].id)}).status_code == 404

    event = AuditEvent.objects.get(event_type="importer.created", entity_id=created.json()["id"])
    assert event.actor.email == "declarant@a.test"


def test_deactivated_user_sessions_are_invalid_and_login_refused(world, session):
    victim = session("declarant@a.test")
    victim.post("/api/v1/importers", {"name": "Décision passée"})
    deactivate_user(user=User.objects.get(email="declarant@a.test"), actor=None)

    assert victim.get("/api/v1/me").status_code == 401
    assert session().login("declarant@a.test").status_code == 400
    assert User.objects.filter(email="declarant@a.test").exists()
    assert AuditEvent.objects.filter(actor__email="declarant@a.test", event_type="importer.created").exists()


def test_deactivated_organization_blocks_access(world, session):
    s = session("declarant@a.test")
    world["org_a"].active = False
    world["org_a"].save()
    assert s.get("/api/v1/importers").status_code == 403
