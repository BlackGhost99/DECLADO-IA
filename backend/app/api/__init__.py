"""
API Router initialization
"""
from fastapi import APIRouter

api_router = APIRouter()

# Import des routes (seront créées ensuite)
from . import health, ocr, hs_classification

__all__ = ["api_router"]
