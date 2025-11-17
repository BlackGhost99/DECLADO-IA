# Moteur de Règles Douanières DECLADO-IA

## Vue d'ensemble

Le module `rules_engine` implémente un **moteur de calcul douanier reproductible et auditable** conforme aux règlements CEMAC. Chaque calcul génère un journal d'audit complet traçant toutes les étapes, formules et valeurs intermédiaires.

## Architecture

### Modules principaux

```
backend/app/rules_engine/
├── __init__.py             # Exports publics
├── types.py                # Types de données (dataclasses)
├── config.py               # Chargement configuration tarifaire (YAML)
├── incoterms.py            # Conversions Incoterms (FOB→CFR→CIF)
├── calculator.py           # Moteur de calcul principal
```

### Fichiers de configuration (YAML)

```
data/tariffs/
├── cemac_tec.yaml          # Taux TEC (Tarif Extérieur Commun) par code HS
├── vat_rates.yaml          # Taux de TVA par pays CEMAC
├── exemptions.yaml         # Exonérations et préférences tarifaires
├── exchange_rates.yaml     # Taux de change vers FCFA
```

### Tests et validation

```
data/tests/
├── golden_set.yaml         # Jeu de tests "golden set" (6 cas manuellement vérifiés)

backend/tests/
├── test_rules_engine.py    # Tests unitaires (pytest)

docs/examples/
├── audit_*.json            # Exemples de journaux d'audit générés
```

## Fonctionnalités

### 1. Conversions Incoterms

Le module `incoterms.py` gère les conversions depuis n'importe quel Incoterm vers CIF (valeur en douane):

- **FOB → CFR**: Ajout du fret (10% FOB par défaut si non fourni)
- **CFR → CIF**: Ajout de l'assurance (0.5% CFR, minimum 5000 FCFA)
- **EXW/FCA/FAS**: Conversion via FOB équivalent (+5% frais pré-embarquement)
- **CPT/CIP/DAP/DPU/DDP**: Traités comme CFR pour simplification
- **CIF**: Aucune conversion (déjà en valeur douane)

**Règle d'arrondi**: Tous les montants arrondis au franc CFA le plus proche (ROUND_HALF_UP).

### 2. Calcul des droits de douane (DD)

Calcul basé sur:
- **Taux TEC**: Récupéré depuis `cemac_tec.yaml` par code HS (5 catégories: 0%, 5%, 10%, 20%, 30%)
- **Préférences tarifaires**:
  - CEMAC (origine GA, CG, CF, TD, GQ): **exonération totale** (100%)
  - APE UE-CEMAC (origine FR, DE, IT, ES, etc.): **réduction 80%**
  - ZLECAf (autres pays africains): **réduction 90%**
- **Exonérations**: Médicaments (EXO_MEDICAL), matériel éducatif, etc.

**Formule**: `DD = Valeur en douane × Taux TEC effectif`

### 3. Autres taxes parafiscales

- **Redevance informatique (RI)**: 1% de la valeur en douane (système SYDONIA)
- **Taxe statistique (TS)**: 1% de la valeur en douane
- **Prélèvements communautaires (PC)**: 1% de la valeur en douane

**Total autres taxes**: 3% de la valeur en douane

### 4. Calcul de la TVA

- **Base TVA**: `Valeur en douane + DD + Autres taxes`
- **Taux TVA Cameroun**: 19.25% (depuis 2022)
- **Exonérations**: Médicaments, matériel éducatif, missions diplomatiques

**Formule**: `TVA = Base TVA × 19.25%`

### 5. Journal d'audit (Audit Log)

Chaque calcul génère un `AuditLog` contenant 11+ entrées traçant:
1. Conversion devise (devise → FCFA)
2. Conversion Incoterms (FOB/CFR → CIF)
3. Valeur en douane (base imposable)
4. Droits de douane (DD) avec taux et préférences
5. Redevance informatique
6. Taxe statistique
7. Prélèvements communautaires
8. Base TVA
9. TVA
10. Totaux (taxes + montant total)
11. Documents requis

