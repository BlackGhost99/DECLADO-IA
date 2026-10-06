"""
Health check endpoint
"""

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db import get_db, test_db_connection
from app.db.models import HealthCheck
from app.models.schemas import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse)
async def health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint
    Vérifie que l'API et la base de données fonctionnent
    """
    # Tester la connexion DB
    db_status = "connected" if test_db_connection() else "disconnected"

    # Enregistrer le health check dans la DB (test d'écriture)
    try:
        health_record = HealthCheck(
            status="healthy", message=f"API running on {settings.API_HOST}:{settings.API_PORT}"
        )
        db.add(health_record)
        db.commit()
        db_write = True
    except Exception as e:
        db_write = False
        db_status = f"error: {str(e)}"

    return HealthResponse(
        status="healthy" if db_write else "degraded",
        version=settings.APP_VERSION,
        timestamp=datetime.now(),
        database=db_status,
        message="All systems operational" if db_write else "Database write failed",
    )


@router.get("/ping")
async def ping():
    """Simple ping endpoint sans DB"""
    return {"status": "pong", "timestamp": datetime.now()}
