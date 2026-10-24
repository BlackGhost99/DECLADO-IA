# Référentiel documentaire réglementaire — Phase initiale

Branche : `feature/document-regulatory-referential`.

## Principes
- Le catalogue des documents est distinct des pièces réellement déposées dans `documents.Document`.
- `DocumentRequirement` est global : aucun administrateur de société ne peut le désactiver.
- `CompanyDocumentPolicy` ajoute des exigences propres à une société ; son champ `active` ne concerne que la politique interne.
- Aucun texte ni article juridique n'est automatiquement activé par les commandes de démarrage.
- Le moteur refuse les paramètres inconnus ou le contexte incomplet ; son résultat est une liste d'exigences, et non une attestation de conformité.
- Toute future API doit restreindre `CompanyDocumentPolicy.organization` à la société active vérifiée côté serveur.
- Les évaluations devront être historisées et la liaison `revision.organization == evaluation.organization` imposée dans le service.

## Installation

```bash
cd backend
python manage.py makemigrations regulations
python manage.py migrate
python manage.py seed_document_types
python manage.py seed_regulatory_sources
python -m pytest tests/test_regulatory_engine.py
```

## Limites volontaires de cette étape
La migration Django n'est pas encore commitée, les endpoints ne sont pas exposés, aucun traitement documentaire réel n'est lancé et aucun droit réglementaire n'est activé en production. Faire une revue réglementaire et technique avant publication.
