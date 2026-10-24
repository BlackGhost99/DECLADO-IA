# Étape 8 — Règles fiscales territorialisées (phase 1)

Le noyau `tax_engine.py` reste un calculateur mathématique, non une décision réglementaire.

## Implémenté
- Modèle Django `FiscalRule` et migration `tariffs/0002_fiscal_rules.py`
- Pays, régime, code tarifaire, début/fin de validité, assiette, taux et référence légale
- Traçabilité du vérificateur, de la date et de la publication
- Filtrage des règles uniquement pour le contexte exact (pays, régime, code, date)
- Refus sans taux publié et refus de doublons contradictoires
- Tests avec des valeurs *fictives*, non légales

## Non achevé
- Vérification juridique et workflow de publication à double contrôle
- Exhaustivité des droits/taxes du territoire et régime (une règle publiée ne prouve pas l'exhaustivité)
- Correspondance effective du tarif, exemptions, accords, origine, contingent, taux spécifiques
- Valeur en douane CIF et conversion vérifiée par taux officiel à date
- Snapshot immuable et empreinte documentaire, scellé sur une révision de dossier
- Raccordement à la prévalidation finale (reste volontairement bloquée)

Aucun taux officiel n'est livré ou présumé. Le champ `published` ne doit être activé
que par une procédure réglementaire contrôlée ; il ne constitue pas une preuve
juridique à lui seul. Ne pas utiliser pour des déclarations réelles.

## Contrôle qualité
```bash
cd backend
ruff check .
ruff format --check .
python manage.py makemigrations --check --dry-run
python manage.py migrate
python -m pytest tests/test_tax_engine.py tests/test_fiscal_applicability.py
```
