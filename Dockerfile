# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Runtime-libraries die WeasyPrint (PDF-export) nodig heeft — zonder deze
# faalt alleen de PDF-download, maar liever meteen goed geregeld.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libcairo2 \
    libffi8 \
    shared-mime-info \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

# Wordt overschreven door een Railway-volume op /data (zie DEPLOYMENT.md);
# lokaal zonder volume valt dit terug op een map in de image (niet-persistent).
RUN mkdir -p /app/data

EXPOSE 8000

# $PORT wordt door Railway (en de meeste PaaS-platforms) automatisch gezet;
# lokaal zonder die var valt dit terug op 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
