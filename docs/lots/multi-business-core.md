# ClairTransit — Socle multi-métiers

Branche d'implémentation : `feature/multi-business-core`.

Quatre profils sont modélisés sans dédoubler le moteur douanier :
transit, importer, logistics, expert.

Les organisations historiques conservent le profil transit via migration.
Les agences sont isolées par organisation.

Le contrôle `has_feature` **ne remplace jamais** les permissions de rôles,
les vérifications d'accès aux dossiers ou les exigences réglementaires.

`workflow_service.transition_revision` ne permet que les changements d'état
préparatoires. La validation interne finale reste réservée au futur lot de
validation, avec vérification documentaire et séparation des fonctions.

Avant fusion :
```bash
cd backend
ruff check .
ruff format --check .
python manage.py makemigrations --check --dry-run
python manage.py migrate
python -m pytest
```

Ne pas mettre ce lot en production avant ces vérifications et une revue des
permissions de chaque API.
