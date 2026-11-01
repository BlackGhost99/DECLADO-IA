"""Preuve que ClamAV analyse réellement les fichiers, sur le PC où tourne ClairTransit.

Sans argument : demande sa version à clamd, puis lui envoie le fichier d'essai EICAR (inoffensif,
reconnu par tous les antivirus) et un contenu sain, par le même chemin que les dépôts. Le contrôle
échoue si EICAR n'est pas détecté ou si le contenu sain n'est pas confirmé.

Avec --fichier : analyse aussi des fichiers de ce PC (un tarif avant import, par exemple).

EICAR n'est jamais écrit sur le disque : il est reconstitué en mémoire, pour que l'antivirus du
poste (Windows Defender) ne supprime pas ce fichier source.
"""

import base64

from django.core.management.base import BaseCommand, CommandError

from apps.documents import antivirus

# Chaîne EICAR inversée puis encodée : ce fichier ne contient pas la signature en clair.
_EICAR_ENCODE = "KkgrSCQhRUxJRi1UU0VULVNVUklWSVROQS1EUkFETkFUUy1SQUNJRSR9NylDQzcpXlAoNDVYWlBcNFtQQUAlUCFPNVg="
_SAIN = b"ClairTransit - controle antivirus - contenu sain fictif.\n"


def eicar() -> bytes:
    return base64.b64decode(_EICAR_ENCODE)[::-1]


def _verdict(contenu: bytes) -> None:
    with antivirus.open_stream() as scanner:
        scanner.feed(contenu)
        scanner.verdict()


class Command(BaseCommand):
    help = "Vérifie que ClamAV répond, détecte le fichier d'essai EICAR et laisse passer un contenu sain."

    def add_arguments(self, parser):
        parser.add_argument("--fichier", action="append", default=[], help="Fichier de ce PC à analyser aussi")
        parser.add_argument("--seulement-fichiers", action="store_true", help="N'analyser que les fichiers donnés")

    def handle(self, *args, **opts):
        try:
            if not opts["seulement_fichiers"]:
                self.stdout.write(f"Antivirus      : {antivirus.version()}")
                try:
                    _verdict(eicar())
                except antivirus.MalwareDetected:
                    self.stdout.write("Essai EICAR    : détecté et refusé (attendu)")
                else:
                    raise CommandError("ClamAV n'a PAS détecté le fichier d'essai EICAR : signatures absentes ?")
                _verdict(_SAIN)
                self.stdout.write("Contenu sain   : accepté (attendu)")
            for chemin in opts["fichier"]:
                try:
                    antivirus.scan_file(chemin)
                except OSError as exc:
                    raise CommandError(f"Fichier illisible : {chemin} ({exc.strerror})") from None
                except antivirus.MalwareDetected:
                    raise CommandError(f"Fichier refusé par l'antivirus : {chemin}") from None
                self.stdout.write(f"Fichier sain   : {chemin}")
        except antivirus.MalwareDetected:
            raise CommandError("ClamAV a refusé le contenu sain : résultat incohérent.") from None
        except antivirus.ScanUnavailable as exc:
            raise CommandError(f"{exc} Rien n'est déposé tant qu'il ne répond pas.") from None
        self.stdout.write(self.style.SUCCESS("ClamAV analyse bien les fichiers."))
