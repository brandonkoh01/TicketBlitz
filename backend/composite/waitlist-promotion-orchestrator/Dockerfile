FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

RUN useradd --create-home --no-log-init --shell /bin/bash appuser

WORKDIR /app

COPY backend/shared/requirements.txt backend/shared/requirements.txt
COPY backend/composite/waitlist-promotion-orchestrator/requirements.txt backend/composite/waitlist-promotion-orchestrator/requirements.txt
RUN pip install --no-cache-dir -r backend/composite/waitlist-promotion-orchestrator/requirements.txt

COPY backend/shared backend/shared
COPY backend/composite/waitlist-promotion-orchestrator backend/composite/waitlist-promotion-orchestrator

USER appuser

STOPSIGNAL SIGTERM

CMD ["python", "backend/composite/waitlist-promotion-orchestrator/waitlist_promotion.py"]
