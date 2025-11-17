"""
DECLADO-IA Backend - Application FastAPI principale
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    customs_calculation,
    declaration_auto,
    exchange_rates,
    health,
    hs_classification,
    ocr,
)
from app.api import export as export_api
from app.core.config import settings
from app.db import init_db, test_db_connection
from app.security.hmac_logger import configure_hmac_logging
from app.security.signatures import verify_signature

# Configuration du logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gère le cycle de vie de l'application
    Initialise la DB au démarrage
    """
    logger.info("🚀 Démarrage de DECLADO-IA Backend...")

    # Configure HMAC audit logger
    configure_hmac_logging()

    # Créer le dossier data s'il n'existe pas
    data_dir = Path("./data")
    data_dir.mkdir(exist_ok=True)

    # Verify signed repos if signature files present
    for repo in settings.SIGNED_REPOS:
        if not repo.exists():
            continue
        sig_path = repo.with_suffix(repo.suffix + ".sig") if repo.is_file() else (repo / ".sig")
        if sig_path.exists():
            if not verify_signature(repo):
                logger.critical(f"Repository signature invalid: {repo}")
                raise RuntimeError(f"Invalid signature for {repo}")
            logger.info(f"Repository signature OK: {repo}")

    # Initialiser la base de données
    try:
        init_db()
        if test_db_connection():
            logger.info("✅ Base de données initialisée et connectée")
        else:
            logger.warning("⚠️  Base de données initialisée mais problème de connexion")
    except Exception as e:
        logger.error(f"❌ Erreur d'initialisation de la DB: {e}")

    yield

    logger.info("👋 Arrêt de DECLADO-IA Backend")


# Créer l'application FastAPI
app = FastAPI(
    title="DECLADO-IA API",
    description="Système d'Extraction de Factures et Calculs Douaniers CEMAC",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

# Configuration CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inclure les routers
app.include_router(health.router, prefix="/api")
app.include_router(ocr.router, prefix="/api")
app.include_router(hs_classification.router, prefix="/api")
app.include_router(customs_calculation.router)
app.include_router(export_api.router)
app.include_router(exchange_rates.router, prefix="/api")
app.include_router(declaration_auto.router)


@app.get("/")
async def root():
    """Point d'entrée racine de l'API"""
    return {
        "message": "DECLADO-IA API",
        "version": settings.APP_VERSION,
        "status": "running",
        "environment": settings.APP_ENV,
        "endpoints": {
            "health": "/api/health",
            "health_ping": "/api/health/ping",
            "ocr_demo": "/api/ocr/demo",
            "ocr_process": "/api/ocr/process",
            "hs_suggest": "/api/hs/suggest",
            "customs_calculate": "/api/customs/calculate",
            "customs_test": "/api/customs/test",
            "export": "/api/export",
            "exchange_rates": "/api/exchange-rates",
            "declaration_auto": "/api/declaration/auto",
            "docs": "/docs",
        },
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT, reload=settings.API_RELOAD)
