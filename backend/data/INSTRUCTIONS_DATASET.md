# Comment créer le dataset CEMAC manuellement

## Méthode 1 : Copier-Coller depuis le PDF (le plus simple)

1. **Ouvrez** le PDF `tarif-des-douanes-de-la-cemac-version-originale-pdf-210608020644.pdf`

2. **Sélectionnez et copiez** des sections avec le format :
   ```
   0901    Café, même torréfié ou décaféiné; coques et pellicules de café
   0902    Thé, même aromatisé
   6109    T-shirts, maillots de corps et articles similaires, en bonneterie
   ```

3. **Collez dans Excel ou LibreOffice Calc** :
   - Colonne A : Code HS (4 chiffres)
   - Colonne B : Description

4. **Nettoyez** :
   - Supprimez les lignes vides
   - Gardez seulement les codes à 4 chiffres (positions tarifaires principales)
   - Vérifiez qu'il n'y a pas de caractères bizarres

5. **Enregistrez** comme `hs_cemac_manual.csv` avec :
   - En-têtes : `hs_code,text`
   - Encodage : UTF-8
   - Séparateur : virgule

6. **Placez le fichier** dans : `backend/data/hs_cemac_manual.csv`

## Méthode 2 : Conversion PDF → Excel en ligne

1. Utilisez un service en ligne :
   - https://www.ilovepdf.com/fr/pdf_en_excel
   - https://smallpdf.com/fr/pdf-en-excel
   - Ou https://www.adobe.com/acrobat/online/pdf-to-excel.html

2. **Téléchargez** le PDF, convertissez en Excel

3. **Nettoyez** le résultat :
   - Gardez seulement 2 colonnes : Code HS et Description
   - Supprimez les en-têtes de page, numéros de page, etc.

4. **Enregistrez** comme CSV (UTF-8)

## Méthode 3 : Extraction assistée par OCR (si le PDF est scanné)

Si le texte ne se sélectionne pas dans le PDF :
1. Utilisez un OCR en ligne : https://www.onlineocr.net/
2. Convertissez page par page ou par lots
3. Consolidez dans Excel

## Format final attendu

Le CSV doit ressembler à ça :

```csv
hs_code,text
0101,Chevaux, ânes, mulets et bardots, vivants
0102,Bovins vivants
0103,Porcins vivants
0104,Ovins et caprins vivants
0201,Viandes de l'espèce bovine, fraîches ou réfrigérées
0901,Café, même torréfié ou décaféiné; coques et pellicules de café
6109,T-shirts, maillots de corps et articles similaires, en bonneterie
```

## Ensuite : Entraîner le modèle

Une fois le CSV prêt, lancez :

```powershell
cd C:\Users\BlackGhost\Desktop\DECLADO-IA\backend
C:\Users\BlackGhost\Desktop\DECLADO-IA\.venv\Scripts\python.exe scripts\retrain_hs_classifier.py --csv data\hs_cemac_manual.csv --out models\hs_classifier.joblib
```

## Conseils

- **Commencez petit** : 50-100 codes les plus courants pour tester
- **Qualité > Quantité** : Mieux vaut 200 codes bien nettoyés que 2000 codes bruités
- **Codes à 4 chiffres** : Ce sont les positions tarifaires principales, idéales pour la classification initiale
- **Descriptions complètes** : Plus la description est précise, meilleure sera la classification

## Besoin d'aide ?

Si vous voulez que je regarde le PDF et vous aide à identifier les pages à extraire en priorité, partagez-moi quelques captures d'écran ou pages extraites.
