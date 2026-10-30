from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.fiscal.importer import LayoutError, import_swd
from apps.fiscal.services import activate_schedule


class Command(BaseCommand):
    help = (
        "Importe le classeur « Tarif CEMAC 2022 SWD » : barème des taxes par code (activé pour le territoire) "
        "et édition du référentiel tarifaire en brouillon."
    )

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--label", default="Tarif CEMAC 2022 (SWD)")
        parser.add_argument("--title")
        parser.add_argument("--territory", default="GA")
        parser.add_argument("--publisher", default="")
        parser.add_argument("--note", default="")
        parser.add_argument("--no-activate", action="store_true", help="Ne pas activer le barème importé")

    def handle(self, *args, **opts):
        path = Path(opts["path"])
        if not path.is_file():
            raise CommandError(f"Fichier introuvable : {path}")
        try:
            schedule = import_swd(
                path,
                label=opts["label"],
                title=opts["title"] or path.name,
                territory=opts["territory"],
                publisher_claimed=opts["publisher"],
                provenance_note=opts["note"],
            )
        except LayoutError as exc:
            raise CommandError(str(exc)) from exc
        if not opts["no_activate"]:
            activate_schedule(schedule=schedule)
        state = "actif" if schedule.is_active else "non activé"
        self.stdout.write(self.style.SUCCESS(f"Barème {schedule.id} « {schedule.label} » ({state})"))
        self.stdout.write(f"Comptages : {schedule.counts}")
        issues = schedule.edition.import_run.counts.get("issues")
        self.stdout.write(f"Édition du référentiel {schedule.edition_id} (brouillon), anomalies : {issues}")
