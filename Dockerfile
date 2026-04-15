# =============================================================================
# Dockerfile — CMIA FastAPI backend
# What this file does: Builds a minimal Python image for the FastAPI service.
# Layer: Deployment — image pushed to ACR, pulled by AKS.
# Why multi-stage isn't used: single service, no compiled assets needed.
# =============================================================================

FROM --platform=linux/arm64 python:3.11-slim

# System deps: pymssql needs FreeTDS headers at build time
RUN apt-get update && apt-get install -y --no-install-recommends \
    freetds-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /code

# Install Python deps first (layer-cached unless requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source
COPY app/ ./app/

# Non-root user — AKS security best practice
RUN useradd -m appuser && chown -R appuser /code
USER appuser

EXPOSE 8000

# Secrets come from K8s Secrets mounted as env vars — never baked into image
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
# amd64
