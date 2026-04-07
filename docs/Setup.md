# TicketBlitz — Complete Project Setup & Development Guide

> **For:** All team members  
> **Updated:** 2026-04-07  
> **Project:** IS213 Enterprise Solution Development — TicketBlitz Concert Ticketing Platform  
> **Deadline:** Week 13 class presentation & submission

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture Overview](#2-architecture-overview)
3. [Two-Week Development Timeline](#3-two-week-development-timeline)
4. [Service Build Sequence](#4-service-build-sequence)
5. [Prerequisites Check](#5-prerequisites-check)
6. [Clone the Repository](#6-clone-the-repository)
7. [Environment Variables](#7-environment-variables)
8. [Option A — Local Python Virtual Environment](#8-option-a--local-python-virtual-environment)
9. [Option B — Docker (Primary Workflow)](#9-option-b--docker-primary-workflow)
10. [Stripe CLI Setup](#10-stripe-cli-setup)
11. [RabbitMQ Exchange Setup](#11-rabbitmq-exchange-setup)
12. [Kong API Gateway](#12-kong-api-gateway)
13. [Verify the Full Stack](#13-verify-the-full-stack)
14. [Daily Development Workflow](#14-daily-development-workflow)
15. [Writing a Service — Standard Template](#15-writing-a-service--standard-template)
16. [Useful Commands Reference](#16-useful-commands-reference)
17. [Troubleshooting](#17-troubleshooting)

---

## 1. Project Overview

TicketBlitz is a microservices-based concert ticketing platform built on a Service-Oriented Architecture (SOA). The platform handles three core business scenarios:

| Scenario | Description |
|---|---|
| **Scenario 1** | Fan books a ticket — async reservation, Stripe payment, waitlist, hold expiry |
| **Scenario 2** | Organiser launches a flash sale with dynamic tier pricing and price broadcast |
| **Scenario 3** | Fan cancels a booking — orchestration-based refund, seat release, and waitlist reallocation |

**Tech Stack at a glance:**

| Layer | Technology |
|---|---|
| Language & Framework | Python 3.11 + Flask |
| API Gateway | Kong Gateway 3.9 (DB-less) |
| Message Broker | RabbitMQ 3 |
| Database | Supabase (PostgreSQL 15), Project ID `cpxcpvcfbohvpiubbujg` |
| Payments | Stripe |
| Email | SendGrid |
| E-Ticket | OutSystems (external route via Kong) |
| Frontend | Vue 3 + Vite |
| Containerisation | Docker + Docker Compose |

**Live database context (project `cpxcpvcfbohvpiubbujg`):**
- Core tables in active use: `users`, `events`, `seat_categories`, `seats`, `seat_holds`, `waitlist_entries`, `transactions`, `flash_sales`, `price_changes`, `payment_webhook_events`, `cancellation_requests`, `inventory_event_state`.
- All listed core tables currently have RLS enabled.

---

## 2. Architecture Overview

```
Fan UI (Vite, localhost:5173)            Organiser UI (same frontend app/routes)
              │
              └──────────────── HTTP ──────────────────┐
                                                      │
                                     ┌────────────────▼──────────────┐
                                     │        Kong API Gateway       │
                                     │  Proxy 8000 / Admin 8001      │
                                     └────────────────┬───────────────┘
                                                      │
                           ┌──────────────────────────┼──────────────────────────┐
                           │                          │                          │
                   ┌───────▼────────┐        ┌────────▼─────────┐      ┌────────▼─────────┐
                   │ Reservation     │        │ Booking Status   │      │ Flash Sale       │
                   │ Orchestrator    │        │ Service          │      │ Orchestrator     │
                   │ (6001 -> 5000)  │        │ (6002 -> 5000)   │      │ (6003 -> 5000)   │
                   └───────┬─────────┘        └────────┬─────────┘      └────────┬─────────┘
                           │                           │                         │
                   ┌───────▼───────────────────────────▼─────────────────────────▼───────┐
                   │                         Atomic Services (HTTP)                         │
                   │ event(5001) user(127.0.0.1:5002) inventory(5003) payment(5004)      │
                   │ waitlist(5005) pricing(5006)                                          │
                   └───────────────────────────────┬───────────────────────────────────────┘
                                                   │
                                             AMQP  │
                                                   ▼
                                           RabbitMQ (5672/15672)
                                                   │
                 ┌─────────────────────────────────┼─────────────────────────────────┐
                 │                                 │                                 │
                 ▼                                 ▼                                 ▼
        notification-service            booking-fulfillment-orch.         pricing-orchestrator
        waitlist-promotion-orch.        expiry-scheduler-service          cancellation-orchestrator (HTTP 6004)
```

**Communication rules:**
- UI → Kong → public routes only.
- Composite/orchestrators → atomic services via Docker DNS (for example `http://user-service:5000`).
- Services publish/consume async events through RabbitMQ exchanges (`ticketblitz`, `ticketblitz.price`).
- `user-service` host exposure is localhost-only (`127.0.0.1:5002:5000`) for safer local debugging.

---

## 3. Two-Week Development Timeline

> Starting date: **1 April 2026**

### Week 1 — Foundation & Scenario 1

| Day | Date | Goal | Who |
|---|---|---|---|
| 1 | Tue 1 Apr | Repo setup, shared utilities (`backend/shared/db.py`, `backend/shared/mq.py`), `/health` on every service | All |
| 2 | Wed 2 Apr | Event Service + User Service (atomic) | Brandon |
| 2 | Wed 2 Apr | Inventory Service (atomic) | Shirin |
| 2 | Wed 2 Apr | Payment Service + Stripe integration (atomic) | Boone |
| 3 | Thu 3 Apr | Waitlist Service (atomic) | Jie Ching |
| 3 | Thu 3 Apr | Notification Service (atomic worker) | Ian |
| 4 | Fri 4 Apr | Atomic integration test — all services healthy via `docker compose ps` | All |
| 5 | Sat 5 Apr | Reservation Orchestrator + Booking Status Service | Brandon + Shirin |
| 6 | Sun 6 Apr | Booking Fulfillment + Waitlist Promotion workers | Brandon + Jie Ching |
| 7 | Mon 7 Apr | Expiry Scheduler + Scenario 1 E2E validation | All |

### Week 2 — UI, Scenarios 2 & 3, Demo

| Day | Date | Goal | Who |
|---|---|---|---|
| 8 | Tue 8 Apr | Fan-facing UI pages and booking states | Brandon + Boone |
| 8 | Tue 8 Apr | Flash Sale + Pricing orchestration flow | Mik |
| 9 | Wed 9 Apr | Cancellation orchestration flow | Shirin |
| 9 | Wed 9 Apr | Organiser controls for status/price/flash sale | Boone |
| 10 | Thu 10 Apr | Scenario 2 E2E validation | Mik |
| 10 | Thu 10 Apr | Scenario 3 E2E validation | Shirin |
| 11 | Fri 11 Apr | Full integration (Scenarios 1-3) | All |
| 12 | Sat 12 Apr | Bug fixes and edge cases | All |
| 13 | Sun 13 Apr | Demo recording + README finalization | All |
| 14 | Mon 14 Apr | **SUBMISSION DEADLINE** | All |

---

## 4. Service Build Sequence

Build in dependency order. Do not bring Kong up before upstream HTTP services are healthy.

```
Phase 1 — Shared Foundations
  └── backend/shared/db.py + backend/shared/mq.py + shared OpenAPI helper

Phase 2 — Atomic HTTP Services
  ├── 1. event-service
  ├── 2. user-service
  ├── 3. inventory-service
  ├── 4. payment-service
  ├── 5. waitlist-service
  └── 6. pricing-service

Phase 3 — Atomic Workers
  └── 7. notification-service

Phase 4 — Composite HTTP
  ├── 8. reservation-orchestrator
  ├── 9. booking-status-service
  ├── 10. flash-sale-orchestrator
  └── 11. cancellation-orchestrator

Phase 5 — Composite Workers
  ├── 12. booking-fulfillment-orchestrator
  ├── 13. waitlist-promotion-orchestrator
  ├── 14. pricing-orchestrator
  └── 15. expiry-scheduler-service

Phase 6 — Gateway + Frontend
  ├── 16. kong
  └── 17. frontend (run locally with Vite)
```

Within each HTTP service, follow:
1. `/health`
2. Read endpoints
3. Write endpoints
4. Error handling
5. OpenAPI (service-specific docs route; see section 13.3 for each service)
6. Container build and health check
7. Kong route validation

---

## 5. Prerequisites Check

Run in **Terminal (macOS)** or **PowerShell (Windows)**.

```bash
docker --version
docker compose version
git --version
python3 --version
node --version
npm --version
code --version
```

Recommended versions:
- Docker Desktop 4.x+
- Compose v2.x+
- Python 3.11+
- Node `^20.19.0 || >=22.12.0` (matches frontend `engines`)

---

## 6. Clone the Repository

```bash
git clone https://github.com/<your-org>/ticketblitz.git
cd ticketblitz
```

Confirm the top-level structure before continuing:

```
ticketblitz/
├── docker-compose.yml
├── .env.local
├── .dockerignore
├── .gitignore
├── backend/
│   ├── atomic/
│   │   ├── event-service/
│   │   ├── user-service/
│   │   ├── inventory-service/
│   │   ├── payment-service/
│   │   ├── waitlist-service/
│   │   ├── pricing-service/
│   │   ├── notification-service/
│   │   └── expiry-scheduler-service/
│   ├── composite/
│   │   ├── reservation-orchestrator/
│   │   ├── booking-status-service/
│   │   ├── booking-fulfillment-orchestrator/
│   │   ├── waitlist-promotion-orchestrator/
│   │   ├── pricing-orchestrator/
│   │   ├── flash-sale-orchestrator/
│   │   └── cancellation-orchestrator/
│   └── shared/
├── kong/
│   └── kong.yml
├── database/
├── docs/
└── frontend/
```

---

## 7. Environment Variables

All backend services load from root `.env.local`.

### 7.1 — Source of truth

The current compose file uses:

```yaml
env_file:
  - .env.local
```

If `.env.local` is missing on a new machine, create it manually from the template below.

### 7.2 — Required baseline keys

```env
# Supabase
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>

# RabbitMQ
RABBITMQ_USER=ticketblitz
RABBITMQ_PASSWORD=<your-password>
RABBITMQ_URL=amqp://ticketblitz:<your-password>@rabbitmq:5672/

# Stripe
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=

# SendGrid
SENDGRID_API_KEY=SG....
SENDGRID_FROM_EMAIL=noreply@ticketblitz.com
SENDGRID_TEMPLATE_BOOKING_CONFIRMED=d-...
SENDGRID_TEMPLATE_WAITLIST_JOINED=d-...
SENDGRID_TEMPLATE_SEAT_AVAILABLE=d-...
SENDGRID_TEMPLATE_HOLD_EXPIRED=d-...

# OutSystems
OUTSYSTEMS_BASE_URL=https://<your-env>.outsystemscloud.com

# Internal service URLs
EVENT_SERVICE_URL=http://event-service:5000
USER_SERVICE_URL=http://user-service:5000
INVENTORY_SERVICE_URL=http://inventory-service:5000
PAYMENT_SERVICE_URL=http://payment-service:5000
WAITLIST_SERVICE_URL=http://waitlist-service:5000
PRICING_SERVICE_URL=http://pricing-service:5000
FLASH_SALE_ORCHESTRATOR_URL=http://flash-sale-orchestrator:5000

# Internal auth
REQUIRE_INTERNAL_AUTH=1
INTERNAL_SERVICE_TOKEN=ticketblitz-internal-token
USER_SERVICE_AUTH_HEADER=X-Internal-Token
WAITLIST_SERVICE_AUTH_HEADER=X-Internal-Token
INTERNAL_AUTH_HEADER=X-Internal-Token

# Flask / scheduler
FLASK_ENV=development
FLASK_DEBUG=0
EXPIRY_INTERVAL_SECONDS=60
```

### 7.3 — Compose-level optional tuning keys (have defaults in `docker-compose.yml`)

`HTTP_TIMEOUT_SECONDS`, `HTTP_MAX_RETRIES`, `REQUIRE_AUTHENTICATED_USER_HEADER`, `AUTHENTICATED_USER_HEADER`, `FALLBACK_AUTHENTICATED_USER_HEADERS`, `CORS_ALLOWED_ORIGINS`, `WAITLIST_PROMOTION_*`, `FLASH_SALE_RECONCILE_*`, `EXPIRY_ERROR_RETRY_*`, `BOOKING_INCIDENT_EMAIL`.

### 7.4 — Security note

`STRIPE_WEBHOOK_SECRET` changes every time `stripe listen` starts. Always update `.env.local` and recreate `payment-service` so the new environment value is loaded.

---

## 8. Option A — Local Python Virtual Environment

Use this for debugging a single service locally while infra remains in Docker.

### 8.1 — Start infrastructure in Docker

```bash
docker compose --env-file .env.local up rabbitmq -d
docker compose ps rabbitmq
```

### 8.2 — Create venv (example: user-service)

**macOS:**
```bash
cd backend/atomic/user-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 8.3 — Set local env for direct run

```bash
export PYTHONPATH="$(cd ../.. && pwd)"
export SUPABASE_URL="https://<project-ref>.supabase.co"
export SUPABASE_SERVICE_KEY="<service-role-key>"
export RABBITMQ_URL="amqp://ticketblitz:<password>@localhost:5672/"
export REQUIRE_INTERNAL_AUTH=1
export INTERNAL_SERVICE_TOKEN="ticketblitz-internal-token"
export PORT=5002
```

### 8.4 — Run the service

```bash
python user.py
```

Use the service entry file for each module:
- event-service: `event.py`
- inventory-service: `inventory.py`
- payment-service: `payment.py`
- waitlist-service: `waitlist.py`
- reservation-orchestrator: `app.py`

---

## 9. Option B — Docker (Primary Workflow)

This is the standard workflow for integration testing.

### 9.1 — Project Dockerfiles

Each service has its own Dockerfile. There is no shared `docker/Dockerfile.flask` in this repository.

Pattern used by HTTP services:
- Base: `python:3.11-slim`
- `PYTHONPATH=/app/backend`
- Install `curl` for healthcheck
- Run as non-root `appuser`
- `CMD` points to service-specific file (for example `python backend/atomic/event-service/event.py`)

Pattern used by workers:
- Same Python base and `PYTHONPATH`
- No `curl` install
- No HTTP port exposure

### 9.2 — `.dockerignore`

Current root `.dockerignore`:

```
__pycache__/
*.pyc
*.pyo
*.pytest_cache/
.coverage
htmlcov/
.env
.env.*
!.env.example
.git/
.gitignore
.vscode/
.idea/
node_modules/
frontend/node_modules/
frontend/dist/
backend/**/.venv/
.DS_Store
```

### 9.3 — `docker-compose.yml`

Important characteristics in the current compose file:
- Build context is root `.` for every service.
- `dockerfile` points to service-local Dockerfiles under `backend/...`.
- Services load `.env.local`.
- Kong starts only after critical upstreams are healthy.

Representative example:

```yaml
event-service:
  build:
    context: .
    dockerfile: backend/atomic/event-service/Dockerfile
  env_file:
    - .env.local
  environment:
    PORT: "5000"
    SERVICE_NAME: event-service
  depends_on:
    rabbitmq:
      condition: service_healthy
  ports:
    - "5001:5000"
```

### 9.4 — Port Reference

| Service | Host Port(s) | Internal Port(s) | Purpose |
|---|---|---|---|
| rabbitmq | 5672, 15672 | 5672, 15672 | Broker + Management UI |
| event-service | 5001 | 5000 | Atomic API |
| user-service | 127.0.0.1:5002 | 5000 | Local/internal API |
| inventory-service | 5003 | 5000 | Atomic API |
| payment-service | 5004 | 5000 | Atomic API |
| waitlist-service | 5005 | 5000 | Atomic API |
| notification-service | None | None | Worker (no published HTTP/AMQP port) |
| booking-status-service | 6002 | 5000 | Composite API |
| waitlist-promotion-orchestrator | None | None | Worker (no published HTTP/AMQP port) |
| cancellation-orchestrator | 6004 | 5000 | Composite API |
| expiry-scheduler-service | None | None | Worker (no published HTTP/AMQP port) |
| pricing-service | 5006 | 5000 | Atomic API |
| flash-sale-orchestrator | 6003 | 5000 | Composite API |
| pricing-orchestrator | None | None | Worker (no published HTTP/AMQP port) |
| booking-fulfillment-orchestrator | None | None | Worker (no published HTTP/AMQP port) |
| reservation-orchestrator | 6001 | 5000 | Composite API |
| kong | 8000, 8001 | 8000, 8001 | API proxy + admin API |

### 9.5 — First-time build

```bash
docker compose --env-file .env.local up -d --build
```

### 9.6 — Subsequent starts

```bash
# Start existing images
docker compose --env-file .env.local up -d

# Recommended after code changes (avoids stale images)
docker compose --env-file .env.local up -d --build <service-name>
```

---

## 10. Stripe CLI Setup

### 10.1 — Install (macOS)

```bash
brew install stripe/stripe-cli/stripe
stripe --version
```

### 10.2 — Login

```bash
stripe login
```

### 10.3 — Start forwarding

```bash
stripe listen --forward-to localhost:8000/payment/webhook
```

### 10.4 — Update `.env.local` and recreate payment service

```env
STRIPE_WEBHOOK_SECRET=whsec_...
```

```bash
docker compose up -d --force-recreate --no-deps payment-service
```

### 10.5 — Trigger tests

```bash
stripe trigger payment_intent.succeeded
stripe trigger payment_intent.payment_failed
docker compose logs -f payment-service
```

---

## 11. RabbitMQ Exchange Setup

Exchanges persist in `rabbitmq-data` volume unless you run `docker compose down -v`.

### 11.1 — Ensure RabbitMQ healthy

```bash
docker compose up rabbitmq -d
docker compose ps rabbitmq
```

### 11.2 — Create exchanges

Create both exchanges:

| Exchange Name | Type | Durable | Use |
|---|---|---|---|
| `ticketblitz` | topic | Yes | Booking, seat release, notifications |
| `ticketblitz.price` | fanout | Yes | Flash sale pricing broadcasts |

### 11.3 — API commands

```bash
curl -u "$RABBITMQ_USER:$RABBITMQ_PASSWORD" \
  -X PUT http://localhost:15672/api/exchanges/%2F/ticketblitz \
  -H "Content-Type: application/json" \
  -d '{"type":"topic","durable":true}'

curl -u "$RABBITMQ_USER:$RABBITMQ_PASSWORD" \
  -X PUT http://localhost:15672/api/exchanges/%2F/ticketblitz.price \
  -H "Content-Type: application/json" \
  -d '{"type":"fanout","durable":true}'
```

### 11.4 — Binding keys reference

| Binding Key | Exchange | Published by | Consumed by |
|---|---|---|---|
| `booking.confirmed` | `ticketblitz` | payment-service | booking-fulfillment-orchestrator |
| `seat.released` | `ticketblitz` | inventory-service | waitlist-promotion-orchestrator |
| `notification.send` | `ticketblitz` | orchestrators/services | notification-service |
| `price.broadcast` | `ticketblitz.price` | flash/pricing flows | price consumers/UI channels |

---

## 12. Kong API Gateway

Kong runs DB-less and loads all config from `kong/kong.yml`.

### 12.1 — Authentication model

- Customer routes (`/reserve`, `/reserve/confirm`, `/waitlist/confirm`) use `key-auth` with header `x-customer-api-key`.
- Organiser routes (`/event/.../status`, `/event/.../categories/prices`, `/flash-sale/launch`, `/flash-sale/end`) use `x-organiser-api-key` and ACL group `organisers`.
- Consumers configured:
  - `customer-frontend` key: `ticketblitz-customer-dev-key`
  - `organiser-dashboard` key: `ticketblitz-organiser-dev-key`

### 12.2 — Exposed route groups

- Reservation: `/reserve`, `/reserve/confirm`, `/waitlist/confirm`
- Event: `/events`, `/event/{id}`, `/event/{id}/categories`, `/event/{id}/flash-sale/status`, `/event/{id}/price-history`, organiser write endpoints
- Waitlist: `/waitlist` (GET/POST/PUT/DELETE)
- Inventory: `/inventory` (GET)
- Booking status: `/booking-status/{holdID}`
- Cancellation: `/bookings/cancel/{bookingID}`, `/orchestrator/cancellation`, `/orchestrator/cancellation/reallocation/confirm`
- Pricing: `/pricing/{eventID}`, `/pricing/{eventID}/history`, `/pricing/{eventID}/flash-sale/active`
- Flash sale: `/flash-sale/launch`, `/flash-sale/end`, `/flash-sale/{eventID}/status`
- Payment webhook: `/payment/webhook`
- External e-ticket proxy: `/eticket/generate`

### 12.3 — Reload Kong config

```bash
curl -X POST http://localhost:8001/config -F config=@kong/kong.yml
```

---

## 13. Verify the Full Stack

### 13.1 — Container health

```bash
docker compose ps
docker compose ps --format "table {{.Names}}\t{{.Status}}"
```

Workers should show `running` (without health check), HTTP services should reach `healthy`.

### 13.2 — Core smoke tests through Kong

```bash
# Public events endpoint
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/events

# Reservation requires customer key + authenticated user header
curl -i -X POST http://localhost:8000/reserve \
  -H "Content-Type: application/json" \
  -H "x-customer-api-key: ticketblitz-customer-dev-key" \
  -H "X-User-ID: 00000000-0000-0000-0000-000000000001" \
  -d '{
    "userID": "00000000-0000-0000-0000-000000000001",
    "eventID": "00000000-0000-0000-0000-000000000001",
    "seatCategory": "CAT1",
    "qty": 1
  }'
```

### 13.3 — API docs access points

| Service | URL |
|---|---|
| Event Service docs | http://localhost:5001/apidocs/ |
| User Service docs | http://localhost:5002/docs |
| Inventory Service docs | http://localhost:5003/inventory/docs/ |
| Payment Service docs | http://localhost:5004/docs |
| Waitlist Service docs | http://localhost:5005/docs |
| Reservation Orchestrator docs | http://localhost:6001/docs |
| Booking Status docs | http://localhost:6002/docs |
| Cancellation docs | http://localhost:6004/docs |
| Kong Admin API | http://localhost:8001 |
| RabbitMQ UI | http://localhost:15672 |

### 13.4 — Supabase sanity checks (project `cpxcpvcfbohvpiubbujg`)

```sql
select table_name
from information_schema.tables
where table_schema = 'public'
order by table_name;
```

Expected operational tables include:
`events`, `seat_categories`, `seats`, `seat_holds`, `waitlist_entries`, `transactions`, `flash_sales`, `price_changes`, `payment_webhook_events`, `cancellation_requests`.

---

## 14. Daily Development Workflow

### Starting your session

```bash
# 1. Pull latest
git pull

# 2. Start backend stack
docker compose --env-file .env.local up -d --build

# 3. In separate terminal: Stripe webhook forwarder
stripe listen --forward-to localhost:8000/payment/webhook

# 4. Update STRIPE_WEBHOOK_SECRET in .env.local
# 5. Recreate payment-service to load updated env vars
docker compose up -d --force-recreate --no-deps payment-service

# 6. Verify status
docker compose ps
```

### Frontend workflow (local)

```bash
cd frontend
npm install
npm run dev
```

Default Vite URL is usually `http://localhost:5173`.

### Making backend code changes

```bash
docker compose --env-file .env.local up -d --build <service-name>
docker compose logs -f <service-name>
```

### Ending your session

```bash
docker compose down
```

Full reset (wipes RabbitMQ volume):

```bash
docker compose down -v
```

---

## 15. Writing a Service — Standard Template

### Flask service pattern

```python
import os
import logging
from flask import Flask, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.get("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": os.getenv("SERVICE_NAME", "unknown")
    }), 200

@app.errorhandler(404)
def not_found(_):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.exception("Unhandled error: %s", e)
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
```

### Shared Supabase helper

Use `backend/shared/db.py` and import as:

```python
from shared.db import get_db
```

This works in containers because Dockerfiles set:

```dockerfile
ENV PYTHONPATH=/app/backend
```

### Worker pattern

Workers should:
- Declare/bind queue(s) and exchange(s)
- Use manual ACK/NACK
- Handle `SIGTERM` for clean container shutdown
- Log correlation IDs for tracing across services

---

## 16. Useful Commands Reference

### Container management

```bash
docker compose ps
docker compose logs -f <service-name>
docker compose logs --tail=100 <service-name>
docker compose --env-file .env.local up -d --build <service-name>
docker compose restart <service-name>
docker compose exec <service-name> /bin/bash
docker compose down
docker compose down -v
```

### Stripe

```bash
stripe listen --forward-to localhost:8000/payment/webhook
stripe trigger payment_intent.succeeded
stripe trigger payment_intent.payment_failed
```

### RabbitMQ

```bash
docker compose exec rabbitmq rabbitmqctl list_queues
docker compose exec rabbitmq rabbitmqctl list_exchanges
docker compose exec rabbitmq rabbitmqctl purge_queue <queue-name>
docker compose exec rabbitmq rabbitmq-diagnostics -q ping
```

### Kong

```bash
curl http://localhost:8001/services
curl http://localhost:8001/routes
curl -X POST http://localhost:8001/config -F config=@kong/kong.yml
```

### Environment debugging

```bash
docker compose config --environment
```

---

## 17. Troubleshooting

### Service keeps restarting or unhealthy

```bash
docker compose logs <service-name>
```

Common causes:
- Missing `.env.local` values
- Dependency not healthy yet
- Supabase key/url mismatch

### RabbitMQ auth failures (`ACCESS_REFUSED`)

```bash
docker exec ticketblitz-rabbitmq rabbitmqctl authenticate_user "$RABBITMQ_USER" "$RABBITMQ_PASSWORD"
```

### Kong returns 503

```bash
docker compose ps
docker compose up -d --build <downstream-service>
```

### Stripe webhook signature mismatch

`STRIPE_WEBHOOK_SECRET` is stale. Restart `stripe listen`, update `.env.local`, then recreate `payment-service` (`docker compose up -d --force-recreate --no-deps payment-service`).

### Frontend cannot call `/reserve` through Kong

Check all of the following:
1. Request includes `x-customer-api-key`.
2. Request includes `X-User-ID` (or configured fallback authenticated-user header).
3. If browser preflight fails, verify CORS allowed headers in `kong/kong.yml` include required custom headers.

### Compose dependency expectations

With `depends_on: condition: service_healthy`, Compose waits for dependency health during startup creation order, but manual restarts still require you to restart dependent services if upstreams changed.

### Env interpolation confusion

Use:

```bash
docker compose config --environment
```

This prints effective interpolation sources and values used by Compose.

### Stale images after code edits

```bash
docker compose --env-file .env.local up -d --build <service-name>
```

### Port already in use

```bash
lsof -i :8000
kill -9 <PID>
```

### Exchange missing after reset

If you ran `docker compose down -v`, recreate `ticketblitz` and `ticketblitz.price` exchanges (Section 11).

### Local import errors for `shared.*`

Set `PYTHONPATH` to the `backend` directory before running services outside Docker.

---

*End of guide. Default debugging entrypoint: `docker compose logs <service-name>` and `docker compose config --environment`.*
