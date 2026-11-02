# ruff: noqa: F811  (fixtures importées)
"""Fondations multi-métiers (MET-01 à MET-06, T103 à T106), sur des données fictives.

Le métier dit ce qu'une société fait ; seule une habilitation vérifiée, en vigueur et du pays de
la société ouvre la préparation d'une déclaration à une société qui n'est pas transitaire.
"""

from datetime import date, timedelta

from apps.audit.models import AuditEvent
from apps.organizations.business_models import CustomsHabilitation, OrganizationBusinessProfile
from apps.organizations.business_permissions import organization_capabilities
from apps.organizations.models import Organization
from tests.test_fin_de_vie import validated_case
from tests.test_fiscal import _private_storage, confirm, edition, schedule  # noqa: F401
from tests.test_onboarding import ORG, STRONG, _enroll, mfa_key, operator  # noqa: F401
from tests.test_validation import act

REASON = "Pièce vue en réunion (fictif)."


def _create(operator, **extra):
    resp = operator.post("/api/v1/platform/organizations", {**ORG, **extra})
    assert resp.status_code == 201, resp.content
    return Organization.objects.get(pk=resp.json()["organization_id"])


def _detail(operator, org):
    return operator.get(f"/api/v1/platform/organizations/{org.pk}").json()


def test_t103_four_families_open_with_secondary_activities(operator):
    expert = _create(operator, name="Cabinet fictif", primary_profile="expert", admin_email="a@cab.test")
    detail = _detail(operator, expert)
    assert detail["primary_profile"] == "expert"
    assert {"advisory", "audit"} <= set(detail["capabilities"])
    # Un conseil ne prépare jamais de déclaration par son seul métier.
    assert "declaration" not in detail["capabilities"] and detail["declaration_basis"] is None

    group = _create(
        operator,
        name="Groupe fictif",
        primary_profile="importer",
        secondary_profiles=["logistics", "importer", "logistics"],
        admin_email="a@grp.test",
    )
    detail = _detail(operator, group)
    assert detail["secondary_profiles"] == ["logistics"]  # sans doublon ni métier principal
    assert {"estimates", "transport", "agencies"} <= set(detail["capabilities"])
    assert "declaration" not in detail["capabilities"]

    v = detail["row_version"]
    short = operator.put(f"/api/v1/platform/organizations/{group.pk}/profiles",
                         {"secondary_profiles": ["transit"], "row_version": v, "reason": "x"})  # fmt: skip
    assert short.status_code == 400  # motif obligatoire
    resp = operator.put(f"/api/v1/platform/organizations/{group.pk}/profiles",
                        {"secondary_profiles": ["transit"], "row_version": v, "reason": REASON})  # fmt: skip
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["secondary_profiles"] == ["transit"]
    assert "declaration" in body["capabilities"] and body["declaration_basis"] == "profile"
    stale = operator.put(f"/api/v1/platform/organizations/{group.pk}/profiles",
                         {"secondary_profiles": [], "row_version": v, "reason": REASON})  # fmt: skip
    assert stale.status_code == 409
    assert AuditEvent.objects.filter(event_type="organization.profiles_changed", organization=group).count() == 1
    assert body["history"][0]["event_type"] == "organization.profiles_changed"


