from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.tariffs.importers.pdf_text import import_pdf_text


class Command(BaseCommand):
    help = "Importe le texte extrait d'un PDF tarifaire comme édition en brouillon (copie dérivée)."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--label", required=True)
        parser.add_argument("--title")
        parser.add_argument("--publisher", default="")
        parser.add_argument("--note", default="")
        parser.add_argument("--hs-version", default="")

    def handle(self, *args, **opts):
        path = Path(opts["path"])
        if not path.is_file():
            raise CommandError(f"Fichier introuvable : {path}")
        edition = import_pdf_text(
            path,
            edition_label=opts["label"],
            title=opts["title"] or path.name,
            publisher_claimed=opts["publisher"],
            provenance_note=opts["note"],
            hs_version=opts["hs_version"],
        )
        run = edition.import_run
        self.stdout.write(self.style.SUCCESS(f"Édition {edition.id} « {edition.label} » : {run.get_status_display()}"))
        self.stdout.write(f"Comptages : {run.counts}")
        self.stdout.write(f"Couverture : {run.coverage}")
