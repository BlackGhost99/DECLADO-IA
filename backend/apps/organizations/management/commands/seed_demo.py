"""Jeu de démonstration A : deux sociétés fictives et leurs utilisateurs.

Données entièrement synthétiques, marquées is_demo. Refusé hors mode DEBUG.
Le mot de passe de démonstration n'est pas un secret : il ne doit jamais servir ailleurs.
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.clients.models import Importer
from apps.organizations.models import Membership, Organization, Role

DEFAULT_DEMO_PASSWORD = "demo-ClairTransit-2026"

ORGS = {
    "alpha": "Transit Alpha (démo)",
    "beta": "Transit Bêta (démo)",
}

USERS = [
    # email, nom, {société: rôles}
    ("declarant@alpha.demo", "Déclarant Alpha", {"alpha": [Role.DECLARANT]}),
    ("validateur@alpha.demo", "Validateur Alpha", {"alpha": [Role.VALIDATOR]}),
    ("admin@alpha.demo", "Admin Alpha", {"alpha": [Role.ORG_ADMIN]}),
    ("declarant@beta.demo", "Déclarant Bêta", {"beta": [Role.DECLARANT]}),
    ("validateur@beta.demo", "Validateur Bêta", {"beta": [Role.VALIDATOR]}),
    ("admin@beta.demo", "Admin Bêta", {"beta": [Role.ORG_ADMIN, Role.DECLARANT]}),
    ("multi@demo.demo", "Agent multi-sociétés", {"alpha": [Role.DECLARANT], "beta": [Role.DECLARANT]}),
]

IMPORTERS = {
    "alpha": [("Société Fictive Import Alpha", {"nif": "DEMO-A-0001"})],
    "beta": [("Comptoir Fictif Bêta", {"nif": "DEMO-B-0001"})],
}


class Command(BaseCommand):
    help = "Crée les sociétés et comptes de démonstration (développement uniquement)."

    def add_arguments(self, parser):
        parser.add_argument("--password", help="Mot de passe des comptes de démonstration.")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo est réservé au développement (DJANGO_DEBUG=true).")
        password = options["password"] or os.environ.get("DEMO_PASSWORD") or DEFAULT_DEMO_PASSWORD

        orgs = {}
        for key, name in ORGS.items():
            orgs[key], _ = Organization.objects.get_or_create(name=name, defaults={"is_demo": True})

        for email, full_name, affiliations in USERS:
            user = User.objects.filter(email=email).first()
            if user is None:
                user = User.objects.create_user(email=email, password=password, full_name=full_name)
            for key, roles in affiliations.items():
                Membership.objects.update_or_create(
                    organization=orgs[key], user=user, defaults={"roles": list(roles), "active": True}
                )

        for key, items in IMPORTERS.items():
            for name, identifiers in items:
                Importer.objects.get_or_create(organization=orgs[key], name=name, defaults={"identifiers": identifiers})

        self.stdout.write(self.style.SUCCESS("Jeu de démonstration prêt (données fictives)."))
        for email, _, affiliations in USERS:
            detail = ", ".join(f"{ORGS[k]}: {'/'.join(r.value for r in v)}" for k, v in affiliations.items())
            self.stdout.write(f"  {email:28} {detail}")
        self.stdout.write(f"Mot de passe commun : {password}")
