FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
# Lot 3 : OCR des scans (Tesseract, langues française et anglaise).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY . .
# Le volume des pièces (compose : /var/clairtransit/private) hérite à sa création du
# propriétaire de ce dossier ; sans lui, il appartient à root et l'application ne peut pas écrire.
RUN useradd --create-home app \
    && mkdir -p /var/clairtransit/private \
    && chown -R app /app /var/clairtransit
USER app
EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
