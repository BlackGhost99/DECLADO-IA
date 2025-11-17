"""
Conversions Incoterms pour calculs douaniers.

Convertit les valeurs FOB → CFR → CIF selon les règles douanières CEMAC.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Tuple


def round_fcfa(amount: Decimal) -> Decimal:
    """
    Arrondit un montant en FCFA selon les règles douanières.

    Les montants sont arrondis au franc le plus proche (0.5 arrondi vers le haut).

    Args:
        amount: Montant à arrondir

    Returns:
        Montant arrondi
    """
    return amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def calculate_freight_default(fob_value: Decimal, origin: str, destination: str = "CM") -> Decimal:
    """
    Calcule un coût de fret par défaut si non fourni.

    Règle simplifiée: 10% de la valeur FOB pour import maritime.
    En pratique, utiliser les frais réels de la facture de transport.

    Args:
        fob_value: Valeur FOB en FCFA
        origin: Pays d'origine (ISO 3166-1 alpha-2)
        destination: Pays de destination

    Returns:
        Coût de fret estimé en FCFA
    """
    # Règle simplifiée: 10% FOB
    # TODO: implémenter table de frais réels par route maritime
    freight_rate = Decimal("0.10")
    return round_fcfa(fob_value * freight_rate)


def calculate_insurance_default(cfr_value: Decimal) -> Decimal:
    """
    Calcule un coût d'assurance par défaut si non fourni.

    Règle CEMAC: assurance = (CFR × 0.5%) ou minimum 5000 FCFA.

    Args:
        cfr_value: Valeur CFR (FOB + Fret) en FCFA

    Returns:
        Coût d'assurance en FCFA
    """
    # Taux d'assurance standard CEMAC: 0.5%
    insurance_rate = Decimal("0.005")
    calculated_insurance = cfr_value * insurance_rate

    # Minimum de 5000 FCFA
    minimum_insurance = Decimal("5000")

    insurance = max(calculated_insurance, minimum_insurance)
    return round_fcfa(insurance)


def fob_to_cfr(
    fob_value: Decimal,
    freight_cost: Decimal | None = None,
    origin: str = "CN",
    destination: str = "CM",
) -> Tuple[Decimal, Decimal]:
    """
    Convertit FOB vers CFR (Cost and Freight).

    Formule: CFR = FOB + Fret

    Args:
        fob_value: Valeur FOB en FCFA
        freight_cost: Coût de fret en FCFA (si connu)
        origin: Pays d'origine
        destination: Pays de destination

    Returns:
        Tuple (CFR value, freight_cost utilisé)
    """
    if freight_cost is None:
        freight_cost = calculate_freight_default(fob_value, origin, destination)

    cfr_value = round_fcfa(fob_value + freight_cost)
    return cfr_value, freight_cost


def cfr_to_cif(
    cfr_value: Decimal, insurance_cost: Decimal | None = None
) -> Tuple[Decimal, Decimal]:
    """
    Convertit CFR vers CIF (Cost, Insurance and Freight).

    Formule: CIF = CFR + Assurance

    Args:
        cfr_value: Valeur CFR en FCFA
        insurance_cost: Coût d'assurance en FCFA (si connu)

    Returns:
        Tuple (CIF value, insurance_cost utilisé)
    """
    if insurance_cost is None:
        insurance_cost = calculate_insurance_default(cfr_value)

    cif_value = round_fcfa(cfr_value + insurance_cost)
    return cif_value, insurance_cost


def fob_to_cif(
    fob_value: Decimal,
    freight_cost: Decimal | None = None,
    insurance_cost: Decimal | None = None,
    origin: str = "CN",
    destination: str = "CM",
) -> Tuple[Decimal, Decimal, Decimal]:
    """
    Convertit FOB directement vers CIF.

    Formule: CIF = FOB + Fret + Assurance

    Args:
        fob_value: Valeur FOB en FCFA
        freight_cost: Coût de fret en FCFA (si connu)
        insurance_cost: Coût d'assurance en FCFA (si connu)
        origin: Pays d'origine
        destination: Pays de destination

    Returns:
        Tuple (CIF value, freight_cost utilisé, insurance_cost utilisé)
    """
    # Étape 1: FOB → CFR
    cfr_value, freight = fob_to_cfr(fob_value, freight_cost, origin, destination)

    # Étape 2: CFR → CIF
    cif_value, insurance = cfr_to_cif(cfr_value, insurance_cost)

    return cif_value, freight, insurance


def convert_to_cif(
    value: Decimal,
    incoterm: str,
    freight_cost: Decimal | None = None,
    insurance_cost: Decimal | None = None,
    origin: str = "CN",
    destination: str = "CM",
) -> Tuple[Decimal, Decimal, Decimal, str]:
    """
    Convertit n'importe quel Incoterm vers CIF.

    Args:
        value: Valeur selon l'Incoterm d'origine en FCFA
        incoterm: Incoterm d'origine (FOB, CFR, CIF, etc.)
        freight_cost: Coût de fret en FCFA (si connu)
        insurance_cost: Coût d'assurance en FCFA (si connu)
        origin: Pays d'origine
        destination: Pays de destination

    Returns:
        Tuple (CIF value, freight_cost, insurance_cost, formula_applied)
    """
    incoterm_upper = incoterm.upper().strip()

    if incoterm_upper == "CIF":
        # Déjà en CIF, pas de conversion nécessaire
        # Mais on doit extraire fret et assurance pour l'audit
        # Règle: si non fournis, on estime rétroactivement
        if freight_cost is None:
            freight_cost = calculate_freight_default(value * Decimal("0.85"), origin, destination)
        if insurance_cost is None:
            insurance_cost = calculate_insurance_default(value * Decimal("0.95"))

        return value, freight_cost, insurance_cost, "CIF (aucune conversion)"

    elif incoterm_upper == "CFR" or incoterm_upper == "C&F":
        # CFR → CIF
        cif_value, insurance = cfr_to_cif(value, insurance_cost)

        # Fret non fourni, on l'estime rétroactivement
        if freight_cost is None:
            fob_estimate = value * Decimal("0.90")  # Estimation inverse
            freight_cost = calculate_freight_default(fob_estimate, origin, destination)

        return cif_value, freight_cost, insurance, "CFR + Assurance = CIF"

    elif incoterm_upper == "FOB":
        # FOB → CIF
        cif_value, freight, insurance = fob_to_cif(
            value, freight_cost, insurance_cost, origin, destination
        )
        return cif_value, freight, insurance, "FOB + Fret + Assurance = CIF"

    elif incoterm_upper in ["EXW", "FCA", "FAS"]:
        # Pour ces Incoterms, on ajoute des frais logistiques avant FOB
        # Règle simplifiée: +5% pour frais pré-embarquement
        pre_shipment_rate = Decimal("0.05")
        fob_equivalent = round_fcfa(value * (Decimal("1") + pre_shipment_rate))

        cif_value, freight, insurance = fob_to_cif(
            fob_equivalent, freight_cost, insurance_cost, origin, destination
        )
        return cif_value, freight, insurance, f"{incoterm_upper} +5% → FOB → CIF"

    elif incoterm_upper in ["CPT", "CIP", "DAP", "DPU", "DDP"]:
        # Incoterms "delivered": déjà incluent fret (et parfois assurance)
        # Conversion simplifiée: considérer comme CFR
        cif_value, insurance = cfr_to_cif(value, insurance_cost)

        if freight_cost is None:
            fob_estimate = value * Decimal("0.90")
            freight_cost = calculate_freight_default(fob_estimate, origin, destination)

        return cif_value, freight_cost, insurance, f"{incoterm_upper} ≈ CFR → CIF"

    else:
        # Incoterm non reconnu, traiter comme FOB par défaut
        cif_value, freight, insurance = fob_to_cif(
            value, freight_cost, insurance_cost, origin, destination
        )
        return cif_value, freight, insurance, f"{incoterm} (inconnu, traité comme FOB) → CIF"
