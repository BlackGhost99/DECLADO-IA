"""ACC-01 : authentification par session, CSRF, sélection de la société active."""

from tests.conftest import PASSWORD, Session


def test_health_is_public(db, session):
    resp = session().get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_unauthenticated_access_is_401_with_structured_error(world, session):
    resp = session().get("/api/v1/importers")
    assert resp.status_code == 401
    body = resp.json()
    assert body["code"] == "NOT_AUTHENTICATED"
    assert body["request_id"] and body["request_id"] == resp["X-Request-ID"]


def test_login_requires_csrf_token(world):
    s = Session()
    resp = s.client.post("/api/v1/auth/login", {"email": "declarant@a.test", "password": PASSWORD}, format="json")
    assert resp.status_code == 403


def test_login_sets_httponly_session_and_autoselects_single_org(world, session):
    s = session()
    resp = s.login("declarant@a.test")
    assert resp.status_code == 200
    cookie = s.client.cookies["sessionid"]
    assert cookie["httponly"]
    body = resp.json()
    assert body["active_organization_id"] == str(world["org_a"].id)
    assert [m["roles"] for m in body["memberships"]] == [["declarant"]]


def test_wrong_password_and_unknown_user_give_same_error(world, session):
    s = session()
    bad = s.login("declarant@a.test", "wrong-password")
    unknown = s.login("nobody@a.test", "wrong-password")
    assert bad.status_code == unknown.status_code == 400
    assert bad.json()["code"] == unknown.json()["code"] == "INVALID_CREDENTIALS"


def test_mutations_require_csrf_once_logged_in(world, session):
    s = session("declarant@a.test")
    resp = s.client.post("/api/v1/importers", {"name": "Sans CSRF"}, format="json")
    assert resp.status_code == 403


def test_multi_org_user_must_choose_then_can_switch(world, session):
    s = session("multi@test.test")
    assert s.get("/api/v1/me").json()["active_organization_id"] is None
    resp = s.get("/api/v1/importers")
    assert resp.status_code == 403
    assert resp.json()["code"] == "NO_ACTIVE_ORGANIZATION"

    s.post("/api/v1/me/active-organization", {"organization_id": str(world["org_a"].id)})
    assert [i["name"] for i in s.get("/api/v1/importers").json()["results"]] == ["Importateur A"]

    s.post("/api/v1/me/active-organization", {"organization_id": str(world["org_b"].id)})
    assert [i["name"] for i in s.get("/api/v1/importers").json()["results"]] == ["Importateur B"]


def test_logout_ends_session(world, session):
    s = session("declarant@a.test")
    assert s.post("/api/v1/auth/logout").status_code == 204
    assert s.get("/api/v1/me").status_code == 401
