"""
API endpoint pour les taux de change
Phase 10: Tests, QA et Performance
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.rules_engine.config import TariffConfig

router = APIRouter(tags=["exchange-rates"])


class ExchangeRatesResponse(BaseModel):
    """Réponse avec les taux de change."""

    XAF: float = 1.0
    USD: float
    EUR: float
    GBP: float
    CNY: float
    source: str = "CEMAC/BEAC"
    last_updated: str | None = None


@router.get("/exchange-rates", response_model=ExchangeRatesResponse)
async def get_exchange_rates():
    """
    Récupère les taux de change actuels depuis la configuration.

    Les taux sont exprimés comme "1 [devise] = X XAF"
    """
    try:
        # Charger la configuration tarifaire
        backend_dir = Path(__file__).parent.parent.parent
        tariffs_dir = backend_dir / "data" / "tariffs"

        config = TariffConfig(tariffs_dir)

        # Récupérer les taux
        rates = {
            "XAF": 1.0,
            "USD": float(config.get_exchange_rate("USD")),
            "EUR": float(config.get_exchange_rate("EUR")),
            "GBP": float(config.get_exchange_rate("GBP")),
            "CNY": float(config.get_exchange_rate("CNY")),
        }

        return ExchangeRatesResponse(
            **rates,
            source="CEMAC/BEAC",
            last_updated=None,  # TODO: Ajouter date de mise à jour depuis le fichier YAML
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Erreur lors de la récupération des taux de change: {str(e)}"
        ) from e
