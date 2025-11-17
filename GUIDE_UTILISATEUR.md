# Déclarations des Droits de Douanes - Zone CEMAC

## 📋 Description

Application desktop professionnelle fonctionnant entièrement **hors-ligne** pour automatiser la déclaration des droits de douanes dans la zone CEMAC (Communauté Économique et Monétaire de l'Afrique Centrale).

### 🎯 Fonctionnalités Principales

- ✅ **Extraction automatique de données** depuis les factures commerciales (obligatoire)
- ✅ **Support des factures de transport** (optionnel)
- ✅ **Support des factures d'assurance** (optionnel)
- ✅ **Import via scanner ou upload** de fichiers (PDF, JPG, PNG)
- ✅ **Calcul automatique des taxes** selon la réglementation CEMAC
- ✅ **Génération de déclarations douanières** complètes
- ✅ **Fonctionnement 100% hors-ligne** - aucune connexion internet requise
- ✅ **Réduction des erreurs humaines** grâce aux calculs automatisés

## 🏛️ Taxes Calculées (Réglementation CEMAC)

L'application calcule automatiquement :

1. **Valeur CIF** (Cost, Insurance, Freight) = FOB + Fret + Assurance
2. **Droits de Douane (DD)** - Taux variable selon le tarif douanier (5%, 10%, 20%, 30%)
3. **TVA** - 19.25% sur (Valeur CIF + DD)
4. **Taxe Communautaire d'Intégration (TCI)** - 1% sur la valeur CIF
5. **Redevance Statistique** - 1% sur la valeur CIF

## 🚀 Installation

### Prérequis

- Node.js 18+ et npm
- Système d'exploitation : Windows, macOS ou Linux

### Installation des dépendances

```bash
npm install
```

## 💻 Utilisation

### Lancement en mode développement

```bash
npm start
```

ou

```bash
npm run dev
```

### Construction de l'application

```bash
# Pour Windows
npm run build:win

# Pour macOS
npm run build:mac

# Pour Linux
npm run build:linux

# Pour toutes les plateformes
npm run build
```

L'application compilée se trouvera dans le dossier `dist/`.

## 📖 Guide d'utilisation

1. **Importer les documents**
   - Cliquez sur "Charger la Facture" pour importer votre facture commerciale (obligatoire)
   - Optionnel : Importez la facture de transport et/ou d'assurance
   - Formats supportés : PDF, JPG, PNG

2. **Vérifier les données extraites**
   - Les données sont extraites automatiquement et affichées dans la section "Données Extraites"
   - Vérifiez que les informations sont correctes

3. **Calculer les taxes**
   - Cliquez sur "Calculer les Taxes"
   - Le système calcule automatiquement tous les droits et taxes applicables

4. **Générer la déclaration**
   - Cliquez sur "Générer la Déclaration"
   - Consultez l'aperçu de la déclaration générée

5. **Exporter le dossier**
   - Cliquez sur "Exporter le Dossier"
   - Choisissez l'emplacement de sauvegarde
   - Le dossier complet est prêt pour le dépôt aux douanes

## 🏗️ Structure du Projet

```
.
├── src/
│   ├── main/
│   │   └── main.js              # Point d'entrée Electron
│   ├── renderer/
│   │   └── index.html           # Interface utilisateur
│   ├── modules/
│   │   ├── invoice/
│   │   │   └── extractor.js     # Extraction factures commerciales
│   │   ├── transport/
│   │   │   └── extractor.js     # Extraction factures transport
│   │   ├── insurance/
│   │   │   └── extractor.js     # Extraction factures assurance
│   │   └── tax-calculator/
│   │       └── calculator.js    # Calcul des taxes CEMAC
│   └── utils/
│       └── declarationGenerator.js  # Génération déclarations
├── public/
│   └── assets/
│       ├── css/
│       │   └── styles.css       # Styles de l'application
│       └── js/
│           └── renderer.js      # Logique interface utilisateur
├── templates/                   # Modèles de déclarations
├── samples/                     # Exemples de documents
└── README.md
```

## 🔧 Technologies Utilisées

- **Electron** - Framework desktop multiplateforme
- **Node.js** - Runtime JavaScript
- **HTML/CSS/JavaScript** - Interface utilisateur
- **Modules personnalisés** - Extraction et calcul des taxes

## 📊 Exemple de Calcul

Pour une importation avec :
- Valeur FOB : 55 000 000 XAF
- Fret : 4 500 000 XAF
- Assurance : 280 000 XAF

**Calculs :**
- Valeur CIF : 59 780 000 XAF
- Droits de Douane (20%) : 11 956 000 XAF
- TVA (19.25%) : 13 814 035 XAF
- TCI (1%) : 597 800 XAF
- Redevance Statistique (1%) : 597 800 XAF
- **Total à payer : 26 965 635 XAF**

## 🌍 Zone CEMAC

L'application est conçue pour la Communauté Économique et Monétaire de l'Afrique Centrale (CEMAC) qui comprend :

- 🇨🇲 Cameroun
- 🇨🇫 République Centrafricaine
- 🇨🇬 République du Congo
- 🇬🇦 Gabon
- 🇬🇶 Guinée Équatoriale
- 🇹🇩 Tchad

## 🔒 Sécurité et Confidentialité

- ✅ Toutes les données restent sur votre ordinateur
- ✅ Aucune connexion internet requise
- ✅ Aucune donnée n'est envoyée vers des serveurs externes
- ✅ Contrôle total sur vos documents et déclarations

## 📝 Licence

MIT License - Voir le fichier LICENSE pour plus de détails

## 👨‍💻 Auteur

BlackGhost99

## 🤝 Contribution

Les contributions sont les bienvenues ! N'hésitez pas à ouvrir une issue ou soumettre une pull request.

## 📞 Support

Pour toute question ou problème, veuillez ouvrir une issue sur le dépôt GitHub.

---

**Version 1.0.0** - Application 100% hors-ligne pour la déclaration des droits de douanes en zone CEMAC
