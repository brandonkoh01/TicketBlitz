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
COPY backend/atomic/waitlist-service/requirements.txt backend/atomic/waitlist-service/requirements.txt
RUN pip install --no-cache-dir -r backend/atomic/waitlist-service/requirements.txt

COPY backend/shared backend/shared
COPY backend/atomic/waitlist-service backend/atomic/waitlist-service

USER appuser

EXPOSE 5000

STOPSIGNAL SIGTERM

CMD ["python", "backend/atomic/waitlist-service/waitlist.py"]
