"""
Schémas Pydantic pour la validation des données API
"""

from datetime import datetime

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Réponse du health check"""

    status: str = "healthy"
    version: str = "0.1.0"
    timestamp: datetime = Field(default_factory=datetime.now)
    database: str = "connected"
    message: str | None = None


class OCRDemoRequest(BaseModel):
    """Requête pour le démo OCR"""

    text: str = Field(..., min_length=1, max_length=1000, description="Texte à analyser")


class OCRDemoResponse(BaseModel):
    """Réponse du démo OCR"""

    original_text: str
    word_count: int
    char_count: int
    detected_numbers: list[str]
    message: str = "OCR demo processing completed"


class OCRProcessResponse(BaseModel):
    """Réponse complète du pipeline OCR"""

    source: str
    num_pages: int
    pages: list[dict]
    normalized: dict
    cer: float | None = None
    warnings: list[str] = []


class HSClassificationRequest(BaseModel):
    """Requête pour suggestion HS"""

    product_description: str = Field(..., min_length=3, max_length=500)


class HSClassificationResponse(BaseModel):
    """Réponse de suggestion HS"""

    product_description: str
    suggested_codes: list[dict]  # Liste de {code, description, confidence}
    message: str = "HS classification completed"


class InvoiceBase(BaseModel):
    """Base pour une facture"""

    invoice_number: str
    vendor: str
    total_amount: float
    currency: str = "USD"


class InvoiceCreate(InvoiceBase):
    """Schéma pour créer une facture"""

    pass


class InvoiceResponse(InvoiceBase):
    """Schéma de réponse d'une facture"""

    id: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
