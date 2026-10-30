# Lot 6 : exports du dossier et nouvelle révision après validation

Branche `check-complet`, partie du « check complet » de la nuit du 30/10/2026 (après les PR #42, #43 et #44).

## Fonctionnalités terminées

- **Exports PDF et Excel** (EXP-01 à EXP-03, T28, T29). Onglet Export : « Générer l'export » produit le récapitulatif PDF et le détail Excel de la révision courante et les télécharge ; chaque carte « Télécharger » produit l'un des deux.
  - Contenu : identification, marchandises et codes, valeur en douane, droits et taxes par taxe, total du compte 1, TCI au compte 2 hors total, RI « calculée par SYDONIA », sources (règles, version des taux, barème), empreinte du calcul, décisions.
  - Le calcul exporté est celui figé à la validation quand la révision est validée, le calcul du moment sinon.
  - Marquage : révision non validée, filigrane « BROUILLON » sur chaque page du PDF, bandeau en tête de chaque feuille Excel et nom de fichier `_brouillon`. Révision validée : « Validé en interne par … le … », avec la mention que ce n'est pas une acceptation par la Douane. Données fictives et simulation historique sont signalées.
  - Excel : codes et textes forcés en texte (les zéros de tête restent), une valeur commençant par `=`, `+`, `-` ou `@` reste un texte (préfixe de citation) ; montants en nombres. Onglets Marchandises, Taxes, Métadonnées.
  - Chaque export est conservé tel que généré (stockage privé, empreinte SHA-256, ajout seul) et journalisé (`revision.exported`). L'historique des exports liste toutes les révisions.
  - Le journal CSV du dossier neutralise lui aussi les cellules qui pourraient devenir des formules.
- **Nouvelle révision après validation** (WF-04, T27). Bouton « Créer une nouvelle révision » avec motif obligatoire sur un dossier validé (déclarant, validateur, administrateur).
  - La révision validée reste inchangée : décisions, calcul figé et exports consultables.
  - La nouvelle révision repart en brouillon avec les pièces (mêmes originaux), factures, lignes, codes relevés et marchandises. Un code validé sur des données identiques est repris avec son auteur et son motif, la reprise est tracée dans ses preuves. Les lectures et sources des pièces restent visibles par la lignée (`copied_from`).
  - Contrôles, soumission et validation se refont sur la nouvelle révision. Événement `revision.created`.
- **Étapes du dossier** (T76) : « Calcul » se coche quand un calcul complet a été soumis, « Export » quand un fichier a été généré. Plus de « à venir » figé.
- **Corrections** trouvées en parcourant un dossier de bout en bout :
  - `publish_tariff_edition` trouve un gestionnaire du référentiel même s'il n'est pas exploitant (le script Windows publiait le tarif en échec sur une base de démonstration).
  - Rattacher l'importateur : le nom lu est coupé avant l'adresse (« Alpha SA, BP 12 Libreville ») et comparé sans casse, accents ni ponctuation ; l'importateur correspondant est proposé d'office.
  - Récapitulatif du calcul : ligne « TCI (compte 2, hors total) » ; « Informations complémentaires » ne se chevauchent plus ; texte « frais … répartis sur les lignes » (ils le sont depuis le lot taxes).
  - Contraste du sous-titre dans les boutons principaux.

## Commandes

```
cd backend && ruff check . && ruff format --check . && python manage.py makemigrations --check --dry-run && python -m pytest
cd frontend && npm run typecheck && npm test && npm run build
```

Nouvelle dépendance : `reportlab==4.4.10` (PDF généré sur le serveur, sans service extérieur). Le script Windows l'installe avec `-MettreAJour`.

## Tests exécutés

- Backend : ruff, makemigrations --check, pytest (324 passés, dont `tests/test_exports.py` : T27, T28, T29, isolation entre sociétés).
- Frontend : typecheck, vitest (70 passés, dont `tests/Etapes.test.tsx` et la nouvelle révision dans `tests/Validation.test.tsx`), build.
- Parcours réel dans le navigateur sur une base de démonstration : soumission, validation, export PDF et Excel téléchargés, nouvelle révision.

## Limites

- Exports en français seulement (langue de la déclaration). Les libellés sont regroupés dans `apps/cases/exports.py` pour une autre langue de sortie ; l'arabe demandera une police et le sens de lecture adaptés.
- Le PDF utilise la police Vera fournie avec reportlab : une désignation en écriture non latine s'affichera mal.
- « Télécharger le dossier complet » (archive) et « Marquer comme exporté » restent désactivés ; le fichier pour SYDONIA attend la confirmation de son format.
- Nouvelle révision : les lectures IA en ligne et le graphe documentaire ne sont pas recopiés ; relire une pièce dans la nouvelle révision repart de la pièce.

## Prochaine étape

1. Confirmer en masse les codes reconnus (un motif pour toutes les marchandises).
2. Archive complète du dossier (pièces, exports, journal) et format SYDONIA quand il sera confirmé.
