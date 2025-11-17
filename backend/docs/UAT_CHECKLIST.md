# UAT Checklist - DECLADO-IA
**Phase 10: Tests, QA et Performance**

## 📋 User Acceptance Testing - Scenarios Réels

### Informations Générales
- **Date de test**: _____________
- **Testeur**: _____________
- **Rôle**: [ ] Opérateur  [ ] Superviseur  [ ] Admin
- **Version**: 0.1.0
- **Environnement**: [ ] Dev  [ ] Staging  [ ] Production

---

## 🎯 Scénario 1: Traitement Facture PDF Simple

### Objectif
Vérifier qu'un opérateur peut traiter une facture PDF standard de bout en bout.

### Étapes
1. [ ] **Connexion** (si auth activée)
   - Se connecter avec compte opérateur
   - Interface s'affiche correctement

2. [ ] **Upload Facture**
   - Cliquer "Upload PDF"
   - Sélectionner facture test: `test_invoice_simple.pdf`
   - Fichier se charge (barre de progression visible)
   - Confirmation d'upload apparaît

3. [ ] **OCR Automatique**
   - Texte extrait automatiquement
   - Affichage aperçu texte extracté
   - Pas d'erreur visible
   - Temps traitement < 10 secondes

4. [ ] **Vérification Extraction**
   - Numéro facture: _______________
   - Fournisseur: _______________
   - Montant total: _______________
   - Devise: _______________
   - [ ] Données correctes (comparer avec PDF original)

5. [ ] **Classification HS Automatique**
   - Système suggère codes HS pour chaque ligne produit
   - Au moins 3 suggestions par produit
   - Score de confiance affiché (0-100%)
   - [ ] Code suggéré pertinent

6. [ ] **Validation/Modification HS**
   - Accepter code suggéré OU
   - Chercher manuellement autre code
   - Code final enregistré: _______________

7. [ ] **Calcul Douanier**
   - Cliquer "Calculer Droits"
   - Résultat s'affiche en < 2 secondes
   - Affichage:
     - Valeur CIF: _______________
     - Droits de douane (DD): _______________
     - TVA: _______________
     - Total taxes: _______________
   - [ ] Montants cohérents

8. [ ] **Export PDF**
   - Cliquer "Exporter PDF"
   - PDF généré et téléchargé
   - Ouvrir PDF exporté
   - [ ] Contient toutes infos (facture, calculs, taxes)
   - [ ] Format professionnel

### Résultat
- [ ] **PASS** - Tous les critères satisfaits
- [ ] **FAIL** - Problèmes rencontrés (détailler ci-dessous)

**Commentaires**:
```


```

**Temps total**: ___ minutes

---

## 🎯 Scénario 2: Traitement Facture Complexe (Multi-pages, Tableaux)

### Objectif
Tester robustesse sur factures complexes avec tableaux multi-colonnes.

### Étapes
1. [ ] Upload facture complexe: `test_invoice_complex.pdf`
2. [ ] OCR extrait toutes les pages (3+ pages)
3. [ ] Tableaux détectés et extraits correctement
4. [ ] Produits multiples (10+ lignes) tous capturés
5. [ ] Classification HS batch pour toutes lignes
6. [ ] Calculs agrégés corrects (somme totale DD + TVA)
7. [ ] Export CSV avec toutes lignes

### Critères Acceptation
- [ ] Extraction >90% précise (vérifier 10 lignes aléatoires)
- [ ] Aucune ligne produit manquante
- [ ] Calculs justes (vérifier 3 lignes manuellement)
- [ ] Export CSV importable dans Excel sans erreur

### Résultat
- [ ] **PASS**
- [ ] **FAIL**

**Problèmes identifiés**:
```


```

---

## 🎯 Scénario 3: Workflow Superviseur - Validation & Audit

### Objectif
Tester fonctionnalités superviseur (validation, historique, rapports).

### Étapes
1. [ ] **Connexion Superviseur**
   - Login avec compte superviseur
   - Interface admin visible

2. [ ] **Tableau de Bord**
   - Voir statistiques journalières:
     - Factures traitées: ___
     - Montant total déclaré: ___
     - Erreurs: ___
   - [ ] Données cohérentes

3. [ ] **Validation Déclarations**
   - Ouvrir liste "Déclarations en attente"
   - Sélectionner déclaration opérateur
   - Vérifier détails calculs
   - [ ] Approuver OU [ ] Rejeter avec commentaire

4. [ ] **Historique & Recherche**
   - Chercher facture par numéro: _______________
   - Filtrer par date: du ___ au ___
   - Filtrer par montant: > ___ FCFA
   - [ ] Résultats corrects

5. [ ] **Audit Log**
   - Ouvrir journal d'audit
   - Vérifier dernières actions utilisateurs
   - [ ] Logs horodatés et complets

6. [ ] **Export Rapports**
   - Générer rapport mensuel (PDF)
   - Télécharger rapport CSV (toutes déclarations)
   - [ ] Données exhaustives

