# ClairTransit — détection documentaire FR/EN/ES/AR (prototype lexical V1)

## Intégration

Le module `apps.extraction.language` analyse les lignes de texte produites par les lecteurs PDF, OCR et Excel. Les résultats sont ajoutés à `ParsedDocument.stats.language_detection`, puis aux métadonnées du `Document` après fusion.

La détection est volontairement conservatrice : `locale=""` indique inconnu/ambigu. Les scores représentent des occurrences lexicales, **pas** une probabilité calibrée. Des documents mixtes, à libellés très courts, ou dont le texte OCR est défectueux peuvent être indéterminés. L'original, les positions et les décisions humaines ne sont pas modifiés.

## OCR

Tesseract utilise `fra+eng+spa+ara` par défaut si les packs sont installés (l'adaptateur existant sélectionne les langues disponibles et peut fonctionner avec un sous-ensemble). Installer les données de langues adaptées à l'image conteneur : `tesseract-ocr-fra`, `tesseract-ocr-eng`, `tesseract-ocr-spa`, `tesseract-ocr-ara`. Vérifier avec `tesseract --list-langs`.

**Limitation :** sélectionner toutes les langues installées ne constitue pas une sélection automatique optimale par page. Les documents mixtes et les colonnes RTL exigent encore des essais ciblés, notamment pour l'arabe. Le détecteur fonctionne *après* lecture OCR, pas avant.

## Tests avant fusion

```bash
cd backend
python manage.py makemigrations --check --dry-run
python -m pytest tests/test_language_detection.py
python -m pytest
ruff check .
ruff format --check .
```

## Étapes suivantes

1. Capturer les langues par page/zone avec scores robustes et validation humaine.
2. Évaluer OCR multilingue sur factures anonymisées et tests de non-régression.
3. Publier les métadonnées via l'API documentaire et les afficher dans l'interface.
4. Conserver toute traduction en couche distincte du référentiel officiel.
