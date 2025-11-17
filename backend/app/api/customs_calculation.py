"""
API endpoints pour le calcul douanier.
"""

from decimal import Decimal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.rules_engine import CalculationInput, CustomsCalculator

router = APIRouter(prefix="/api/customs", tags=["Customs Calculation"])


# Modèles Pydantic pour l'API
class CalculateRequest(BaseModel):
    """Requête pour le calcul douanier."""

    invoice_number: str = Field(..., description="Numéro de facture")
    hs_code: str = Field(..., min_length=4, max_length=10, description="Code HS (4-10 chiffres)")
    description: str = Field(..., description="Description de la marchandise")
    quantity: Decimal = Field(..., description="Quantité (nombre décimal)", gt=0)
    unit_price: Decimal = Field(..., description="Prix unitaire (nombre décimal)", gt=0)
    currency: str = Field(
        ..., min_length=3, max_length=3, description="Code devise ISO 4217 (USD, EUR, XAF, etc.)"
    )
    incoterm: str = Field(..., description="Incoterm (FOB, CFR, CIF, etc.)")
    origin_country: str = Field(
        ..., min_length=2, max_length=2, description="Pays d'origine (code ISO 3166-1 alpha-2)"
    )
    destination_country: str = Field(
        default="CM", min_length=2, max_length=2, description="Pays de destination"
    )
    freight_cost: Decimal | None = Field(default=None, description="Coût de fret (si connu)", ge=0)
    insurance_cost: Decimal | None = Field(
        default=None, description="Coût d'assurance (si connu)", ge=0
    )
    exchange_rate: Decimal | None = Field(
        default=None, description="Taux de change vers FCFA (si connu)", gt=0
    )
    exemption_code: str | None = Field(
        default=None, description="Code d'exonération (si applicable)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "invoice_number": "INV-2024-001",
                "hs_code": "6109",
                "description": "T-shirts en coton",
                "quantity": "100",
                "unit_price": "5",
                "currency": "EUR",
                "incoterm": "CIF",
                "origin_country": "CN",
                "destination_country": "CM",
            }
        }


class CalculateResponse(BaseModel):
    """Réponse du calcul douanier."""

    calculation_id: str
    input: dict
    incoterms_conversion: dict
    taxable_base: str
    tax_breakdown: dict
    required_documents: list[str]
    warnings: list[str]
    audit_log: dict

    class Config:
        json_schema_extra = {
            "example": {
                "calculation_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                "taxable_base": "1639893",
                "tax_breakdown": {
                    "customs_duty_rate": "20",
                    "customs_duty_amount": "327979",
                    "vat_rate": "19.25",
                    "vat_amount": "388286",
                    "total_taxes": "765462",
                    "total_amount": "2405355",
                },
            }
        }


# Instance globale du calculateur
_calculator: CustomsCalculator | None = None


def get_calculator() -> CustomsCalculator:
    """Récupère l'instance du calculateur (singleton lazy)."""
    global _calculator
    if _calculator is None:
        _calculator = CustomsCalculator()
    return _calculator


@router.post("/calculate", response_model=CalculateResponse)
async def calculate_customs(request: CalculateRequest):
    """
    Calcule les droits et taxes douanières pour une facture.

    Cette route accepte une facture normalisée et retourne:
    - Calcul détaillé des droits de douane (DD)
    - Calcul de la TVA
    - Autres taxes parafiscales
    - Valeur CIF et conversions Incoterms
    - Journal d'audit complet (traçabilité de chaque étape)
    - Liste des documents requis pour dédouanement

    Le calcul est reproductible: mêmes entrées → mêmes résultats.
    Tous les montants sont arrondis au franc CFA le plus proche.

    Args:
        request: Données de la facture (invoice, HS code, valeur, etc.)

    Returns:
        Résultat complet du calcul avec audit log

    Raises:
        HTTPException 400: Si les données d'entrée sont invalides
        HTTPException 500: Si une erreur survient lors du calcul
    """
    try:
        # Convertir la requête Pydantic en CalculationInput
        calc_input = CalculationInput(
            invoice_number=request.invoice_number,
            hs_code=request.hs_code,
            description=request.description,
            quantity=Decimal(request.quantity),
            unit_price=Decimal(request.unit_price),
            currency=request.currency,
            incoterm=request.incoterm,
            origin_country=request.origin_country,
            destination_country=request.destination_country,
            freight_cost=Decimal(request.freight_cost) if request.freight_cost else None,
            insurance_cost=Decimal(request.insurance_cost) if request.insurance_cost else None,
            exchange_rate=Decimal(request.exchange_rate) if request.exchange_rate else None,
            exemption_code=request.exemption_code,
        )

        # Exécuter le calcul
        calculator = get_calculator()
        result = calculator.calculate(calc_input)

        # Convertir le résultat en dictionnaire pour la réponse API
        result_dict = result.to_dict()

        return CalculateResponse(**result_dict)

    except ValueError as e:
        # Erreur de conversion des nombres (Decimal)
        raise HTTPException(status_code=400, detail=f"Données numériques invalides: {str(e)}")

    except Exception as e:
        # Erreur générique lors du calcul
        raise HTTPException(status_code=500, detail=f"Erreur lors du calcul douanier: {str(e)}")


@router.get("/test")
async def test_calculation():
    """
    Route de test pour vérifier le fonctionnement du calculateur.

    Exécute un cas de test simple et retourne le résultat.
    """
    test_request = CalculateRequest(
        invoice_number="TEST-001",
        hs_code="6109",
        description="T-shirts en coton (test)",
        quantity="100",
        unit_price="5",
        currency="EUR",
        incoterm="CIF",
        origin_country="CN",
        destination_country="CM",
    )

    return await calculate_customs(test_request)
