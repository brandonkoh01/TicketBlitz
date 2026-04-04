FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --no-log-init --shell /bin/bash appuser

WORKDIR /app

COPY backend/shared/requirements.txt backend/shared/requirements.txt
COPY backend/composite/scenario-1/reservation-orchestrator/requirements.txt backend/composite/scenario-1/reservation-orchestrator/requirements.txt
RUN pip install --no-cache-dir -r backend/composite/scenario-1/reservation-orchestrator/requirements.txt

COPY backend/shared backend/shared
COPY backend/composite/scenario-1/reservation-orchestrator backend/composite/scenario-1/reservation-orchestrator

USER appuser

EXPOSE 5000

STOPSIGNAL SIGTERM

CMD ["python", "backend/composite/scenario-1/reservation-orchestrator/app.py"]
