from django.core.management.base import BaseCommand

from apps.tariffs.models import TariffEdition
from apps.tariffs.services import compare_editions


class Command(BaseCommand):
    help = "Compare les codes de deux éditions et enregistre chaque écart comme anomalie (REF-03)."

    def add_arguments(self, parser):
        parser.add_argument("reference_id")
        parser.add_argument("other_id")

    def handle(self, *args, **opts):
        a = TariffEdition.objects.get(pk=opts["reference_id"])
        b = TariffEdition.objects.get(pk=opts["other_id"])
        self.stdout.write(str(compare_editions(reference=a, other=b)))
