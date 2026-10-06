"""Jeu de démonstration A : deux sociétés fictives et leurs utilisateurs.

Données entièrement synthétiques, marquées is_demo. Refusé hors mode DEBUG.
Le mot de passe de démonstration n'est pas un secret : il ne doit jamais servir ailleurs.
"""

import os
from decimal import Decimal

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
    # Gestionnaire du référentiel : permission distincte, sans accès métier aux sociétés.
    ("referentiel@demo.demo", "Gestionnaire du référentiel", {}),
]
REFERENCE_MANAGERS = {"referentiel@demo.demo"}

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
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    full_name=full_name,
                    is_reference_manager=email in REFERENCE_MANAGERS,
                )
            for key, roles in affiliations.items():
                Membership.objects.update_or_create(
                    organization=orgs[key], user=user, defaults={"roles": list(roles), "active": True}
                )

        for key, items in IMPORTERS.items():
            for name, identifiers in items:
                Importer.objects.get_or_create(organization=orgs[key], name=name, defaults={"identifiers": identifiers})

        self._demo_case(orgs["alpha"])
        self.stdout.write(self.style.SUCCESS("Jeu de démonstration prêt (données fictives)."))
        for email, _, affiliations in USERS:
            detail = ", ".join(f"{ORGS[k]}: {'/'.join(r.value for r in v)}" for k, v in affiliations.items())
            detail = detail or "gestionnaire du référentiel (aucune société)"
            self.stdout.write(f"  {email:28} {detail}")
        self.stdout.write(f"Mot de passe commun : {password}")

    def _demo_case(self, org):
        """Dossier fictif d'Alpha : facture PDF synthétique, une ligne avec code douanier et référence article."""
        from django.core.files.uploadedfile import SimpleUploadedFile

        from apps.cases import services as cases
        from apps.cases.models import CustomsCase
        from apps.documents.synthetic import make_pdf
        from apps.tariffs.models import PublicationState, TariffEdition

        title = "Dossier de démonstration (fictif)"
        if CustomsCase.objects.for_organization(org).filter(title=title).exists():
            return
        actor = User.objects.get(email="declarant@alpha.demo")
        edition = (
            TariffEdition.objects.filter(publication_state=PublicationState.CONSULTATION).order_by("created_at").first()
        )
        case = cases.create_case(
            org=org,
            actor=actor,
            data={
                "title": title,
                "importer_id": Importer.objects.for_organization(org).first().id,
                "regime": "C100 (fictif)",
                "target_edition_id": edition.id if edition else None,
            },
        )
        revision = case.current_revision
        pdf = make_pdf(
            [
                "FACTURE FICTIVE - DEMONSTRATION CLAIRTRANSIT",
                "Fournisseur : Haras Fictif SARL   Facture n. DEMO-001   Devise : EUR",
                "Ref. article 12345678   Chevaux reproducteurs fictifs   HS Code 0101.10.00",
                "Quantite 2 NMB   Prix unitaire 1 500,00   Montant 3 000,00   Origine FR",
                "Total facture : 3 000,00 EUR",
            ]
        )
        link, _created = cases.attach_upload(
            org=org,
            actor=actor,
            revision=revision,
            upload=SimpleUploadedFile("facture-demo-001.pdf", pdf, content_type="application/pdf"),
            usage="invoice",
            duplicate_action="keep_both",
        )
        invoice = cases.add_invoice(
            org=org,
            actor=actor,
            revision_id=revision.id,
            data={
                "supplier_name": "Haras Fictif SARL",
                "invoice_number": "DEMO-001",
                "currency": "EUR",
                "declared_total": Decimal("3000"),
                "document_id": link.id,
            },
        )
        line = cases.add_invoice_line(
            org=org,
            actor=actor,
            invoice_id=invoice.id,
            data={
                "description_raw": "Chevaux reproducteurs fictifs",
                "source_reference": "12345678",
                "customs_code": "0101.10.00",
                "customs_code_label": "HS Code",
                "quantity": Decimal("2"),
                "unit": "NMB",
                "unit_price": Decimal("1500"),
                "amount": Decimal("3000"),
                "origin_country": "FR",
                "evidence_document_id": link.id,
                "evidence_page": 1,
            },
        )
        cases.create_goods_line(org=org, actor=actor, revision_id=revision.id, data={"invoice_line_ids": [line.id]})