Chaque entrée contient:
- **step**: Nom de l'étape
- **formula**: Formule appliquée
- **inputs**: Valeurs d'entrée (dict)
- **output**: Résultat de l'étape
- **notes**: Explications supplémentaires
- **timestamp**: Horodatage ISO 8601

### 6. Documents requis

Le calculateur détermine automatiquement les documents nécessaires selon:
- **Type de marchandise** (HS code): médicaments → certificat santé, véhicules → quitus fiscal
- **Origine**: UE → EUR.1, CEMAC → C10
- **Exonération**: attestations spécifiques

Documents de base (toujours requis):
- Facture commerciale originale
- Connaissement (Bill of Lading) ou LTA
- Liste de colisage (Packing List)
- Certificat d'origine
- Déclaration en douane (DAU)

## API Endpoint

### POST `/api/customs/calculate`

Calcule les droits et taxes pour une facture.

**Request Body** (JSON):
```json
{
  "invoice_number": "INV-2024-001",
  "hs_code": "6109",
  "description": "T-shirts en coton",
  "quantity": "500",
  "unit_price": "5",
  "currency": "EUR",
  "incoterm": "CIF",
  "origin_country": "CN",
  "destination_country": "CM",
  "freight_cost": null,
  "insurance_cost": null,
  "exchange_rate": null,
  "exemption_code": null
}
```

**Response** (JSON):
```json
{
  "calculation_id": "a1b2c3d4-...",
  "input": { ... },
  "incoterms_conversion": {
    "original_incoterm": "CIF",
    "cif_value": "1639893",
    "freight_cost": "139391",
    "insurance_cost": "7789"
  },
  "taxable_base": "1639893",
  "tax_breakdown": {
    "customs_duty_rate": "20",
    "customs_duty_amount": "327979",
    "vat_rate": "19.25",
    "vat_amount": "388286",
    "total_taxes": "765462",
    "total_amount": "2405355"
  },
  "required_documents": [...],
  "warnings": [...],
  "audit_log": {
    "calculation_id": "...",
    "entries": [...]
  }
}
```

### GET `/api/customs/test`

Route de test retournant un calcul exemple.

## Tests et Validation

### Golden Set

6 cas de test manuellement vérifiés dans `data/tests/golden_set.yaml`:

1. **Riz (Thaïlande, FOB)**: Conversion Incoterms, taux 5%
2. **T-shirts (Chine, CIF)**: Taux 20%, avertissement origine Chine
3. **Bijoux (France, FOB)**: Préférence APE UE-CEMAC (réduction 80%)
4. **Médicaments (Inde, CIF)**: Exonération totale DD + TVA
5. **Télécoms (Gabon, FOB)**: Préférence CEMAC (exonération DD, TVA normale)
6. **Outils (Chine, CFR)**: Conversion CFR→CIF, taux 10%

