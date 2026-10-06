import json
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.extraction import evaluation


class Command(BaseCommand):
    help = "Mesure l'extraction sur un corpus annoté (<nom>.expected.json) ; aucune donnée n'est enregistrée."

    def add_arguments(self, parser):
        parser.add_argument("directory")
        parser.add_argument("--json", dest="json_path", help="Écrit aussi le rapport détaillé en JSON.")

    def handle(self, directory, json_path=None, **options):
        report = evaluation.evaluate_corpus(Path(directory))
        if json_path:
            Path(json_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(evaluation.markdown(report))
