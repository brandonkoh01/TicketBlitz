FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend

RUN useradd --create-home --no-log-init --shell /bin/bash appuser

WORKDIR /app

COPY backend/shared/requirements.txt backend/shared/requirements.txt
COPY backend/atomic/expiry-scheduler-service/requirements.txt backend/atomic/expiry-scheduler-service/requirements.txt
RUN pip install --no-cache-dir -r backend/atomic/expiry-scheduler-service/requirements.txt

COPY backend/shared backend/shared
COPY backend/atomic/expiry-scheduler-service backend/atomic/expiry-scheduler-service

USER appuser

STOPSIGNAL SIGTERM

CMD ["python", "backend/atomic/expiry-scheduler-service/expiry_scheduler.py"]