### Résultat
- [ ] **PASS**
- [ ] **FAIL**

**Commentaires**:
```


```

---

## 🎯 Scénario 4: Gestion Cas d'Exception

### Objectif
Vérifier gestion erreurs et cas limites.

### Test Cases

#### 4.1 Facture Illisible (Qualité Image Faible)
- [ ] Upload image floue: `test_invoice_lowquality.png`
- [ ] Système affiche warning "Qualité image faible"
- [ ] OCR fonctionne (même si imprécis)
- [ ] Opérateur peut corriger manuellement

#### 4.2 Code HS Inconnu/Invalide
- [ ] Saisir code HS inexistant: "9999.99.99"
- [ ] Système alerte "Code non trouvé dans nomenclature"
- [ ] Calcul utilise taux par défaut (20% DD, 19.25% TVA)

#### 4.3 Produits Exonérés (Médicaments)
- [ ] Saisir produit médical HS 3004
- [ ] Cocher "Exonération médicale"
- [ ] Calcul applique DD=0%, TVA réduite ou 0%
- [ ] Export mentionne exonération

#### 4.4 Multi-Devises (Conversion)
- [ ] Facture en USD: ___ USD
- [ ] Facture en EUR: ___ EUR
- [ ] Système convertit automatiquement vers FCFA
- [ ] Taux de change affiché: 1 USD = ___ FCFA
- [ ] Montants cohérents

#### 4.5 Fichier Corrompu
- [ ] Upload fichier non-PDF: `test.exe`
- [ ] Système rejette avec message clair
- [ ] Pas de crash application

### Résultat Global
- [ ] **PASS** (≥4/5 tests passés)
- [ ] **FAIL**

---

## 🎯 Scénario 5: Performance & Charge

### Objectif
Vérifier performances sous charge réaliste.

### Tests

#### 5.1 Latence Interface
- [ ] Page se charge en < 3 secondes
- [ ] Upload facture réactif (feedback immédiat)
- [ ] Calculs affichés en < 2 secondes

#### 5.2 Batch Processing
- [ ] Importer CSV 50 lignes
- [ ] Traitement automatique lancé
- [ ] Temps total: ___ secondes
- [ ] Cible: < 5 minutes (soit ~6 sec/ligne)
- [ ] **PASS** si < 5 min

#### 5.3 Utilisation Ressources
- [ ] CPU usage durant traitement: ___ %
- [ ] Mémoire utilisée: ___ MB
- [ ] Pas de freeze interface
- [ ] **PASS** si < 80% CPU, < 2 GB RAM

### Résultat
- [ ] **PASS**
- [ ] **FAIL**

---

## 📊 Critères d'Acceptation Globaux

### Fonctionnalité
- [ ] 100% fonctionnalités core opérationnelles
- [ ] 0 blockers critiques
- [ ] ≤2 bugs mineurs acceptables

### Utilisabilité
- [ ] Interface intuitive (opérateur formé en < 30 min)
- [ ] Messages d'erreur clairs et exploitables
- [ ] Aide contextuelle disponible

### Performance
- [ ] Traitement facture simple < 15 secondes
- [ ] Batch 200 lignes < 30 minutes
- [ ] Pas de crash durant tests (uptime 100%)

### Précision
- [ ] OCR: >85% précision (échantillon 100 factures)
- [ ] Classification HS: code correct dans top-3 suggestions >70% cas
- [ ] Calculs douaniers: 100% précision mathématique

### Sécurité
- [ ] Accès protégé par login
- [ ] Logs audit fonctionnels
- [ ] Données sensibles non exposées

---

## ✅ Signature Acceptation

### Opérateur
**Nom**: _______________  
**Date**: _______________  
**Signature**: _______________  
**Décision**: [ ] Accepté  [ ] Accepté avec réserves  [ ] Rejeté

**Réserves/Commentaires**:
```


```

### Superviseur
**Nom**: _______________  
**Date**: _______________  
**Signature**: _______________  
**Décision**: [ ] Accepté  [ ] Accepté avec réserves  [ ] Rejeté

**Réserves/Commentaires**:
```


```

### Chef de Projet
**Nom**: _______________  
**Date**: _______________  
**Signature**: _______________  
**Décision Finale**: [ ] **UAT PASSED - GO PRODUCTION**  [ ] Corrections requises

---

## 📝 Suivi Bugs Identifiés

| ID | Priorité | Description | Status | Assigné | Date Résolution |
|----|----------|-------------|--------|---------|-----------------|
| 1  | [ ] P0 [ ] P1 [ ] P2 | | [ ] Open [ ] Fixed | | |
| 2  | [ ] P0 [ ] P1 [ ] P2 | | [ ] Open [ ] Fixed | | |
| 3  | [ ] P0 [ ] P1 [ ] P2 | | [ ] Open [ ] Fixed | | |

**Légende Priorité**:
- **P0**: Bloquant (empêche UAT)
- **P1**: Majeur (impact fonctionnalité core)
- **P2**: Mineur (amélioration UX)
