# BoloAI — AI for everyone through a normal phone call
# Lightweight, secure container definition

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application and operational modules
COPY app/ ./app/
COPY mock_services/ ./mock_services/
COPY fixtures/ ./fixtures/
COPY evals/ ./evals/
COPY tests/ ./tests/
COPY scripts/ ./scripts/
COPY pytest.ini .
COPY .env.example .
COPY aikart_runner.py .

# Default port (supports Koyeb dynamic PORT assignment)
ENV PORT=8000
EXPOSE 8000

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Start BoloAI server
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
