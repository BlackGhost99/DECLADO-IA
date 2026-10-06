# Instructions pour les assistants

- Spécifications : `docs/specifications/` (cahier des charges, conception, plan et recette). Les exigences sont numérotées (ACC-01…) et les tests de recette aussi (T01…) : référencez-les.
- Un lot à la fois ; compte rendu dans `docs/lots/lot-N.md` (fonctionnalités terminées, commandes, tests exécutés, limites, prochaine étape).
- Tout modèle propre à une société hérite d'`apps.core.models.OrganizationOwnedModel` et se lit via `objects.for_organization(request.organization)`. Ajouter un test d'accès croisé pour chaque nouvel endpoint.
- Les transitions et modifications passent par des services (`services.py`) qui journalisent via `apps.audit.services.record_event`.
- Codes douaniers et références en texte, jamais en entier ; montants en Decimal.
- Vérifications : `cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest` ; `cd frontend && npm run typecheck && npm test && npm run build`.
- Interface et messages en français.
