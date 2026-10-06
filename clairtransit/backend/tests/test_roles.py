"""Droits côté serveur selon les rôles du cahier des charges (§5)."""

from apps.organizations.models import Membership, Role


def test_admin_without_business_role_can_read_but_not_create_importers(world, session):
    s = session("admin@a.test")
    assert s.get("/api/v1/importers").status_code == 200
    assert s.post("/api/v1/importers", {"name": "X"}).status_code == 403


def test_declarant_and_validator_can_create_importers(world, session):
    assert session("declarant@a.test").post("/api/v1/importers", {"name": "X"}).status_code == 201
    assert session("validateur@a.test").post("/api/v1/importers", {"name": "Y"}).status_code == 201


def test_only_org_admin_manages_members(world, session):
    for email in ("declarant@a.test", "validateur@a.test"):
        assert session(email).get("/api/v1/organization/members").status_code == 403


def test_admin_adds_member_and_new_user_can_log_in(world, session):
    s = session("admin@a.test")
    resp = s.post(
        "/api/v1/organization/members",
        {
            "email": "Nouveau@A.test",
            "full_name": "Nouveau",
            "roles": ["declarant"],
            "initial_password": "une-phrase-assez-longue-1",
        },
    )
    assert resp.status_code == 201, resp.content
    assert resp.json()["email"] == "nouveau@a.test"
    assert session().login("nouveau@a.test", "une-phrase-assez-longue-1").status_code == 200


def test_admin_rejects_unknown_role_and_weak_password(world, session):
    s = session("admin@a.test")
    bad_role = s.post(
        "/api/v1/organization/members",
        {"email": "x@a.test", "roles": ["superuser"], "initial_password": "une-phrase-assez-longue-1"},
    )
    assert bad_role.json()["code"] == "UNKNOWN_ROLE"
    weak = s.post(
        "/api/v1/organization/members", {"email": "x@a.test", "roles": ["declarant"], "initial_password": "123"}
    )
    assert weak.json()["code"] == "WEAK_PASSWORD"


def test_admin_changes_roles_with_row_version(world, session):
    s = session("admin@a.test")
    member = Membership.objects.get(user__email="declarant@a.test")
    url = f"/api/v1/organization/members/{member.id}/roles"
    ok = s.put(url, {"roles": ["declarant", "validator"], "row_version": member.row_version})
    assert ok.status_code == 200
    stale = s.put(url, {"roles": ["declarant"], "row_version": member.row_version})
    assert stale.status_code == 409
    member.refresh_from_db()
    assert member.roles == [Role.DECLARANT, Role.VALIDATOR]


def test_last_admin_cannot_be_removed(world, session):
    s = session("admin@a.test")
    me = Membership.objects.get(user__email="admin@a.test")
    resp = s.put(f"/api/v1/organization/members/{me.id}/roles", {"roles": ["declarant"], "row_version": 1})
    assert resp.status_code == 409
    assert resp.json()["code"] == "LAST_ADMIN"
    resp = s.post(f"/api/v1/organization/members/{me.id}/deactivate")
    assert resp.json()["code"] == "SELF_DEACTIVATION"
