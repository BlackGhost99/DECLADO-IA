# Guide de Démarrage Rapide

## Installation Rapide

1. **Cloner le projet**
```bash
git clone https://github.com/BlackGhost99/D-clarations-des-droits-de-douanes-en-zone-CEMAC.git
cd D-clarations-des-droits-de-douanes-en-zone-CEMAC
```

2. **Installer les dépendances**
```bash
npm install
```

3. **Lancer l'application**
```bash
npm start
```

## Première Utilisation

### Étape 1: Charger une facture commerciale (obligatoire)
1. Cliquez sur le bouton "📤 Charger la Facture"
2. Sélectionnez votre fichier (PDF, JPG ou PNG)
3. Les données seront extraites automatiquement

### Étape 2: Charger les documents optionnels
- **Facture de transport**: Cliquez sur "📤 Charger Transport"
- **Facture d'assurance**: Cliquez sur "📤 Charger Assurance"

### Étape 3: Calculer les taxes
1. Cliquez sur "🧮 Calculer les Taxes"
2. L'application calculera automatiquement:
   - La valeur CIF
   - Les droits de douane
   - La TVA (19.25%)
   - La TCI (1%)
   - La redevance statistique (1%)

### Étape 4: Générer la déclaration
1. Cliquez sur "📑 Générer la Déclaration"
2. Consultez l'aperçu de votre déclaration

### Étape 5: Exporter
1. Cliquez sur "💾 Exporter le Dossier"
2. Choisissez l'emplacement de sauvegarde
3. Votre dossier complet est prêt!

## Exemple de Calcul

Pour une importation de **55 000 000 XAF** (FOB):
- Ajoutez le fret: **4 500 000 XAF**
- Ajoutez l'assurance: **280 000 XAF**
- **Valeur CIF = 59 780 000 XAF**

Taxes calculées:
- Droits de Douane (20%): **11 956 000 XAF**
- TVA (19.25%): **13 809 180 XAF**
- TCI (1%): **597 800 XAF**
- Redevance Statistique (1%): **597 800 XAF**

**Total à payer: 26 960 780 XAF**

## Fonctionnement Hors-Ligne

✅ L'application fonctionne **100% hors-ligne**
- Aucune connexion internet requise
- Toutes vos données restent sur votre ordinateur
- Aucune donnée n'est envoyée vers des serveurs externes

## Support

Pour toute question:
- Consultez le [GUIDE_UTILISATEUR.md](GUIDE_UTILISATEUR.md)
- Consultez le [GUIDE_TECHNIQUE.md](GUIDE_TECHNIQUE.md) pour les développeurs
- Ouvrez une issue sur GitHub

## Construction de l'Exécutable

Pour créer une application standalone:

```bash
# Windows
npm run build:win

# macOS
npm run build:mac

# Linux
npm run build:linux
```

L'exécutable sera dans le dossier `dist/`.

---

**Bon usage!** 🚀
