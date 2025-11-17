# Guide Technique - Système de Déclaration Douanière CEMAC

## Architecture de l'Application

### Vue d'ensemble

L'application suit une architecture modulaire composée de plusieurs couches :

```
┌─────────────────────────────────────┐
│     Interface Utilisateur (UI)      │
│        (Electron Renderer)          │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│      Contrôleur Principal           │
│       (renderer.js)                 │
└──────────────┬──────────────────────┘
               │
    ┌──────────┼──────────┐
    │          │          │
┌───▼───┐  ┌──▼───┐  ┌──▼─────┐
│Invoice│  │Trans-│  │Insur-  │
│Extract│  │port  │  │ance    │
│       │  │Extract│ │Extract │
└───┬───┘  └──┬───┘  └──┬─────┘
    │         │         │
    └─────────┼─────────┘
              │
         ┌────▼────┐
         │   Tax   │
         │Calculator│
         └────┬────┘
              │
       ┌──────▼─────────┐
       │  Declaration   │
       │   Generator    │
       └────────────────┘
```

## Modules Principaux

### 1. Invoice Extractor (`src/modules/invoice/extractor.js`)

**Responsabilité :** Extraction des données des factures commerciales

**Méthodes principales :**
- `extract(filePath, fileData)` - Extrait les données d'une facture
- `validate(data)` - Valide les données extraites
- `calculateFOB(data)` - Calcule la valeur FOB totale

**Format de sortie :**
```javascript
{
  numeroFacture: "FAC-2024-XXXX",
  dateFacture: "2024-01-15",
  fournisseur: { nom, adresse, telephone, email },
  destinataire: { nom, adresse, telephone, email },
  articles: [
    {
      description: "...",
      quantite: 50,
      prixUnitaire: 800000,
      montantTotal: 40000000,
      origine: "France",
      codeHS: "8471.30.00"
    }
  ],
  montantTotal: 55000000,
  devise: "XAF"
}
```

### 2. Transport Extractor (`src/modules/transport/extractor.js`)

**Responsabilité :** Extraction des données des factures de transport

**Méthodes principales :**
- `extract(filePath, fileData)` - Extrait les données de transport
- `calculateTotalCost(data)` - Calcule le coût total du transport

**Format de sortie :**
```javascript
{
  numeroConnaissement: "BL-2024-XXXX",
  transporteur: { nom, adresse, telephone },
  modeTransport: "MARITIME",
  portDepart: "Marseille, France",
  portArrivee: "Douala, Cameroun",
  montantTotal: 4500000,
  devise: "XAF"
}
```

### 3. Insurance Extractor (`src/modules/insurance/extractor.js`)

**Responsabilité :** Extraction des données des polices d'assurance

**Méthodes principales :**
- `extract(filePath, fileData)` - Extrait les données d'assurance
- `calculatePremium(valeurAssuree, tauxPrime)` - Calcule la prime

**Format de sortie :**
```javascript
{
  numeroPolice: "POL-2024-XXXX",
  assureur: { nom, adresse, telephone },
  typeAssurance: "TOUS_RISQUES",
  primeAssurance: 280000,
  devise: "XAF"
}
```

### 4. Tax Calculator (`src/modules/tax-calculator/calculator.js`)

**Responsabilité :** Calcul de tous les droits et taxes selon la réglementation CEMAC

**Méthodes principales :**
- `calculate(invoiceData, transportData, insuranceData)` - Calcule toutes les taxes
- `calculateDetailedByArticle(...)` - Calcul détaillé par article
- `determineCustomsDutyRate(invoiceData)` - Détermine le taux de DD applicable

**Taux appliqués :**
```javascript
{
  customsDuty: {
    category1: 0.05,   // 5% - Biens de première nécessité
    category2: 0.10,   // 10% - Biens intermédiaires
    category3: 0.20,   // 20% - Biens de consommation
    category4: 0.30    // 30% - Biens de luxe
  },
  vat: 0.1925,         // 19.25%
  tci: 0.01,           // 1%
  statisticalFee: 0.01 // 1%
}
```

**Formules de calcul :**
```
1. Valeur CIF = FOB + Fret + Assurance
2. Droits de Douane (DD) = CIF × Taux DD
3. Base TVA = CIF + DD
4. TVA = Base TVA × 19.25%
5. TCI = CIF × 1%
6. Redevance Statistique = CIF × 1%
7. Total = DD + TVA + TCI + Redevance Statistique
```

### 5. Declaration Generator (`src/utils/declarationGenerator.js`)

**Responsabilité :** Génération du document de déclaration douanière

**Méthodes principales :**
- `generate(invoiceData, transportData, insuranceData, taxData)` - Génère la déclaration
- `validate(declaration)` - Valide la déclaration avant export
- `export(declaration, format)` - Exporte en JSON, PDF ou XML

