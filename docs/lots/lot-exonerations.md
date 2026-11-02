# Lot « Exonérations » (TAX-04, T23, T94 à T96)

Demande du 2 novembre 2026 : développer le module suivant après la supervision, c'est-à-dire les exonérations. Aucun texte officiel d'exonération n'a encore été fourni. Le module livre donc le cadre, sans aucune exonération préremplie.

## Fonctionnalités terminées

- **Référentiel › Exonérations**, réservé à l'admin ClairTransit pour l'écriture et en lecture pour les sociétés. On y déclare :
  - la référence textuelle (code additionnel, convention…) et le libellé ;
  - les taxes visées, avec le taux appliqué à la place du barème (0 = exonération totale) ;
  - le champ d'application : débuts de codes SH, régimes douaniers et période ;
  - les justificatifs exigés et les conditions ;
  - le texte source avec sa référence (obligatoire sauf « Décision de l'exploitant », alors marquée « Sans texte officiel ») et un motif.
- Une exonération n'est jamais réécrite : on la désactive avec un motif, puis on en déclare une nouvelle. Tout passe par `record_event`.
- **Dossier › Calculs › Exonérations** :
  - l'agent demande une exonération, choisit les articles (aucun = tous), coche les pièces justificatives du dossier et saisit le n° du justificatif ;
  - un validateur ou un administrateur de la société valide le justificatif (refusé sans pièce jointe), le refuse avec un motif, ou l'agent retire la demande.
- **Calcul** :
  - une demande en attente n'est pas appliquée : le calcul est provisoire et la soumission est bloquée (point bloquant « exemption ») ;
  - une demande validée applique le taux de l'exonération aux taxes visées, article par article, seulement si le code confirmé, le régime (article ou dossier) et la date du calcul sont dans le champ ;
  - hors champ, rien n'est appliqué et la raison est affichée ;
  - chaque taxe exonérée garde le taux du barème remplacé, la référence de l'exonération, son texte et le n° du justificatif ;
  - le calcul figé à la validation interne les conserve.
- Nouvelle révision (WF-04) : les demandes suivent avec leur décision, leurs pièces et leurs articles copiés.
- Textes en FR, EN, ES et AR.

## Limites

- Aucune exonération réelle n'est saisie : il faut les textes officiels (codes additionnels, régimes privilégiés, conventions, Charte des investissements, etc.).
- Une exonération vise les taxes calculées par article. La redevance informatique est calculée par SYDONIA et n'est pas concernée.
- Si deux exonérations validées visent la même taxe, la plus favorable s'applique et est affichée ; aucun cumul n'est calculé.

## Exports (2 novembre 2026, T100)

- L'annexe du PDF (export DAU compris) comporte un tableau « Exonérations appliquées » : la référence et le texte de chaque exonération, les taxes avec le taux du barème remplacé, les lignes concernées et le n° du justificatif.
- L'Excel comporte une feuille « Exonérations appliquées » avec les mêmes informations.
- Le dépôt en douane déclaré par l'agent (n°, date, mention « non vérifié ») apparaît dans l'identification et dans les métadonnées.
- Les cases douanières du formulaire DAU restent vides : seule la Douane les remplit.

## Commandes

```
cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest
cd frontend && npm run typecheck && npm test && npm run build
```

## Tests exécutés

- `tests/test_exonerations.py` couvre :
  - T94 : déclaration réservée, champs obligatoires, désactivation, journal ;
  - T23 : demande en attente non appliquée et soumission bloquée ; justificatif exigé, puis validation par le validateur ; DDI et TVA à 0 avec le taux du barème rappelé ; soumission possible ;
  - T95 : hors champ, non appliquée avec sa raison ;
  - T96 : refus motivé, retrait, isolation entre sociétés.
- `frontend/tests/Exemptions.test.tsx` : liste avec la mention « Sans texte officiel », puis validation d'un justificatif par un validateur.

## Prochaine étape

Saisir les vraies exonérations dès réception des textes.
