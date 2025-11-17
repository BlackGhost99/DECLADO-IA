"""
Chargement de la configuration tarifaire depuis fichiers YAML/JSON.
"""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml


class TariffConfig:
    """Gestionnaire de configuration tarifaire."""

    def __init__(self, data_dir: Path):
        """
        Initialise le gestionnaire de configuration.

        Args:
            data_dir: Répertoire contenant les fichiers de configuration
        """
        self.data_dir = Path(data_dir)
        self._tec_rates: dict[str, Any] | None = None
        self._vat_rates: dict[str, Any] | None = None
        self._exemptions: dict[str, Any] | None = None
        self._exchange_rates: dict[str, Any] | None = None
        self._hs_documents: dict[str, Any] | None = None

    def _load_yaml(self, filename: str) -> dict[str, Any]:
        """Charge un fichier YAML."""
        filepath = self.data_dir / filename
        if not filepath.exists():
            return {}

        with open(filepath, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _load_json(self, filename: str) -> dict[str, Any]:
        """Charge un fichier JSON."""
        filepath = self.data_dir / filename
        if not filepath.exists():
            return {}

        with open(filepath, encoding="utf-8") as f:
            return json.load(f)

    @property
    def tec_rates(self) -> dict[str, Any]:
        """Charge les taux TEC CEMAC."""
        if self._tec_rates is None:
            self._tec_rates = self._load_yaml("cemac_tec.yaml")
        return self._tec_rates

    @property
    def vat_rates(self) -> dict[str, Any]:
        """Charge les taux de TVA."""
        if self._vat_rates is None:
            self._vat_rates = self._load_yaml("vat_rates.yaml")
        return self._vat_rates

    @property
    def exemptions(self) -> dict[str, Any]:
        """Charge les règles d'exonération."""
        if self._exemptions is None:
            self._exemptions = self._load_yaml("exemptions.yaml")
        return self._exemptions

    @property
    def exchange_rates(self) -> dict[str, Any]:
        """Charge les taux de change."""
        if self._exchange_rates is None:
            self._exchange_rates = self._load_yaml("exchange_rates.yaml")
        return self._exchange_rates

    # -----------------------------
    # Documents requis (HS -> docs)
    # -----------------------------
    @property
    def hs_documents(self) -> dict[str, Any]:
        """Charge le mapping HS -> documents depuis data/documents/hs_documents.yaml.

        Note: self.data_dir pointe sur data/tariffs. On remonte d'un niveau pour atteindre data/documents.
        """
        if self._hs_documents is None:
            docs_path = self.data_dir.parent / "documents" / "hs_documents.yaml"
            if docs_path.exists():
                with open(docs_path, encoding="utf-8") as f:
                    self._hs_documents = yaml.safe_load(f) or {}
            else:
                self._hs_documents = {}
        return self._hs_documents

    def get_documents_for_hs(self, hs_code: str) -> list[str]:
        """Retourne la liste de documents pour un code HS par correspondance de préfixe.
        La correspondance la plus longue gagne. Ajoute aussi les _defaults s'ils existent.
        """
        mapping = self.hs_documents or {}
        hs = str(hs_code)
        # Collecte des candidats par préfixe
        candidates = []
        for key, value in mapping.items():
            if key == "_defaults":
                continue
            if hs.startswith(key) and isinstance(value, list):
                candidates.append((len(key), value))
        candidates.sort(key=lambda x: x[0], reverse=True)

        base_docs = list(mapping.get("_defaults", []) or [])
        if candidates:
            base_docs.extend(candidates[0][1])

        # Dé-duplication en préservant l'ordre
        seen = set()
        result: list[str] = []
        for d in base_docs:
            if d not in seen:
                seen.add(d)
                result.append(d)
        return result

    def get_tec_rate(self, hs_code: str) -> Decimal:
        """
        Récupère le taux TEC pour un code HS.

        Args:
            hs_code: Code HS (peut être partiel, ex: "6109" ou "610910")

        Returns:
            Taux TEC en pourcentage (ex: Decimal("30") pour 30%)
        """
        tec_data = self.tec_rates.get("rates", {})

        # Recherche exacte d'abord
        if hs_code in tec_data:
            return Decimal(str(tec_data[hs_code]))

        # Recherche par préfixe (du plus long au plus court)
        for length in range(len(hs_code), 1, -1):
            prefix = hs_code[:length]
            if prefix in tec_data:
                return Decimal(str(tec_data[prefix]))

        # Taux par défaut si non trouvé
        default_rate = tec_data.get("default", 20)
        return Decimal(str(default_rate))

    def get_vat_rate(self, country: str = "CM") -> Decimal:
        """
        Récupère le taux de TVA pour un pays.

        Args:
            country: Code pays ISO 3166-1 alpha-2

        Returns:
            Taux de TVA en pourcentage
        """
        vat_data = self.vat_rates.get("rates", {})
        rate = vat_data.get(country, vat_data.get("CEMAC", 19.25))
        return Decimal(str(rate))

    def get_exemption(self, exemption_code: str) -> dict[str, Any] | None:
        """
        Récupère les détails d'une exonération.

        Args:
            exemption_code: Code d'exonération

        Returns:
            Dictionnaire avec détails de l'exonération ou None
        """
        exemptions_data = self.exemptions.get("exemptions", {})
        return exemptions_data.get(exemption_code)

    def get_exchange_rate(self, currency: str) -> Decimal:
        """
        Récupère le taux de change vers FCFA.

        Args:
            currency: Code devise ISO 4217 (USD, EUR, etc.)

        Returns:
            Taux de change vers FCFA
        """
        rates_data = self.exchange_rates.get("rates", {})

        if currency == "XAF":  # FCFA
            return Decimal("1")

        rate = rates_data.get(currency, rates_data.get("default", 600))
        return Decimal(str(rate))
