# ruff: noqa: F811  (fixtures importées)
"""Partage d'un dossier entre sociétés (COL-01 à COL-07, T107 à T110), sur des données fictives."""

from apps.audit.models import AuditEvent
from apps.organizations.models import Organization, Role
from apps.sharing.models import CaseShare, CaseShareNote
from tests.conftest import _user
from tests.test_fiscal import _private_storage, confirm, edition, schedule  # noqa: F401
from tests.test_validation import ready_case


def _code(s):
    resp = s.get("/api/v1/organization/partner-code")
    assert resp.status_code == 200, resp.content
    return resp.json()["code"]


def _share(case, code, level="comment", **extra):
    return case["s"].post(f"/api/v1/cases/{case['id']}/shares", {"code": code, "level": level, **extra})


def test_t107_partner_code_is_per_company_and_renewed_by_admin_only(world, session):
    admin_b = session("admin@b.test")
    code = _code(admin_b)
    assert code.startswith("CT-") and len(code) == 12
    assert _code(admin_b) == code  # stable
    # Tout membre lit le code pour le donner à un client ; seul l'administrateur le renouvelle.
    declarant_b = session("declarant@b.test")
    assert _code(declarant_b) == code
    assert declarant_b.post("/api/v1/organization/partner-code").status_code == 403
    renewed = admin_b.post("/api/v1/organization/partner-code").json()["code"]
    assert renewed != code
    assert _code(session("admin@a.test")) not in (code, renewed)
    assert AuditEvent.objects.filter(event_type="partner_code.regenerated", organization=world["org_b"]).exists()


def test_t108_share_invitation_accept_snapshot_and_access_log(world, schedule, edition, session):
    case, body = ready_case(session, edition)
    admin_b = session("admin@b.test")
    code = _code(admin_b)
    assert _share(case, "CT-0000-0000").json()["code"] == "PARTNER_NOT_FOUND"
    assert _share(case, _code(session("admin@a.test"))).json()["code"] == "SELF_SHARE"
    resp = _share(case, code.lower().replace("-", " "), message="Pour avis (fictif)")
    assert resp.status_code == 201, resp.content
    share = resp.json()
    assert share["status"] == "pending" and share["organization"]["name"] == "Société B"
    assert _share(case, code).json()["code"] == "SHARE_EXISTS"

    # En attente : visible dans la liste, mais rien du dossier n'est lisible.
    incoming = admin_b.get("/api/v1/shares/incoming").json()["results"]
    assert [s["id"] for s in incoming] == [share["id"]] and incoming[0]["case_id"] is None
    assert admin_b.get(f"/api/v1/shares/{share['id']}").json()["code"] == "SHARE_CLOSED"
    # Un déclarant de B ne décide pas ; l'administrateur accepte.
    assert session("declarant@b.test").post(f"/api/v1/shares/{share['id']}/accept").status_code == 403
    assert case["s"].post(f"/api/v1/shares/{share['id']}/accept").status_code == 404  # propriétaire ≠ partenaire
    accepted = admin_b.post(f"/api/v1/shares/{share['id']}/accept")
    assert accepted.status_code == 200 and accepted.json()["status"] == "accepted"
    assert admin_b.post(f"/api/v1/shares/{share['id']}/refuse").json()["code"] == "SHARE_ALREADY_DECIDED"

    detail = session("declarant@b.test").get(f"/api/v1/shares/{share['id']}")
    assert detail.status_code == 200, detail.content
    snap = detail.json()["case"]
    assert snap["reference"] == body["reference"] and snap["owner"] == "Société A"
    assert {"documents", "invoices", "goods", "state"} <= set(snap)
    # Le partage n'ouvre jamais les écrans de travail du dossier.
    assert admin_b.get(f"/api/v1/cases/{case['id']}").status_code == 404
    assert admin_b.get(f"/api/v1/cases/{case['id']}/shares").status_code == 404
    # Journal des consultations chez le propriétaire.
    assert AuditEvent.objects.filter(event_type="case_share.viewed", organization=world["org_a"]).count() == 1
    assert AuditEvent.objects.filter(event_type="case_share.accepted", organization=world["org_b"]).count() == 1


def test_t109_notes_follow_the_level_and_both_sides_read_them(world, schedule, edition, session):
    case, _ = ready_case(session, edition)
    admin_b = session("admin@b.test")
    code = _code(admin_b)
    read_only = _share(case, code, level="read").json()
    admin_b.post(f"/api/v1/shares/{read_only['id']}/accept")
    note = admin_b.post(f"/api/v1/shares/{read_only['id']}/notes", {"text": "Code à revoir (fictif)"})
    assert note.status_code == 403 and note.json()["code"] == "SHARE_READ_ONLY"
    case["s"].post(f"/api/v1/shares/{read_only['id']}/revoke", {"reason": "Niveau à changer"})

    share = _share(case, code, level="comment").json()
    admin_b.post(f"/api/v1/shares/{share['id']}/accept")
    assert admin_b.post(f"/api/v1/shares/{share['id']}/notes", {"text": "  "}).status_code == 400
    resp = admin_b.post(f"/api/v1/shares/{share['id']}/notes", {"text": "Ligne 1 : chapitre 84 plutôt (fictif)."})
    assert resp.status_code == 201
    resp = case["s"].post(f"/api/v1/shares/{share['id']}/notes", {"text": "Bien reçu (fictif)."})
    notes = resp.json()["notes"]
    assert [n["organization"] for n in notes] == ["Société B", "Société A"]
    assert [n["own"] for n in notes] == [False, True]
    owner_view = case["s"].get(f"/api/v1/shares/{share['id']}").json()
    assert "case" not in owner_view and len(owner_view["notes"]) == 2
    assert CaseShareNote.objects.count() == 2


def test_t110_revocation_and_cross_tenant_isolation(world, schedule, edition, session):
    case, _ = ready_case(session, edition)
    admin_b = session("admin@b.test")
    share = _share(case, _code(admin_b)).json()
    admin_b.post(f"/api/v1/shares/{share['id']}/accept")
    org_c = Organization.objects.create(name="Société C")
    _user("admin@c.test", org_c, [Role.ORG_ADMIN])
    admin_c = session("admin@c.test")
    for url in (f"/api/v1/shares/{share['id']}", f"/api/v1/shares/{share['id']}/notes"):
        assert admin_c.get(url).status_code in (404, 405)
    assert admin_c.get(f"/api/v1/shares/{share['id']}").status_code == 404
    assert admin_c.post(f"/api/v1/shares/{share['id']}/notes", {"text": "x"}).status_code == 404
    assert admin_c.post(f"/api/v1/shares/{share['id']}/revoke").status_code == 404
    assert admin_c.get("/api/v1/shares/incoming").json()["results"] == []
    # Le partenaire ne retire pas le partage ; le propriétaire si.
    assert admin_b.post(f"/api/v1/shares/{share['id']}/revoke").status_code == 404
    resp = case["s"].post(f"/api/v1/shares/{share['id']}/revoke", {"reason": "Fin de mission (fictif)"})
    assert resp.status_code == 200 and resp.json()["status"] == "revoked"
    assert admin_b.get(f"/api/v1/shares/{share['id']}").json()["code"] == "SHARE_CLOSED"
    assert admin_b.get("/api/v1/shares/incoming").json()["results"] == []
    assert CaseShare.objects.get(pk=share["id"]).revoked_at is not None
    # Après retrait, un nouveau partage avec la même société est possible.
    assert _share(case, _code(admin_b)).status_code == 201
