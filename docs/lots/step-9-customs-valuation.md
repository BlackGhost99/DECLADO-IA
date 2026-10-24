# Étape 9 — Valeur en douane, conversion et répartition : noyau arithmétique

Fonctions disponibles :
- `convert` : conversion monétaire à taux daté, sourcé et vérifié par le client
- `distribute` : répartition proportionnelle déterministe à sommes conservées
- `valuation_preview` : addition explicite marchandises + fret + assurance + ajustements

**Limites de sécurité et conformité :**
- L'identification du taux BEAC ou autre source officielle applicable reste à intégrer.
- Une attestation booléenne de taux `verified` n'est PAS une validation de source légale.
- L'ajout fret/assurance n'est pas systématiquement applicable à toutes les opérations.
- Les Incoterms, la valeur transactionnelle, les exonérations, les frais d'achat, les décotes,
  les taux officiels datés et les règles nationales doivent être vérifiés séparément.
- Il reste à relier les lignes de facture et justificatifs documentaires, publier les taux
  de conversion, persister un snapshot et contrôler les mises à jour.
- La validation finale reste bloquée ; ces fonctions servent à des simulations de test,
  pas à l'établissement d'une déclaration douanière réelle.

Tests : `cd backend && python -m pytest tests/test_customs_valuation.py`.
