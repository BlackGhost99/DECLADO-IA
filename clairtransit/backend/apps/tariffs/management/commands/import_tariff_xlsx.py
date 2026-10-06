from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.tariffs.importers.xlsx import import_xlsx


class Command(BaseCommand):
    help = "Importe un classeur tarifaire .xlsx original (formules et caches conservés) en brouillon."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--label", required=True)
        parser.add_argument("--title")
        parser.add_argument("--sheet", help="Feuille à importer (par défaut la première)")
        parser.add_argument("--publisher", default="")
        parser.add_argument("--note", default="")
        parser.add_argument("--code-length", type=int, default=8)

    def handle(self, *args, **opts):
        path = Path(opts["path"])
        if not path.is_file():
            raise CommandError(f"Fichier introuvable : {path}")
        edition = import_xlsx(
            path,
            edition_label=opts["label"],
            title=opts["title"] or path.name,
            sheet=opts["sheet"],
            code_length=opts["code_length"],
            publisher_claimed=opts["publisher"],
            provenance_note=opts["note"],
        )
        run = edition.import_run
        self.stdout.write(self.style.SUCCESS(f"Édition {edition.id} « {edition.label} » : {run.get_status_display()}"))
        self.stdout.write(f"Comptages : {run.counts}")
