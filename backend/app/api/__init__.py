"""API Router initialization with graceful optional imports.

Only critical endpoints (health) are required for startup. OCR and HS
classification endpoints are loaded opportunistically; missing heavy
ML/OCR dependencies will not block the API from running.
"""
import logging
from fastapi import APIRouter

logger = logging.getLogger(__name__)

api_router = APIRouter()

from . import health  # noqa: E402

optional_modules = ["ocr", "hs_classification", "scanners"]
for mod_name in optional_modules:
	try:
		module = __import__(f"app.api.{mod_name}", fromlist=[mod_name])
		# Attach router if present
		if hasattr(module, "router"):
			logger.info(f"Loaded optional API module: {mod_name}")
		else:
			logger.warning(f"Module {mod_name} has no router attribute")
	except Exception as e:  # broad: we want to continue startup regardless
		logger.warning(f"Skipping optional API module '{mod_name}': {e}")

__all__ = ["api_router"]
