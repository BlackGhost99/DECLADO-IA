"""
Modèles SQLAlchemy pour la base de données
"""

from sqlalchemy import Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from app.db.database import Base


class HealthCheck(Base):
    """Table pour stocker les health checks (test DB)"""

    __tablename__ = "health_checks"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String(50), default="healthy")
    message = Column(Text, nullable=True)


class Invoice(Base):
    """Table pour stocker les factures"""

    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(100), unique=True, index=True)
    date = Column(DateTime(timezone=True))
    vendor = Column(String(255))
    total_amount = Column(Float)
    currency = Column(String(10), default="USD")
    status = Column(String(50), default="draft")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class HSClassification(Base):
    """Table pour stocker les classifications HS"""

    __tablename__ = "hs_classifications"

    id = Column(Integer, primary_key=True, index=True)
    product_description = Column(Text)
    hs_code = Column(String(10))
    confidence_score = Column(Float)
    model_version = Column(String(50))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
