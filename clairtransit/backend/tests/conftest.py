"""Jeu A de la recette : sociétés A et B, déclarant/validateur/admin, données différentes."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.clients.models import Importer
from apps.organizations.models import Membership, Organization, Role

PASSWORD = "test-password-not-secret-42"


class Session:
    """Client API qui passe par le vrai parcours : cookie CSRF, connexion, en-tête X-CSRFToken."""

    def __init__(self):
        self.client = APIClient(enforce_csrf_checks=True)

    def csrf(self) -> str:
        self.client.get("/api/v1/auth/csrf")
        return self.client.cookies["csrftoken"].value

    def login(self, email, password=PASSWORD):
        return self.post("/api/v1/auth/login", {"email": email, "password": password})

    def _headers(self, extra=None):
        headers = {"HTTP_X_CSRFTOKEN": self.csrf()}
        headers.update(extra or {})
        return headers

    def get(self, url, **params):
        return self.client.get(url, params)

    def post(self, url, data=None, **headers):
        return self.client.post(url, data or {}, format="json", **self._headers(headers))

    def upload(self, url, data, **headers):
        return self.client.post(url, data, format="multipart", **self._headers(headers))

    def put(self, url, data=None, **headers):
        return self.client.put(url, data or {}, format="json", **self._headers(headers))

    def patch(self, url, data=None, **headers):
        return self.client.patch(url, data or {}, format="json", **self._headers(headers))

    def delete(self, url, **headers):
        return self.client.delete(url, **self._headers(headers))


def _user(email, org, roles):
    user = User.objects.create_user(email=email, password=PASSWORD, full_name=email.split("@")[0])
    Membership.objects.create(organization=org, user=user, roles=roles)
    return user


@pytest.fixture
def world(db):
    org_a = Organization.objects.create(name="Société A")
    org_b = Organization.objects.create(name="Société B")
    users = {
        "a_declarant": _user("declarant@a.test", org_a, [Role.DECLARANT]),
        "a_validator": _user("validateur@a.test", org_a, [Role.VALIDATOR]),
        "a_admin": _user("admin@a.test", org_a, [Role.ORG_ADMIN]),
        "b_declarant": _user("declarant@b.test", org_b, [Role.DECLARANT]),
        "b_admin": _user("admin@b.test", org_b, [Role.ORG_ADMIN]),
    }
    multi = User.objects.create_user(email="multi@test.test", password=PASSWORD)
    Membership.objects.create(organization=org_a, user=multi, roles=[Role.DECLARANT])
    Membership.objects.create(organization=org_b, user=multi, roles=[Role.DECLARANT])
    users["multi"] = multi
    importer_a = Importer.objects.create(organization=org_a, name="Importateur A", identifiers={"nif": "A-1"})
    importer_b = Importer.objects.create(organization=org_b, name="Importateur B", identifiers={"nif": "B-1"})
    return {"org_a": org_a, "org_b": org_b, "users": users, "importer_a": importer_a, "importer_b": importer_b}


@pytest.fixture
def session():
    def make(email=None):
        s = Session()
        if email:
            resp = s.login(email)
            assert resp.status_code == 200, resp.content
        return s

    return make


@pytest.fixture(autouse=True)
def _fast_password_hasher(settings):
    # Accélère les tests uniquement ; la production garde les hachages par défaut de Django.
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