**Structure de la déclaration :**
```javascript
{
  declaration: { numero, dateCreation, type, regime, ... },
  importateur: { ... },
  exportateur: { ... },
  marchandises: [ ... ],
  transport: { ... },
  assurance: { ... },
  valorisation: { valeurFOB, fret, assurance, valeurCIF },
  liquidation: {
    droitsDeDouane: { base, taux, montant },
    tva: { base, taux, montant },
    tci: { base, taux, montant },
    redevanceStatistique: { base, taux, montant },
    totalAPayer: ...
  },
  documentsJoints: [ ... ],
  resume: { ... }
}
```

## Flux de Données

### 1. Import de Document

```
Utilisateur → Upload File
    ↓
IPC Main Process → Select File Dialog
    ↓
Renderer Process → Read File Data
    ↓
Extractor Module → Extract Data
    ↓
UI Update → Display Extracted Data
```

### 2. Calcul des Taxes

```
User Action → Click "Calculer"
    ↓
Validate Invoice Data
    ↓
Tax Calculator → Calculate CIF
    ↓
Tax Calculator → Calculate DD
    ↓
Tax Calculator → Calculate VAT
    ↓
Tax Calculator → Calculate TCI & Stats
    ↓
UI Update → Display Tax Breakdown
```

### 3. Génération de Déclaration

```
User Action → Click "Générer"
    ↓
Declaration Generator → Create Structure
    ↓
Validate Declaration
    ↓
Generate Preview
    ↓
Display in UI
```

### 4. Export

```
User Action → Click "Exporter"
    ↓
IPC Main Process → Save File Dialog
    ↓
File System → Write JSON/PDF
    ↓
Confirmation → Success/Error
```

## Classification HS et Taux de Droits

| Code HS | Catégorie | Taux DD | Description |
|---------|-----------|---------|-------------|
| 0101-2499 | 1 | 5% | Produits agricoles et alimentaires |
| 2500-3999 | 2 | 10% | Produits chimiques et matières premières |
| 4000-6999 | 2 | 10% | Matières plastiques, cuirs, bois |
| 7000-8299 | 2 | 10% | Métaux communs |
| 8300-8599 | 3 | 20% | Machines et équipements |
| 8600-8999 | 4 | 30% | Véhicules et transport |
| 9000-9799 | 3 | 20% | Instruments, meubles, jouets |

## Performance et Optimisation

### Mode Hors-ligne
- Tous les calculs sont effectués localement
- Aucun appel réseau requis
- Données stockées localement uniquement

### Gestion de la Mémoire
- Les fichiers sont chargés en mémoire temporairement
- Nettoyage automatique après export
- Pas de stockage permanent sauf export explicite

## Sécurité

### Données Sensibles
- Aucune donnée n'est envoyée vers des serveurs externes
- Les fichiers restent sur la machine locale
- Option d'export chiffrée (future version)

### Validation des Entrées
- Vérification des formats de fichiers
- Validation des montants et calculs
- Contrôle des champs obligatoires

## Extension Future

### Fonctionnalités Prévues
1. **OCR Réel** - Intégration de Tesseract.js pour l'extraction automatique
2. **Support Multi-Langues** - Français, Anglais
3. **Base de Données Locale** - Historique des déclarations
4. **Export PDF Avancé** - Génération de documents officiels
5. **Calcul par Article** - Détail des taxes par ligne de facture
6. **Mode Batch** - Traitement multiple de factures
7. **Signature Numérique** - Authentification des déclarations

### API Extensions

Pour étendre les extracteurs :

```javascript
class CustomExtractor extends BaseExtractor {
  async extract(filePath, fileData) {
    // Implémenter la logique d'extraction
    const data = await this.processFile(fileData);
    return this.validate(data);
  }
  
  validate(data) {
    // Implémenter la validation
    return super.validate(data);
  }
}
```

## Dépannage

### Problèmes Courants

1. **L'application ne démarre pas**
   - Vérifier que Node.js est installé
   - Exécuter `npm install` pour installer les dépendances

2. **Les fichiers ne se chargent pas**
   - Vérifier le format du fichier (PDF, JPG, PNG)
   - Vérifier les permissions de lecture

3. **Les calculs sont incorrects**
   - Vérifier que toutes les données sont présentes
   - Vérifier la classification HS des articles

## Conformité Réglementaire

L'application implémente les règlements suivants :
- Tarif Extérieur Commun CEMAC (TEC)
- Directive CEMAC sur la TVA
- Réglementation douanière CEMAC

**Note :** Cette application est un outil d'aide à la préparation. Les déclarations générées doivent être vérifiées avant soumission officielle.

---

**Version :** 1.0.0  
**Dernière mise à jour :** Janvier 2024
