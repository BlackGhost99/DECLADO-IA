"""
Types de données pour le moteur de règles douanières.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional


@dataclass
class AuditLogEntry:
    """Une entrée dans le journal d'audit."""

    step: str  # Nom de l'étape de calcul
    formula: str  # Formule appliquée
    inputs: Dict[str, Any]  # Valeurs d'entrée
    output: Any  # Résultat de l'étape
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    notes: Optional[str] = None  # Notes ou explications supplémentaires


@dataclass
class AuditLog:
    """Journal d'audit complet d'un calcul douanier."""

    calculation_id: str
    entries: List[AuditLogEntry] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def add_entry(
        self,
        step: str,
        formula: str,
        inputs: Dict[str, Any],
        output: Any,
        notes: Optional[str] = None,
    ):
        """Ajoute une entrée au journal d'audit."""
        entry = AuditLogEntry(step=step, formula=formula, inputs=inputs, output=output, notes=notes)
        self.entries.append(entry)

    def to_dict(self) -> Dict[str, Any]:
        """Convertit le journal en dictionnaire pour sérialisation."""
        return {
            "calculation_id": self.calculation_id,
            "created_at": self.created_at,
            "entries": [
                {
                    "step": e.step,
                    "formula": e.formula,
                    "inputs": e.inputs,
                    "output": str(e.output) if isinstance(e.output, Decimal) else e.output,
                    "timestamp": e.timestamp,
                    "notes": e.notes,
                }
                for e in self.entries
            ],
        }


@dataclass
class IncotermsConversion:
    """Résultat d'une conversion Incoterms."""

    original_incoterm: str
    original_value: Decimal
    freight_cost: Decimal
    insurance_cost: Decimal
    cif_value: Decimal
    formula_applied: str


@dataclass
class TaxBreakdown:
    """Détail des taxes calculées."""

    customs_duty_rate: Decimal  # Taux DD (%)
    customs_duty_amount: Decimal  # Montant DD (FCFA)
    vat_rate: Decimal  # Taux TVA (%)
    vat_base: Decimal  # Assiette TVA (FCFA)
    vat_amount: Decimal  # Montant TVA (FCFA)
    other_taxes: Dict[str, Decimal] = field(default_factory=dict)  # Autres taxes
    total_taxes: Decimal = Decimal("0")  # Total taxes
    total_amount: Decimal = Decimal("0")  # Valeur CIF + taxes


@dataclass
class CalculationInput:
    """Données d'entrée pour le calcul douanier."""

    invoice_number: str
    hs_code: str
    description: str
    quantity: Decimal
    unit_price: Decimal  # Prix unitaire en devise originale
    currency: str  # Code devise (USD, EUR, etc.)
    incoterm: str  # FOB, CFR, CIF, etc.
    origin_country: str  # Pays d'origine (ISO 3166-1 alpha-2)
    destination_country: str = "CM"  # Cameroun par défaut
    freight_cost: Optional[Decimal] = None  # Coût de fret si connu
    insurance_cost: Optional[Decimal] = None  # Coût d'assurance si connu
    exchange_rate: Optional[Decimal] = None  # Taux de change vers FCFA
    exemption_code: Optional[str] = None  # Code d'exonération si applicable


@dataclass
class CalculationResult:
    """Résultat complet d'un calcul douanier."""

    calculation_id: str
    input_data: CalculationInput
    incoterms_conversion: IncotermsConversion
    taxable_base: Decimal  # Valeur en douane (base imposable)
    tax_breakdown: TaxBreakdown
    required_documents: List[str]  # Documents requis pour dédouanement
    audit_log: AuditLog
    warnings: List[str] = field(default_factory=list)  # Avertissements éventuels

    def to_dict(self) -> Dict[str, Any]:
        """Convertit le résultat en dictionnaire pour API."""
        return {
            "calculation_id": self.calculation_id,
            "input": {
                "invoice_number": self.input_data.invoice_number,
                "hs_code": self.input_data.hs_code,
                "description": self.input_data.description,
                "quantity": str(self.input_data.quantity),
                "unit_price": str(self.input_data.unit_price),
                "currency": self.input_data.currency,
                "incoterm": self.input_data.incoterm,
                "origin_country": self.input_data.origin_country,
            },
            "incoterms_conversion": {
                "original_incoterm": self.incoterms_conversion.original_incoterm,
                "original_value": str(self.incoterms_conversion.original_value),
                "freight_cost": str(self.incoterms_conversion.freight_cost),
                "insurance_cost": str(self.incoterms_conversion.insurance_cost),
                "cif_value": str(self.incoterms_conversion.cif_value),
                "formula": self.incoterms_conversion.formula_applied,
            },
            "taxable_base": str(self.taxable_base),
            "tax_breakdown": {
                "customs_duty_rate": str(self.tax_breakdown.customs_duty_rate),
                "customs_duty_amount": str(self.tax_breakdown.customs_duty_amount),
                "vat_rate": str(self.tax_breakdown.vat_rate),
                "vat_base": str(self.tax_breakdown.vat_base),
                "vat_amount": str(self.tax_breakdown.vat_amount),
                "other_taxes": {k: str(v) for k, v in self.tax_breakdown.other_taxes.items()},
                "total_taxes": str(self.tax_breakdown.total_taxes),
                "total_amount": str(self.tax_breakdown.total_amount),
            },
            "required_documents": self.required_documents,
            "warnings": self.warnings,
            "audit_log": self.audit_log.to_dict(),
        }
