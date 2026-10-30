from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.core.exceptions import ApiError
from apps.tariffs.models import PublicationState, TariffEdition
from apps.tariffs.services import publish_edition


class Command(BaseCommand):
    help = (
        "Publie une édition tarifaire en brouillon, au nom d'un gestionnaire du référentiel. "
        "Par défaut en consultation : visible dans la recherche, jamais utilisée pour un calcul."
    )

    def add_arguments(self, parser):
        parser.add_argument("--label", required=True, help="Libellé de l'édition, tel que donné à l'import")
        parser.add_argument(
            "--actor",
            help="E-mail du gestionnaire (par défaut : un exploitant gestionnaire, sinon tout gestionnaire)",
        )
        parser.add_argument(
            "--mode",
            choices=[PublicationState.CONSULTATION, PublicationState.OPERATIONAL],
            default=PublicationState.CONSULTATION,
        )
        parser.add_argument(
            "--check-actor", action="store_true", help="Vérifie seulement qu'un gestionnaire existe, sans rien publier"
        )

    def handle(self, *args, **opts):
        managers = User.objects.filter(is_reference_manager=True, is_active=True)
        actor = (
            managers.filter(email=opts["actor"].lower()).first()
            if opts["actor"]
            else (
                managers.filter(is_platform_operator=True).order_by("created_at").first()
                or managers.order_by("created_at").first()
            )
        )
        if actor is None:
            raise CommandError("Aucun gestionnaire du référentiel : terminez d'abord la mise en service.")
        if opts["check_actor"]:
            return
        edition = (
            TariffEdition.objects.filter(label=opts["label"], publication_state=PublicationState.DRAFT)
            .order_by("-created_at")
            .first()
        )
        if edition is None:
            raise CommandError(f"Aucune édition en brouillon nommée « {opts['label']} ».")
        try:
            edition = publish_edition(edition=edition, actor=actor, mode=opts["mode"])
        except ApiError as exc:
            raise CommandError(str(exc.detail)) from exc
        state = edition.get_publication_state_display()
        self.stdout.write(self.style.SUCCESS(f"Édition « {edition.label} » publiée ({state})."))
