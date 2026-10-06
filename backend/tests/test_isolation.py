"""ACC-02 / T01 (socle) : aucune donnée d'une autre société, ni par liste, ni par URL, ni par paramètre."""

import pytest

from apps.clients.models import Importer
from apps.organizations.models import Membership


def test_list_only_shows_own_organization(world, session):
    names = [i["name"] for i in session("declarant@a.test").get("/api/v1/importers").json()["results"]]
    assert names == ["Importateur A"]


def test_search_does_not_leak_other_organization(world, session):
    results = session("declarant@a.test").get("/api/v1/importers", q="Importateur B").json()["results"]
    assert results == []


@pytest.mark.parametrize("method", ["get", "patch"])
def test_detail_of_other_organization_is_404_without_metadata(world, session, method):
    s = session("declarant@a.test")
    url = f"/api/v1/importers/{world['importer_b'].id}"
    resp = s.get(url) if method == "get" else s.patch(url, {"name": "piraté", "row_version": 1})
    assert resp.status_code == 404
    assert "Importateur B" not in resp.content.decode()
    world["importer_b"].refresh_from_db()
    assert world["importer_b"].name == "Importateur B"


def test_unknown_id_and_foreign_id_are_indistinguishable(world, session):
    s = session("declarant@a.test")
    foreign = s.get(f"/api/v1/importers/{world['importer_b'].id}")
    unknown = s.get("/api/v1/importers/00000000-0000-0000-0000-000000000000")
    assert foreign.status_code == unknown.status_code == 404
    assert foreign.json()["code"] == unknown.json()["code"]


def test_client_supplied_organization_is_ignored(world, session):
    s = session("declarant@a.test")
    resp = s.post(
        "/api/v1/importers",
        {"name": "Nouveau", "organization": str(world["org_b"].id), "organization_id": str(world["org_b"].id)},
    )
    assert resp.status_code == 201
    assert Importer.objects.get(pk=resp.json()["id"]).organization == world["org_a"]


def test_cannot_select_organization_without_membership(world, session):
    s = session("declarant@a.test")
    resp = s.post("/api/v1/me/active-organization", {"organization_id": str(world["org_b"].id)})
    assert resp.status_code == 404
    assert s.get("/api/v1/me").json()["active_organization_id"] == str(world["org_a"].id)


def test_members_and_audit_are_scoped(world, session):
    s = session("admin@a.test")
    emails = {m["email"] for m in s.get("/api/v1/organization/members").json()["results"]}
    assert emails == {"declarant@a.test", "validateur@a.test", "admin@a.test", "multi@test.test"}

    b_member = Membership.objects.get(user__email="declarant@b.test")
    assert s.post(f"/api/v1/organization/members/{b_member.id}/deactivate").status_code == 404
    b_member.refresh_from_db()
    assert b_member.active

    session("declarant@b.test").post("/api/v1/importers", {"name": "Créé chez B"})
    events = s.get("/api/v1/audit-events").json()["results"]
    assert all(e["entity_id"] != str(world["importer_b"].id) for e in events)
    assert not any(e["event_type"] == "importer.created" for e in events)


def test_queryset_without_organization_is_empty(world):
    assert not Importer.objects.for_organization(None).exists()
