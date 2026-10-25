"""Mise en route : premier lancement, demandes d'espace, console de l'exploitant, invitations, agences.

Chaque endpoint nouveau a son test d'accès croisé (société B, rôle insuffisant, non-exploitant).
"""

from datetime import timedelta

import pytest
from cryptography.fernet import Fernet
from django.core.cache import cache
from django.utils import timezone

from apps.accounts import mfa
from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.onboarding.models import AccessRequest, Invitation
from apps.organizations.business_models import Agency
from apps.organizations.models import Membership, Organization, Role
from tests.conftest import PASSWORD, Session

STRONG = "Une-phrase-longue-2026"


@pytest.fixture(autouse=True)
def mfa_key(settings):
    settings.MFA_ENCRYPTION_KEY = Fernet.generate_key().decode("ascii")
    cache.clear()


def _enroll(s: Session):
    secret = s.post("/api/v1/auth/mfa/setup").json()["secret"]
    done = s.post("/api/v1/auth/mfa/confirm", {"code": mfa._totp(secret, int(mfa.time.time() // mfa.PERIOD))})
    assert done.status_code == 200, done.content


@pytest.fixture
def operator(db):
    """Exploitant déjà mis en service, double authentification active."""
    User.objects.create_user(email="ops@ct.test", password=STRONG, full_name="Exploitant", is_platform_operator=True)
    s = Session()
    assert s.login("ops@ct.test", STRONG).status_code == 200
    _enroll(s)
    return s


ORG = {
    "name": "Trans Exemple",
    "primary_profile": "transit",
    "country_code": "GA",
    "default_locale": "fr",
    "max_users": 3,
    "admin_name": "Admin Exemple",
    "admin_email": "admin@trans.test",
}


# ---------- Premier lancement ----------


def test_first_launch_creates_single_operator_who_must_enable_mfa(db):
    s = Session()
    assert s.get("/api/v1/auth/setup").json() == {"needs_setup": True}
    weak = s.post("/api/v1/auth/setup", {"full_name": "X", "email": "ops@ct.test", "password": "court"})
    assert weak.status_code == 400 and weak.json()["code"] == "WEAK_PASSWORD"
    created = s.post("/api/v1/auth/setup", {"full_name": "Exploitant", "email": "OPS@ct.test", "password": STRONG})
    assert created.status_code == 201, created.content
    me = created.json()
    assert me["is_platform_operator"] is True
    assert me["is_reference_manager"] is True
    assert me["memberships"] == []
    assert me["mfa_required_for_access"] is True
    # Sans double authentification, la console reste fermée même en mode local (MFA_ENFORCE désactivé).
    blocked = s.get("/api/v1/platform/organizations")
    assert blocked.status_code == 403 and blocked.json()["code"] == "MFA_REQUIRED"
    _enroll(s)
    assert s.get("/api/v1/platform/organizations").status_code == 200
    assert AuditEvent.objects.filter(event_type="platform.setup").count() == 1

    other = Session()
    assert other.get("/api/v1/auth/setup").json() == {"needs_setup": False}
    again = other.post("/api/v1/auth/setup", {"full_name": "Intrus", "email": "x@ct.test", "password": STRONG})
    assert again.status_code == 409 and again.json()["code"] == "SETUP_DONE"
    assert User.objects.filter(is_platform_operator=True).count() == 1


def test_setup_is_closed_on_a_seeded_server(world):
    s = Session()
    assert s.get("/api/v1/auth/setup").json() == {"needs_setup": False}
    assert s.post("/api/v1/auth/setup", {"full_name": "X", "email": "x@ct.test", "password": STRONG}).status_code == 409


# ---------- Console : accès ----------


@pytest.mark.parametrize(
    "method,url",
    [
        ("get", "/api/v1/platform/organizations"),
        ("post", "/api/v1/platform/organizations"),
        ("get", "/api/v1/platform/access-requests"),
    ],
)
def test_console_is_closed_to_company_admins_and_anonymous(world, session, method, url):
    admin = session("admin@a.test")
    assert getattr(admin, method)(url).status_code == 403
    assert getattr(Session(), method)(url).status_code in (401, 403)


def test_operator_sees_no_company_data(world, operator):
    # La console gère les sociétés, jamais leurs dossiers ni leurs importateurs.
    assert operator.get("/api/v1/cases").status_code == 403
    assert operator.get("/api/v1/importers").status_code == 403
    assert operator.get("/api/v1/organization/members").status_code == 403


# ---------- Demandes d'ouverture ----------

REQUEST = {
    "company_name": "Logi Exemple",
    "primary_profile": "transit",
    "country_code": "cg",
    "registration_number": "RCCM 0012-B",
    "contact_name": "Contact Exemple",
    "contact_role": "Gérante",
    "contact_email": "Contact@Logi.test",
    "contact_phone": "+242 00 00 00",
}


def test_access_request_waits_for_operator_then_contact_becomes_admin(db, operator):
    public = Session()
    sent = public.post("/api/v1/auth/access-requests", REQUEST)
    assert sent.status_code == 201, sent.content
    assert sent.json() == {"received": True}
    request = AccessRequest.objects.get()
    assert request.status == "pending" and request.country_code == "CG"
    assert request.registration_number == "RCCM 0012-B"
    # Rien n'est ouvert avant l'accord.
    assert not Organization.objects.exists()

    listed = operator.get("/api/v1/platform/access-requests", status="pending").json()
    assert [r["company_name"] for r in listed] == ["Logi Exemple"]
    accepted = operator.post(f"/api/v1/platform/access-requests/{request.pk}/accept")
    assert accepted.status_code == 201, accepted.content
    token = accepted.json()["invitation"]["token"]
    org = Organization.objects.get()
    assert org.country_code == "CG" and org.business_profile.primary_profile == "transit"
    assert operator.post(f"/api/v1/platform/access-requests/{request.pk}/accept").status_code == 409

    contact = Session()
    lookup = contact.post("/api/v1/auth/invitations/lookup", {"token": token})
    assert lookup.status_code == 200
    assert lookup.json()["organization_name"] == "Logi Exemple"
    assert lookup.json()["existing_account"] is False
    joined = contact.post(
        "/api/v1/auth/invitations/accept", {"token": token, "full_name": "Contact", "password": STRONG}
    )
    assert joined.status_code == 200, joined.content
    assert joined.json()["memberships"][0]["roles"] == [Role.ORG_ADMIN]
    assert joined.json()["active_organization_id"] == str(org.pk)
    assert User.objects.get(email="contact@logi.test").check_password(STRONG)
    # Lien à usage unique.
    assert Session().post("/api/v1/auth/invitations/lookup", {"token": token}).status_code == 404


def test_access_request_rejects_closed_profiles_and_non_cemac_countries(db):
    s = Session()
    importer = s.post("/api/v1/auth/access-requests", {**REQUEST, "primary_profile": "importer"})
    assert importer.status_code == 400 and importer.json()["code"] == "PROFILE_NOT_OPEN"
    abroad = s.post("/api/v1/auth/access-requests", {**REQUEST, "country_code": "FR"})
    assert abroad.status_code == 400 and abroad.json()["code"] == "COUNTRY_NOT_CEMAC"
    assert not AccessRequest.objects.exists()


def test_refused_request_creates_nothing(db, operator):
    Session().post("/api/v1/auth/access-requests", REQUEST)
    request = AccessRequest.objects.get()
    refused = operator.post(f"/api/v1/platform/access-requests/{request.pk}/refuse", {"note": "RCCM illisible"})
    assert refused.status_code == 200 and refused.json()["status"] == "refused"
    assert not Organization.objects.exists()
    assert operator.post(f"/api/v1/platform/access-requests/{request.pk}/accept").status_code == 409


# ---------- Sociétés ----------


def test_operator_creates_suspends_and_reactivates_a_company(db, operator):
    created = operator.post("/api/v1/platform/organizations", ORG)
    assert created.status_code == 201, created.content
    token = created.json()["invitation"]["token"]
    row = operator.get("/api/v1/platform/organizations").json()[0]
    assert row["name"] == "Trans Exemple" and row["max_users"] == 3
    assert row["admin_invitation"]["status"] == "pending"
    assert "token" not in row["admin_invitation"]

    admin = Session()
    assert admin.post("/api/v1/auth/invitations/accept", {"token": token, "password": STRONG}).status_code == 200
    assert admin.get("/api/v1/organization/overview").status_code == 200
    org_id = row["id"]
    assert operator.post(f"/api/v1/platform/organizations/{org_id}/suspend").status_code == 200
    # Société suspendue : ses utilisateurs n'y entrent plus, ses données restent.
    assert admin.get("/api/v1/organization/overview").status_code == 403
    assert operator.post(f"/api/v1/platform/organizations/{org_id}/reactivate").status_code == 200
    assert Organization.objects.get(pk=org_id).active


def test_operator_renews_only_admin_invitations(db, operator, world):
    created = operator.post("/api/v1/platform/organizations", ORG).json()
    first = created["invitation"]
    renewed = operator.post(f"/api/v1/platform/invitations/{first['id']}/renew")
    assert renewed.status_code == 200 and renewed.json()["token"] != first["token"]
    assert Session().post("/api/v1/auth/invitations/lookup", {"token": first["token"]}).status_code == 404
    agent = Invitation.objects.create(
        organization=world["org_a"],
        email="agent@a.test",
        roles=[Role.DECLARANT],
        token_hash="x" * 64,
        expires_at=timezone.now() + timedelta(hours=1),
    )
    assert operator.post(f"/api/v1/platform/invitations/{agent.pk}/renew").status_code == 404


# ---------- Invitations de la société ----------


def _invite(s, **extra):
    return s.post("/api/v1/organization/invitations", {"email": "nouveau@a.test", "roles": ["declarant"], **extra})


def test_admin_invites_agent_who_sets_own_password(world, session):
    admin = session("admin@a.test")
    agency = admin.post("/api/v1/organization/agencies", {"name": "Libreville", "code": "lbv"}).json()
    sent = _invite(admin, full_name="Nouveau Agent", agency_id=agency["id"])
    assert sent.status_code == 201, sent.content
    assert sent.json()["agency_name"] == "Libreville"
    listed = admin.get("/api/v1/organization/invitations").json()
    assert [i["email"] for i in listed] == ["nouveau@a.test"]
    assert "token" not in listed[0]

    agent = Session()
    joined = agent.post("/api/v1/auth/invitations/accept", {"token": sent.json()["token"], "password": STRONG})
    assert joined.status_code == 200, joined.content
    membership = Membership.objects.get(user__email="nouveau@a.test")
    assert membership.roles == [Role.DECLARANT] and membership.agency.code == "LBV"
    assert agent.get("/api/v1/importers").status_code == 200
    assert AuditEvent.objects.filter(event_type="invitation.accepted", organization=world["org_a"]).exists()
    reused = Session().post("/api/v1/auth/invitations/lookup", {"token": sent.json()["token"]})
    assert reused.status_code == 404 and reused.json()["code"] == "INVITATION_INVALID"


def test_invitation_email_is_sent_only_when_configured_and_reachable(world, session, settings, mailoutbox):
    admin = session("admin@a.test")
    # Sans serveur SMTP : rien ne part, l'écran propose le lien à copier.
    assert _invite(admin).json()["email_status"] == "disabled"
    settings.INVITATION_EMAIL_ENABLED = True
    # Une adresse 127.0.0.1 n'ouvrirait que le PC de l'invité : pas d'envoi.
    settings.PUBLIC_APP_URL = "http://127.0.0.1:5173"
    assert _invite(admin).json()["email_status"] == "local_address"
    assert mailoutbox == []

    settings.PUBLIC_APP_URL = "https://clairtransit.example.test"
    sent = _invite(admin, full_name="Nouveau Agent")
    assert sent.json()["email_status"] == "sent"
    assert len(mailoutbox) == 1 and mailoutbox[0].to == ["nouveau@a.test"]
    assert f"https://clairtransit.example.test/#/activation/{sent.json()['token']}" in mailoutbox[0].body
    event = AuditEvent.objects.get(event_type="invitation.email_sent", organization=world["org_a"])
    assert sent.json()["token"] not in str(event.current or "")


def test_invitation_email_failure_keeps_the_link(world, session, settings, monkeypatch):
    settings.INVITATION_EMAIL_ENABLED = True
    settings.PUBLIC_APP_URL = "https://clairtransit.example.test"

    def refuse(*args, **kwargs):
        raise OSError("SMTP injoignable")

    monkeypatch.setattr("apps.onboarding.mail.send_mail", refuse)
    sent = _invite(session("admin@a.test"))
    assert sent.status_code == 201 and sent.json()["email_status"] == "failed" and sent.json()["token"]
    assert AuditEvent.objects.filter(event_type="invitation.email_failed").exists()


def test_invitation_of_a_suspended_company_is_refused(world, session):
    token = _invite(session("admin@a.test")).json()["token"]
    Organization.objects.filter(pk=world["org_a"].pk).update(active=False)
    refused = Session().post("/api/v1/auth/invitations/accept", {"token": token, "password": STRONG})
    assert refused.status_code == 404 and refused.json()["code"] == "INVITATION_INVALID"
    assert not User.objects.filter(email="nouveau@a.test").exists()


def test_existing_account_joins_with_its_own_password(world, session):
    admin_b = session("admin@b.test")
    token = admin_b.post(
        "/api/v1/organization/invitations", {"email": "declarant@a.test", "roles": ["validator"]}
    ).json()["token"]
    s = Session()
    assert s.post("/api/v1/auth/invitations/lookup", {"token": token}).json()["existing_account"] is True
    wrong = s.post("/api/v1/auth/invitations/accept", {"token": token, "password": STRONG})
    assert wrong.status_code == 400 and wrong.json()["code"] == "INVALID_CREDENTIALS"
    ok = s.post("/api/v1/auth/invitations/accept", {"token": token, "password": PASSWORD})
    assert ok.status_code == 200, ok.content
    assert len(ok.json()["memberships"]) == 2
    assert User.objects.get(email="declarant@a.test").check_password(PASSWORD)


def test_invitation_rules(world, session):
    admin = session("admin@a.test")
    assert _invite(admin, email="declarant@a.test").json()["code"] == "ALREADY_MEMBER"
    assert _invite(admin, roles=[]).status_code == 400
    assert _invite(admin, roles=["chef"]).json()["code"] == "UNKNOWN_ROLE"
    first = _invite(admin).json()
    second = _invite(admin).json()
    # La nouvelle invitation remplace l'ancienne pour la même adresse.
    assert Session().post("/api/v1/auth/invitations/lookup", {"token": first["token"]}).status_code == 404
    assert Session().post("/api/v1/auth/invitations/lookup", {"token": second["token"]}).status_code == 200
    revoked = admin.post(f"/api/v1/organization/invitations/{second['id']}/revoke")
    assert revoked.status_code == 200 and revoked.json()["status"] == "revoked"
    assert Session().post("/api/v1/auth/invitations/lookup", {"token": second["token"]}).status_code == 404

    expired = _invite(admin, email="tard@a.test").json()
    Invitation.objects.filter(pk=expired["id"]).update(expires_at=timezone.now() - timedelta(minutes=1))
    late = Session().post("/api/v1/auth/invitations/accept", {"token": expired["token"], "password": STRONG})
    assert late.status_code == 404 and late.json()["code"] == "INVITATION_INVALID"
    renewed = admin.post(f"/api/v1/organization/invitations/{expired['id']}/renew").json()
    assert Session().post("/api/v1/auth/invitations/lookup", {"token": renewed["token"]}).status_code == 200


def test_seat_limit_counts_members_and_pending_invitations(world, session):
    org = world["org_a"]
    org.max_users = Membership.objects.filter(organization=org, active=True).count() + 1
    org.save()
    admin = session("admin@a.test")
    assert _invite(admin).status_code == 201
    full = _invite(admin, email="encore@a.test")
    assert full.status_code == 409 and full.json()["code"] == "SEAT_LIMIT"


def test_company_admin_routes_are_isolated(world, session):
    admin_a = session("admin@a.test")
    admin_b = session("admin@b.test")
    invitation = _invite(admin_a).json()
    agency_a = admin_a.post("/api/v1/organization/agencies", {"name": "Libreville", "code": "LBV"}).json()
    member_a = Membership.objects.get(user__email="declarant@a.test")
    # Société B : 404 sans rien révéler de la société A.
    assert admin_b.post(f"/api/v1/organization/invitations/{invitation['id']}/revoke").status_code == 404
    assert admin_b.post(f"/api/v1/organization/invitations/{invitation['id']}/renew").status_code == 404
    assert admin_b.post(f"/api/v1/organization/members/{member_a.pk}/reactivate").status_code == 404
    assert admin_b.put(f"/api/v1/organization/members/{member_a.pk}/agency", {"agency_id": None}).status_code == 404
    assert _invite(admin_b, email="x@b.test", agency_id=agency_a["id"]).status_code == 404
    assert admin_b.get("/api/v1/organization/agencies").json() == []
    assert admin_b.get("/api/v1/organization/invitations").json() == []
    # Rôle insuffisant dans la société A.
    declarant = session("declarant@a.test")
    assert _invite(declarant).status_code == 403
    assert declarant.get("/api/v1/organization/invitations").status_code == 403
    assert declarant.post("/api/v1/organization/agencies", {"name": "X", "code": "X"}).status_code == 403
    assert declarant.get("/api/v1/organization/agencies").status_code == 200
    assert declarant.get("/api/v1/organization/overview").status_code == 403


def test_reactivate_and_move_member(world, session):
    admin = session("admin@a.test")
    member = Membership.objects.get(user__email="declarant@a.test")
    assert admin.post(f"/api/v1/organization/members/{member.pk}/deactivate").status_code == 200
    back = admin.post(f"/api/v1/organization/members/{member.pk}/reactivate")
    assert back.status_code == 200 and back.json()["active"] is True
    agency = Agency.objects.create(organization=world["org_a"], name="Port-Gentil", code="POG")
    moved = admin.put(f"/api/v1/organization/members/{member.pk}/agency", {"agency_id": str(agency.pk)})
    assert moved.status_code == 200 and moved.json()["agency_name"] == "Port-Gentil"
    duplicate = admin.post("/api/v1/organization/agencies", {"name": "Autre", "code": "pog"})
    assert duplicate.status_code == 409
    overview = admin.get("/api/v1/organization/overview").json()
    assert overview["agencies"] == 1 and overview["primary_profile"] == "transit"
