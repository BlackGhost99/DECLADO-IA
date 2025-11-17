# Phase 7 - Interface utilisateur complète (Desktop UI)

## Statut: ✅ Terminé (composants principaux)

## Architecture implémentée

### Structure modulaire React + TypeScript

```
frontend/src/
├── types/
│   └── index.ts                    # Définitions TypeScript complètes
├── hooks/
│   ├── useLocalStorage.ts          # Persistence localStorage (offline-first)
│   └── useFileImport.ts            # Drag-drop file picker
├── components/
│   ├── Sidebar.tsx + .css          # Gestion projets (collapsible)
│   ├── DocumentList.tsx + .css     # Liste documents avec status badges
│   ├── FileDropZone.tsx + .css     # Zone drag-drop upload
│   └── DetailsPanel.tsx + .css     # Panneau détails avec 4 onglets
├── layouts/
│   └── MainLayout.tsx + .css       # Orchestrateur principal
└── App.tsx                          # Point d'entrée (intégration complète)
```

## Fonctionnalités

### 1. Workflow automatisé (MainLayout)

**Pipeline auto-processing** (exécutable sans erreur par opérateur):
1. Upload fichier (PDF/image) via drag-drop ou bouton
2. **OCR** → POST `/api/ocr/process` (Tesseract eng+fra)
3. **Classification HS** → POST `/api/hs/suggest` (extraction auto description)
4. **Calcul douanier** → POST `/api/customs/calculate` (extraction auto montants)
5. Mise à jour status: `pending` → `processing` → `completed`/`error`

### 2. Gestion projets (Sidebar)

- Création/suppression projets
- Sidebar collapsible (280px ↔ 60px)
- Badge nombre documents par projet
- Sélection projet active
- **Persistence**: localStorage (`declado_projects`)

### 3. Liste documents (DocumentList)

- Status badges colorés:
  - 🟠 Pending (orange)
  - 🔵 Processing (bleu)
  - 🟢 Completed (vert)
  - 🔴 Error (rouge)
- Ajout/suppression documents
- Empty state avec bouton d'ajout

### 4. Panneau détails (DetailsPanel)

**4 onglets**:

#### OCR
- Pages traitées, source, CER
- Champs normalisés (dates, montants, devises)

#### Classification HS
- Liste codes HS avec confidence %
- Description complète pour chaque code

#### Calcul douanier
- Conversion Incoterms (FOB → CIF)
- Ventilation taxes (DD, VAT, autres)
- Liste documents requis (5 premiers)
- Totaux (DD, TVA, montant total)

#### Export
- **Formulaire métadonnées eSAD** (6 champs):
  - Numéro déclaration
  - Nom déclarant
  - Exportateur
  - Importateur
  - Bureau douane
  - Date déclaration
- **4 boutons export** (colorés):
  - 🔴 PDF (dossier A4 complet)
  - 🟢 XML eSAD (bien formé, structure Header/Parties/Goods/Taxes/Documents)
  - 🔵 CSV (ligne unique, 15 colonnes)
  - 🟠 JSON (pretty print)
- Désactivé si pas de calcul

### 5. Drag-drop (FileDropZone)

- Support clavier (Enter/Space pour ouvrir picker)
- Filtrage extensions (.pdf, .png, .jpg, .jpeg, .tif, .tiff)
- Feedback visuel (border, background, scale transform)

## Persistence & Offline

**useLocalStorage hook**:
- Stockage: `localStorage['declado_projects']`
- CRUD projets/documents
- Auto-génération IDs: `proj_${timestamp}_${random}`
- Serialization JSON automatique

## Types TypeScript

Toutes les structures backend typées:
- `BackendHealth`, `OCRResult` (OCRPage, OCRWord, NormalizedFields)
- `HSClassification`, `CustomsCalculation` (IncotermsConversion, TaxBreakdown, AuditLog)
- `InvoiceDocument` (status enum), `Project`, `ExportRequest`, `ExportMeta`

## CSS

Chaque composant a son CSS isolé:
- `Sidebar.css`: Flexbox, transitions collapse, hover states
- `DocumentList.css`: Status colors, overflow handling
- `FileDropZone.css`: Dashed border, drag feedback (scale)
- `DetailsPanel.css`: Tab navigation, form grids, export button colors
- `MainLayout.css`: Layout principal (sidebar | list | content-area), spinner animation

## Tests & Validation

### Lint
- ✅ Toutes les erreurs TypeScript/ESLint résolues
- ✅ Imports propres (pas d'imports inutilisés)
- ✅ Pas de `any` types (sauf catch blocks acceptable)
- ✅ HTML apostrophes échappées (`&apos;`)

### Export backend (Phase 6)
- ✅ 4/4 tests passing
- ✅ PDF bytes>1000
- ✅ XML parseable (eSAD root + DeclarationNumber)
- ✅ CSV headers présents
- ✅ JSON structure correcte

## Intégration App.tsx

**Nouveau flow**:
1. Initialisation backend URL (Electron API ou fallback http://127.0.0.1:8000)
2. Health check automatique
3. États loading/error avec UI dédiée
4. **Rendu MainLayout** avec backendUrl si opérationnel

## Prochaines étapes (optionnel)

### PDF viewer avec overlay OCR
- Installer react-pdf ou PDF.js
- Afficher bounding boxes des mots OCR
- Navigation pages (arrows, +/- zoom)

### Accessibilité complète
- ARIA labels complets
- Audit contraste WCAG AA (4.5:1)
- Test navigation clavier complète
- Dark theme (CSS variables + toggle + persistence)
- Support zoom système (125%, 150%, 200%)

## Tests end-to-end suggérés

1. **Démarrer backend**: `cd backend; .\venv\Scripts\python.exe -m uvicorn app.main:app --reload`
2. **Démarrer frontend**: `cd frontend; npm run electron:dev`
3. **Workflow complet**:
   - Créer projet
   - Upload fichier PDF/image
   - Vérifier auto-processing (OCR → HS → Customs)
   - Vérifier onglets DetailsPanel remplis
   - Tester export (PDF, XML, CSV, JSON)
   - Rafraîchir app → vérifier persistence localStorage

## Notes techniques

- **Auto-processing**: Extraction intelligente description (vendor field ou premiers 200 chars)
- **Auto-calculation**: Extraction montants/devises, defaults (HS=6109, qty=1, incoterm=CIF, origin=CN, dest=CM)
- **Error handling**: Try-catch à chaque étape, status 'error' + message stocké
- **Performance**: Batch processing avec indicateur visuel (spinner + bouton annulation)
- **UX**: Welcome screen avec quick-start (3 étapes)

## Fichiers modifiés

### Nouveaux
- `frontend/src/types/index.ts`
- `frontend/src/hooks/useLocalStorage.ts`
- `frontend/src/hooks/useFileImport.ts`
- `frontend/src/components/Sidebar.tsx + .css`
- `frontend/src/components/DocumentList.tsx + .css`
- `frontend/src/components/FileDropZone.tsx + .css`
- `frontend/src/components/DetailsPanel.tsx + .css`
- `frontend/src/layouts/MainLayout.tsx + .css`

### Modifiés
- `frontend/src/App.tsx` (simplifié: uniquement init + health check + rendu MainLayout)

## Compatibilité

- React 18.2.0
- TypeScript 5.3.3
- Electron 28.1.4
- Backend FastAPI (endpoints `/api/ocr/process`, `/api/hs/suggest`, `/api/customs/calculate`, `/api/export`)
