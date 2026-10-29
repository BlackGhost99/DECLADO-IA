from django.core.management.base import BaseCommand

from apps.fiscal.importer import is_swd_workbook


class Command(BaseCommand):
    help = "Affiche « oui » si le classeur a la disposition SWD (barème des taxes par code), sinon « non »."

    def add_arguments(self, parser):
        parser.add_argument("path")

    def handle(self, *args, **opts):
        self.stdout.write("oui" if is_swd_workbook(opts["path"]) else "non")
