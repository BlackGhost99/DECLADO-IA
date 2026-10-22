from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.tariffs.importers.csv_export import import_csv


class Command(BaseCommand):
    help = "Importe un export CSV de classeur tarifaire comme édition en brouillon (copie dérivée)."

    def add_arguments(self, parser):
        parser.add_argument("path")
        parser.add_argument("--label", required=True, help="Nom de l'édition, ex. « Tarif intitulé 2016 (CSV) »")
        parser.add_argument("--title", help="Titre de la source")
        parser.add_argument("--publisher", default="", help="Éditeur annoncé (non vérifié)")
        parser.add_argument("--note", default="", help="Provenance déclarée")
        parser.add_argument("--code-length", type=int, default=8)

    def handle(self, *args, **opts):
        path = Path(opts["path"])
        if not path.is_file():
            raise CommandError(f"Fichier introuvable : {path}")
        edition = import_csv(
            path,
            edition_label=opts["label"],
            title=opts["title"] or path.name,
            code_length=opts["code_length"],
            publisher_claimed=opts["publisher"],
            provenance_note=opts["note"],
        )
        run = edition.import_run
        self.stdout.write(self.style.SUCCESS(f"Édition {edition.id} « {edition.label} » : {run.get_status_display()}"))
        self.stdout.write(f"Comptages : {run.counts}")