**Tolérance**: ±1 ou ±2 FCFA selon complexité (cumul d'arrondis).

### Exécution des tests

```bash
# Tests unitaires (pytest)
cd backend
python -m pytest tests/test_rules_engine.py -v

# Tests end-to-end avec génération d'exemples
python test_customs_direct.py
```

**Résultats attendus**: 10/10 tests passent (6 golden set + 4 tests spécifiques).

### Exemples générés

Fichiers JSON dans `docs/examples/`:
- `audit_riz_thailande.json`
- `audit_tshirts_chine.json`
- `audit_bijoux_france.json`
- `audit_medicaments_exoneration.json`
- `audit_telecoms_gabon.json`

Chaque exemple contient:
- Calcul complet (inputs, conversions, taxes, totaux)
- Journal d'audit avec 11 étapes détaillées
- Documents requis
- Avertissements éventuels

## Utilisation

### En Python

```python
from decimal import Decimal
from app.rules_engine import CustomsCalculator, CalculationInput

# Créer une entrée de calcul
calc_input = CalculationInput(
    invoice_number="INV-001",
    hs_code="6109",
    description="T-shirts en coton",
    quantity=Decimal("100"),
    unit_price=Decimal("5"),
    currency="EUR",
    incoterm="CIF",
    origin_country="CN",
    destination_country="CM"
)

# Exécuter le calcul
calculator = CustomsCalculator()
result = calculator.calculate(calc_input)

# Accéder aux résultats
print(f"Valeur CIF: {result.incoterms_conversion.cif_value:,.0f} FCFA")
print(f"DD ({result.tax_breakdown.customs_duty_rate}%): {result.tax_breakdown.customs_duty_amount:,.0f} FCFA")
print(f"TVA ({result.tax_breakdown.vat_rate}%): {result.tax_breakdown.vat_amount:,.0f} FCFA")
print(f"Total à payer: {result.tax_breakdown.total_amount:,.0f} FCFA")

# Journal d'audit
for entry in result.audit_log.entries:
    print(f"{entry.step}: {entry.formula}")
```

### Via API (FastAPI)

```bash
# Démarrer le backend
cd backend
uvicorn app.main:app --reload

# Tester l'endpoint
curl -X POST http://localhost:8000/api/customs/calculate \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_number": "INV-001",
    "hs_code": "6109",
    "description": "T-shirts",
    "quantity": "100",
    "unit_price": "5",
    "currency": "EUR",
    "incoterm": "CIF",
    "origin_country": "CN"
  }'
```

## Critères d'acceptation

✅ **Reproductibilité**: Mêmes inputs → mêmes résultats (validé par golden set)

✅ **Auditabilité**: Chaque calcul a journal complet avec formules et valeurs intermédiaires

✅ **Règles configurables**: Taux TEC, TVA, exemptions dans fichiers YAML séparés

✅ **Tests golden set**: 6 cas manuels reproduits avec écart ≤ ±2 FCFA

✅ **Traçabilité**: ID unique par calcul, timestamp par étape, exports JSON

✅ **Documents requis**: Génération automatique selon HS code, origine, exonérations

✅ **Conformité CEMAC**: TEC 5 catégories, TVA 19.25%, préférences tarifaires

## Limitations et améliorations futures

### Limitations actuelles

1. **Taux TEC partiels**: Configuration contient ~30 codes HS (vs. milliers en production)
2. **Taux de change statiques**: Fichier YAML (vs. API BEAC temps réel)
3. **Pays UE incomplets**: Seulement 6 pays listés dans APE (vs. 27)
4. **Validation documents**: Pas de vérification authenticité certificats d'origine

### Améliorations recommandées

1. **Base TEC complète**: Charger nomenclature SYDONIA avec 10,000+ codes HS
2. **API taux de change**: Intégration temps réel avec BEAC (mis à jour quotidiennement)
3. **Règles d'origine**: Vérification cumul diagonal, teneur en valeur, transformation substantielle
4. **Historique calculs**: Stockage PostgreSQL avec recherche par facture/période
5. **Exports**: Génération PDF pré-déclaration, XML pour système SYDONIA
6. **Validation ML**: Détection anomalies (valeurs anormalement basses, incohérences HS/description)

## Références

- **Tarif CEMAC 2024**: [BEAC - Nomenclature TEC](https://www.beac.int/)
- **TVA Cameroun**: Loi de finances 2022 (taux 19.25%)
- **Incoterms 2020**: CCI - Chambre de Commerce Internationale
- **APE UE-CEMAC**: Accord de Partenariat Économique 2023
- **ZLECAf**: Zone de Libre-Échange Continentale Africaine

---

**Version**: 1.0  
**Date**: 2024-11-15  
**Auteur**: DECLADO-IA Team  
**Status**: ✅ Production-ready (avec limitations documentées)
