"""
Calculateur douanier principal avec audit complet.

Ce module implémente le moteur de règles pour les calculs douaniers
avec traçabilité complète de chaque étape.
"""

import uuid
from decimal import Decimal
from pathlib import Path

from .config import TariffConfig
from .incoterms import convert_to_cif, round_fcfa
from .types import (
    AuditLog,
    CalculationInput,
    CalculationResult,
    IncotermsConversion,
    TaxBreakdown,
)


class CustomsCalculator:
    """Calculateur de droits et taxes douanières avec audit complet."""

    def __init__(self, tariffs_dir: Path | None = None):
        """
        Initialise le calculateur.

        Args:
            tariffs_dir: Répertoire contenant les fichiers de configuration tarifaire
        """
        if tariffs_dir is None:
            # Par défaut, utiliser data/tariffs/ depuis la racine du projet
            backend_dir = Path(__file__).parent.parent.parent
            tariffs_dir = backend_dir.parent / "data" / "tariffs"

        self.config = TariffConfig(tariffs_dir)

    def calculate(self, input_data: CalculationInput) -> CalculationResult:
        """
        Calcule les droits et taxes douanières pour une facture.

        Args:
            input_data: Données d'entrée de la facture

        Returns:
            Résultat complet du calcul avec audit log
        """
        # Générer ID de calcul déterministe basé sur l'entrée
        seed = "|".join(
            [
                str(input_data.invoice_number),
                str(input_data.hs_code),
                str(input_data.description),
                str(input_data.quantity),
                str(input_data.unit_price),
                str(input_data.currency),
                str(input_data.incoterm),
                str(input_data.origin_country),
                str(input_data.destination_country),
                str(input_data.freight_cost or ""),
                str(input_data.insurance_cost or ""),
                str(input_data.exchange_rate or ""),
                str(input_data.exemption_code or ""),
            ]
        )
        calc_id = str(uuid.uuid5(uuid.NAMESPACE_URL, seed))

        # Initialiser le journal d'audit
        audit = AuditLog(calculation_id=calc_id)

        # Étape 1: Conversion de la devise vers FCFA
        exchange_rate = (
            input_data.exchange_rate
            if input_data.exchange_rate
            else self.config.get_exchange_rate(input_data.currency)
        )

        total_value_foreign = input_data.quantity * input_data.unit_price
        total_value_fcfa = round_fcfa(total_value_foreign * exchange_rate)

        audit.add_entry(
            step="Conversion devise",
            formula=f"{input_data.currency} → XAF",
            inputs={
                "quantity": str(input_data.quantity),
                "unit_price": str(input_data.unit_price),
                "currency": input_data.currency,
                "exchange_rate": str(exchange_rate),
            },
            output=total_value_fcfa,
            notes=f"Taux de change: 1 {input_data.currency} = {exchange_rate} FCFA",
        )

        # Étape 2: Conversion Incoterms vers CIF
        cif_value, freight, insurance, formula = convert_to_cif(
            value=total_value_fcfa,
            incoterm=input_data.incoterm,
            freight_cost=input_data.freight_cost,
            insurance_cost=input_data.insurance_cost,
            origin=input_data.origin_country,
            destination=input_data.destination_country,
        )

        audit.add_entry(
            step="Conversion Incoterms",
            formula=formula,
            inputs={
                "original_incoterm": input_data.incoterm,
                "original_value": str(total_value_fcfa),
                "freight_cost": str(freight) if freight else "calculé",
                "insurance_cost": str(insurance) if insurance else "calculé",
            },
            output=cif_value,
            notes="Conversion vers valeur CIF (base imposable)",
        )

        incoterms_conv = IncotermsConversion(
            original_incoterm=input_data.incoterm,
            original_value=total_value_fcfa,
            freight_cost=freight,
            insurance_cost=insurance,
            cif_value=cif_value,
            formula_applied=formula,
        )

        # Étape 3: Déterminer la valeur en douane (base imposable)
        taxable_base = cif_value

        audit.add_entry(
            step="Valeur en douane",
            formula="Valeur en douane = CIF",
            inputs={"cif_value": str(cif_value)},
            output=taxable_base,
            notes="Valeur CIF = base imposable pour droits de douane",
        )

        # Étape 4: Calculer les droits de douane (DD)
        dd_rate, dd_amount = self._calculate_customs_duty(
            input_data.hs_code,
            taxable_base,
            input_data.exemption_code,
            input_data.origin_country,
            audit,
        )

        # Étape 5: Calculer les autres taxes (redevances, etc.)
        other_taxes = self._calculate_other_taxes(taxable_base, audit)

        # Étape 6: Calculer la base TVA
        vat_base = taxable_base + dd_amount + sum(other_taxes.values())

        audit.add_entry(
            step="Base TVA",
            formula="Base TVA = Valeur en douane + DD + Autres taxes",
            inputs={
                "taxable_base": str(taxable_base),
                "dd_amount": str(dd_amount),
                "other_taxes_total": str(sum(other_taxes.values())),
            },
            output=vat_base,
            notes="Assiette pour calcul de la TVA",
        )

        # Étape 7: Calculer la TVA
        vat_rate, vat_amount = self._calculate_vat(
            vat_base, input_data.destination_country, input_data.exemption_code, audit
        )

        # Étape 8: Calculer les totaux
        total_taxes = dd_amount + vat_amount + sum(other_taxes.values())
        total_amount = taxable_base + total_taxes

        audit.add_entry(
            step="Totaux",
            formula="Total = Valeur en douane + Taxes totales",
            inputs={
                "taxable_base": str(taxable_base),
                "dd_amount": str(dd_amount),
                "vat_amount": str(vat_amount),
                "other_taxes": str(sum(other_taxes.values())),
            },
            output={"total_taxes": str(total_taxes), "total_amount": str(total_amount)},
            notes="Montant total à payer (valeur + taxes)",
        )

        # Construire le breakdown fiscal
        tax_breakdown = TaxBreakdown(
            customs_duty_rate=dd_rate,
            customs_duty_amount=dd_amount,
            vat_rate=vat_rate,
            vat_base=vat_base,
            vat_amount=vat_amount,
            other_taxes=other_taxes,
            total_taxes=total_taxes,
            total_amount=total_amount,
        )

        # Déterminer les documents requis
        required_docs = self._get_required_documents(input_data, audit)

        # Créer le résultat final
        warnings = self._generate_warnings(input_data, dd_rate, vat_rate)

        result = CalculationResult(
            calculation_id=calc_id,
            input_data=input_data,
            incoterms_conversion=incoterms_conv,
            taxable_base=taxable_base,
            tax_breakdown=tax_breakdown,
            required_documents=required_docs,
            audit_log=audit,
            warnings=warnings,
        )

        return result

    def _calculate_customs_duty(
        self,
        hs_code: str,
        taxable_base: Decimal,
        exemption_code: str | None,
        origin_country: str,
        audit: AuditLog,
    ) -> tuple[Decimal, Decimal]:
        """Calcule les droits de douane avec gestion des exonérations."""

        # Récupérer le taux TEC de base
        base_rate = self.config.get_tec_rate(hs_code)

        # Vérifier les exonérations
        exemption = None
        if exemption_code:
            exemption = self.config.get_exemption(exemption_code)

        # Vérifier les préférences tarifaires (origine)
        preferential_reduction = self._check_preferential_tariff(origin_country, audit)

        # Calculer le taux effectif
        effective_rate = base_rate

        notes_list = [f"Taux TEC de base pour HS {hs_code}: {base_rate}%"]

        if exemption and "customs_duty" in exemption.get("applies_to", []):
            effective_rate = Decimal("0")
            notes_list.append(f"Exonération appliquée: {exemption.get('name')}")

        elif preferential_reduction > 0:
            reduction = base_rate * (Decimal(str(preferential_reduction)) / Decimal("100"))
            effective_rate = base_rate - reduction
            notes_list.append(
                f"Préférence tarifaire: réduction de {preferential_reduction}% (taux effectif: {effective_rate}%)"
            )

        # Calculer le montant des droits
        dd_amount = round_fcfa(taxable_base * (effective_rate / Decimal("100")))

        # Vérifier les minima de perception
        minima_config = self.config.tec_rates.get("minima", {})
        minimum = Decimal(str(minima_config.get(hs_code, minima_config.get("default", 0))))

        if dd_amount < minimum:
            old_amount = dd_amount
            dd_amount = minimum
            notes_list.append(
                f"Minimum de perception appliqué: {minimum} FCFA (au lieu de {old_amount} FCFA)"
            )

        audit.add_entry(
            step="Droits de douane (DD)",
            formula=f"DD = Base imposable × Taux TEC ({effective_rate}%)",
            inputs={
                "hs_code": hs_code,
                "taxable_base": str(taxable_base),
                "base_rate": str(base_rate),
                "effective_rate": str(effective_rate),
                "exemption_code": exemption_code or "aucun",
                "origin_country": origin_country,
            },
            output=dd_amount,
            notes=" | ".join(notes_list),
        )

        return effective_rate, dd_amount

    def _check_preferential_tariff(self, origin_country: str, audit: AuditLog) -> int:
        """
        Vérifie si un tarif préférentiel s'applique selon le pays d'origine.

        Returns:
            Pourcentage de réduction (0-100)
        """
        preferences = self.config.exemptions.get("preferential_tariffs", {})

        # Vérifier CEMAC (exonération totale)
        cemac = preferences.get("CEMAC_INTERNAL", {})
        if origin_country in cemac.get("origin_countries", []):
            return 100  # Réduction totale pour origine CEMAC

        # Vérifier APE UE-CEMAC
        ape_eu = preferences.get("APE_EU", {})
        if origin_country in ape_eu.get("origin_countries", []):
            return ape_eu.get("reduction_rate", 0)

        # Vérifier ZLECAf
        zlecaf = preferences.get("ZLECAF", {})
        if origin_country in zlecaf.get("origin_countries", []):
            return zlecaf.get("reduction_rate", 0)

        return 0  # Pas de préférence

    def _calculate_other_taxes(self, taxable_base: Decimal, audit: AuditLog) -> dict[str, Decimal]:
        """Calcule les autres taxes parafiscales."""

        other_taxes_config = self.config.vat_rates.get("other_taxes", {})
        result = {}

        # Redevance informatique (1%)
        if "redevance_informatique" in other_taxes_config:
            ri_config = other_taxes_config["redevance_informatique"]
            ri_rate = Decimal(str(ri_config.get("rate", 1.0)))
            ri_amount = round_fcfa(taxable_base * (ri_rate / Decimal("100")))
            result["redevance_informatique"] = ri_amount

            audit.add_entry(
                step="Redevance informatique",
                formula=f"RI = Valeur en douane × {ri_rate}%",
                inputs={"taxable_base": str(taxable_base), "rate": str(ri_rate)},
                output=ri_amount,
                notes=ri_config.get("description", ""),
            )

        # Taxe statistique (1%)
        if "taxe_statistique" in other_taxes_config:
            ts_config = other_taxes_config["taxe_statistique"]
            ts_rate = Decimal(str(ts_config.get("rate", 1.0)))
            ts_amount = round_fcfa(taxable_base * (ts_rate / Decimal("100")))
            result["taxe_statistique"] = ts_amount

            audit.add_entry(
                step="Taxe statistique",
                formula=f"TS = Valeur en douane × {ts_rate}%",
                inputs={"taxable_base": str(taxable_base), "rate": str(ts_rate)},
                output=ts_amount,
                notes=ts_config.get("description", ""),
            )

        # Prélèvements communautaires (1%)
        if "prelevements_communautaires" in other_taxes_config:
            pc_config = other_taxes_config["prelevements_communautaires"]
            pc_rate = Decimal(str(pc_config.get("rate", 1.0)))
            pc_amount = round_fcfa(taxable_base * (pc_rate / Decimal("100")))
            result["prelevements_communautaires"] = pc_amount

            audit.add_entry(
                step="Prélèvements communautaires",
                formula=f"PC = Valeur en douane × {pc_rate}%",
                inputs={"taxable_base": str(taxable_base), "rate": str(pc_rate)},
                output=pc_amount,
                notes=pc_config.get("description", ""),
            )

        return result

    def _calculate_vat(
        self, vat_base: Decimal, country: str, exemption_code: str | None, audit: AuditLog
    ) -> tuple[Decimal, Decimal]:
        """Calcule la TVA."""

        # Récupérer le taux de TVA
        base_rate = self.config.get_vat_rate(country)

        # Vérifier exonération TVA
        exemption = None
        if exemption_code:
            exemption = self.config.get_exemption(exemption_code)

        effective_rate = base_rate
        notes = f"Taux TVA {country}: {base_rate}%"

        if exemption and "vat" in exemption.get("applies_to", []):
            effective_rate = Decimal("0")
            notes += f" | Exonération TVA appliquée: {exemption.get('name')}"

        # Calculer le montant de TVA
        vat_amount = round_fcfa(vat_base * (effective_rate / Decimal("100")))

        audit.add_entry(
            step="Taxe sur la Valeur Ajoutée (TVA)",
            formula=f"TVA = Base TVA × {effective_rate}%",
            inputs={
                "vat_base": str(vat_base),
                "country": country,
                "base_rate": str(base_rate),
                "effective_rate": str(effective_rate),
                "exemption_code": exemption_code or "aucun",
            },
            output=vat_amount,
            notes=notes,
        )

        return effective_rate, vat_amount

    def _get_required_documents(self, input_data: CalculationInput, audit: AuditLog) -> list[str]:
        """Détermine les documents requis pour le dédouanement."""
        # Base documents via mapping HS -> documents with defaults
        mapped = self.config.get_documents_for_hs(input_data.hs_code)
        docs = list(mapped)

        # Documents spécifiques selon HS (compléments éventuels)
        hs_prefix = input_data.hs_code[:2]
        if hs_prefix in ["22", "24"]:  # Boissons alcoolisées, tabac
            docs.append("Licence d'importation produits soumis à accise")

        # Documents d'exonération
        if input_data.exemption_code:
            exemption = self.config.get_exemption(input_data.exemption_code)
            if exemption:
                required_docs = exemption.get("required_documents", [])
                docs.extend(required_docs)

        # Documents pour préférences tarifaires
        if input_data.origin_country in ["FR", "DE", "IT", "ES", "BE", "NL"]:
            docs.append("Certificat EUR.1 (préférence tarifaire UE)")

        if input_data.origin_country in ["GA", "CG", "CF", "TD", "GQ"]:
            docs.append("Certificat d'origine CEMAC (formulaire C10)")

        # Dé-duplication avant audit
        dedup: list[str] = []
        seen = set()
        for d in docs:
            if d not in seen:
                seen.add(d)
                dedup.append(d)

        audit.add_entry(
            step="Documents requis",
            formula="Liste des documents obligatoires",
            inputs={
                "hs_code": input_data.hs_code,
                "origin_country": input_data.origin_country,
                "exemption_code": input_data.exemption_code or "aucun",
            },
            output=len(dedup),
            notes=f"{len(dedup)} documents requis pour dédouanement",
        )

        return dedup

    def _generate_warnings(
        self, input_data: CalculationInput, dd_rate: Decimal, vat_rate: Decimal
    ) -> list[str]:
        """Génère des avertissements éventuels."""

        warnings = []

        # Avertissement si valeur très faible
        total_value = input_data.quantity * input_data.unit_price
        if total_value < Decimal("100"):
            warnings.append(
                "Attention: Valeur unitaire très faible. Vérifier la cohérence avec le prix du marché."
            )

        # Avertissement si taux DD élevé
        if dd_rate > Decimal("25"):
            warnings.append(
                f"Taux de droits de douane élevé ({dd_rate}%). Vérifier si éligible à préférence tarifaire."
            )

        # Avertissement si origine Chine sans certificat
        if input_data.origin_country == "CN" and not input_data.exemption_code:
            warnings.append(
                "Origine Chine: s'assurer que le certificat d'origine est valide et authentique."
            )

        return warnings