def test_t104_habilitation_opens_declaration_only_once_verified_in_force_and_local(operator, world, session):
    importer = _create(operator, name="Import fictif", primary_profile="importer", admin_email="a@imp.test")
    url = f"/api/v1/platform/organizations/{importer.pk}/habilitations"
    assert operator.post(url, {"kind": "own_account", "country_code": "GA", "reference": " "}).status_code == 400
    abroad = operator.post(url, {"kind": "own_account", "country_code": "CM", "reference": "CM-FIC-1"})
    assert abroad.status_code == 201
    resp = operator.post(url, {"kind": "own_account", "country_code": "GA", "reference": "  GA  FIC 7 ",
                               "valid_until": (date.today() + timedelta(days=30)).isoformat()})  # fmt: skip
    assert resp.status_code == 201, resp.content
    body = resp.json()
    assert "declaration" not in body["capabilities"]  # déclarée, pas encore vérifiée
    local = next(h for h in body["habilitations"] if h["country_code"] == "GA")
    assert local["reference"] == "GA FIC 7" and local["status"] == "declared"
    foreign = next(h for h in body["habilitations"] if h["country_code"] == "CM")

    decide = f"{url}/{foreign['id']}/verify"
    assert operator.post(decide, {"row_version": foreign["row_version"], "reason": REASON}).status_code == 200
    assert "declaration" not in organization_capabilities(importer)  # autre pays que la société

    decide = f"{url}/{local['id']}/verify"
    assert operator.post(decide, {"row_version": local["row_version"], "reason": "x"}).status_code == 400
    resp = operator.post(decide, {"row_version": local["row_version"], "reason": REASON})
    assert resp.status_code == 200, resp.content
    assert "declaration" in resp.json()["capabilities"] and resp.json()["declaration_basis"] == "habilitation"

    h = CustomsHabilitation.objects.get(pk=local["id"])
    assert "declaration" not in organization_capabilities(importer, day=date.today() + timedelta(days=31))
    resp = operator.post(f"{url}/{h.pk}/revoke", {"row_version": h.row_version, "reason": REASON})
    assert resp.status_code == 200
    assert "declaration" not in resp.json()["capabilities"]
    h.refresh_from_db()
    again = operator.post(f"{url}/{h.pk}/verify", {"row_version": h.row_version, "reason": REASON})
    assert again.status_code == 409 and again.json()["code"] == "HABILITATION_REVOKED"
    assert AuditEvent.objects.filter(event_type__startswith="habilitation.", organization=importer).count() == 5

    # Accès croisé : seuls l'exploitant écrit ; une société ne lit que les siennes.
    admin_b = session("admin@b.test")
    assert admin_b.get(url).status_code == 403
    assert admin_b.post(url, {"kind": "own_account", "country_code": "GA", "reference": "X"}).status_code == 403
    assert admin_b.post(f"{url}/{h.pk}/verify", {"row_version": 1, "reason": REASON}).status_code == 403
    other = _create(operator, name="Autre fictive", admin_email="a@autre.test")
    assert operator.post(f"/api/v1/platform/organizations/{other.pk}/habilitations/{h.pk}/verify",
                         {"row_version": h.row_version, "reason": REASON}).status_code == 404  # fmt: skip
    overview = admin_b.get("/api/v1/organization/overview").json()
    assert overview["habilitations"] == [] and overview["primary_profile"] == "transit"


def test_t105_me_exposes_profiles_and_capabilities(world, session):
    OrganizationBusinessProfile.objects.create(
        organization=world["org_b"], primary_profile="expert", secondary_profiles=["importer"]
    )
    me = session("multi@test.test").get("/api/v1/me").json()
    orgs = {m["organization"]["name"]: m["organization"] for m in me["memberships"]}
    assert orgs["Société A"]["profiles"] == ["transit"]
    assert "declaration" in orgs["Société A"]["capabilities"]
    assert orgs["Société B"]["profiles"] == ["expert", "importer"]
    assert "declaration" not in orgs["Société B"]["capabilities"]
    assert {"advisory", "estimates"} <= set(orgs["Société B"]["capabilities"])


def test_t106_without_habilitation_no_lodging_and_no_dau(world, schedule, edition, session):
    case, rev = validated_case(world, edition, session)
    OrganizationBusinessProfile.objects.create(organization=world["org_a"], primary_profile="importer")
    resp = act(case, "lodge", rev["row_version"], number="L 1", lodged_on="2026-11-02")
    assert resp.status_code == 403 and resp.json()["code"] == "CAPABILITY_REQUIRED"
    dau = case["s"].post(f"/api/v1/cases/{case['id']}/exports", {"format": "dau"})
    assert dau.status_code == 403 and dau.json()["details"] == {"capability": "declaration"}
    pdf = case["s"].post(f"/api/v1/cases/{case['id']}/exports", {"format": "pdf"})
    assert pdf.status_code == 201, pdf.content
    raw = b"".join(case["s"].get(f"/api/v1/cases/{case['id']}/exports/{pdf.json()['id']}/file").streaming_content)
    # Récapitulatif seul : le titre du PDF n'annonce pas un projet de déclaration.
    assert b"Projet de d" not in raw and raw.startswith(b"%PDF")
