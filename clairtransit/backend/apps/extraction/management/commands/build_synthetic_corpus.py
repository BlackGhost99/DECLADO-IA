from pathlib import Path

from django.core.management.base import BaseCommand

from apps.extraction import corpus


class Command(BaseCommand):
    help = "Écrit le corpus synthétique d'évaluation (jeux B à E) et ses valeurs attendues."

    def add_arguments(self, parser):
        parser.add_argument("directory")

    def handle(self, directory, **options):
        names = corpus.build(Path(directory))
        self.stdout.write(f"{len(names)} pièces fictives écrites dans {directory}.")
