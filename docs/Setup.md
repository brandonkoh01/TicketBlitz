# TicketBlitz — Project Setup Guide


## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Architecture Overview](#2-architecture-overview)
3. [Prerequisites Check](#3-prerequisites-check)
4. [Clone the Repository](#4-clone-the-repository)
5. [Environment Variables](#5-environment-variables)
6. [Option B — Docker (Primary Workflow)](#6-option-b--docker-primary-workflow)
7. [Option A — Local Python Virtual Environment](#7-option-a--local-python-virtual-environment)
8. [Stripe CLI Setup](#8-stripe-cli-setup)
9. [RabbitMQ Exchange Setup](#9-rabbitmq-exchange-setup)
10. [Kong API Gateway](#10-kong-api-gateway)
11. [Verify the Full Stack](#11-verify-the-full-stack)
12. [Development Workflow](#12-development-workflow)
13. [Useful Commands Reference](#13-useful-commands-reference)
14. [Troubleshooting](#14-troubleshooting)

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
| API Gateway | Kong   |
| Message Broker | RabbitMQ 3 |
| Database | Supabase (PostgreSQL 15) |
| Payments | Stripe |
| Email | SendGrid |
| E-Ticket | OutSystems (external route via Kong) |
| Frontend | Vue 3 + Vite |
| Containerisation | Docker + Docker Compose |

---

## 2. Architecture Overview

![SOA](./images/SOA.png "SOA")

**Communication rules:**
- UI → Kong → public routes only.
- Composite/orchestrators → atomic services via Docker DNS (for example `http://user-service:5000`).
- Services publish/consume async events through RabbitMQ exchanges (`ticketblitz`, `ticketblitz.price`).

---

## 3. Prerequisites Check

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

## 4. Clone the Repository

```bash
git clone https://github.com/brandonkoh01/ticketblitz.git
cd ticketblitz
```
---

## 5. Environment Variables

All backend services load from root `.env.local`.

### 5.1 — Source of truth

The current compose file uses:

```yaml
env_file:
  - .env.local
```

If `.env.local` is missing on a new machine, create it manually from the template below.

### 5.2 — Required baseline keys

```env
# Supabase
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_KEY=<service-role-key>

# RabbitMQ
RABBITMQ_USER=ticketblitz
RABBITMQ_PASSWORD=123
RABBITMQ_URL=amqp://ticketblitz:123@rabbitmq:5652/
# ↑ Uses Docker DNS "rabbitmq". For local venv outside Docker:
#   RABBITMQ_URL=amqp://ticketblitz:123@localhost:5652/

# ── Stripe ───────────────────────────────────────────────────
# Dashboard → Developers → API keys
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=

# SendGrid
SENDGRID_API_KEY=SG....
SENDGRID_FROM_EMAIL=noreply@ticketblitz.com
SENDGRID_TEMPLATE_BOOKING_CONFIRMED=d-...
SENDGRID_TEMPLATE_WAITLIST_JOINED=d-...
SENDGRID_TEMPLATE_SEAT_AVAILABLE=d-...
SENDGRID_TEMPLATE_HOLD_EXPIRED=d-...
SENDGRID_TEMPLATE_FLASH_SALE_LAUNCHED=d-...
SENDGRID_TEMPLATE_PRICE_ESCALATED=d-...
SENDGRID_TEMPLATE_FLASH_SALE_ENDED=d-...

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

### 5.3 — Compose-level optional tuning keys (have defaults in `docker-compose.yml`)

`HTTP_TIMEOUT_SECONDS`, `HTTP_MAX_RETRIES`, `REQUIRE_AUTHENTICATED_USER_HEADER`, `AUTHENTICATED_USER_HEADER`, `FALLBACK_AUTHENTICATED_USER_HEADERS`, `CORS_ALLOWED_ORIGINS`, `WAITLIST_PROMOTION_*`, `FLASH_SALE_RECONCILE_*`, `EXPIRY_ERROR_RETRY_*`, `BOOKING_INCIDENT_EMAIL`.

### 5.4 — Security note

`STRIPE_WEBHOOK_SECRET` changes every time `stripe listen` starts. Always update `.env.local` and recreate `payment-service` so the new environment value is loaded.

---
## 6. Option B — Docker (Primary Workflow)

This is the standard workflow for integration testing.

### 6.1 — Project Dockerfiles

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

### 6.2 — `.dockerignore`

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

### 6.3 — `docker-compose.yml`

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

### 6.4 — Port Reference

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

### 6.5 — First-time build

```bash
docker compose --env-file .env.local up -d --build
```

### 6.6 — Subsequent starts

```bash
# Start existing images
docker compose --env-file .env.local up -d

# Recommended after code changes (avoids stale images)
docker compose --env-file .env.local up -d --build <service-name>
```

---

## 7. Option A — Local Python Virtual Environment

Use this for debugging a single service locally while infra remains in Docker.

### 7.1 — Start infrastructure in Docker

```bash
docker compose --env-file .env.local up rabbitmq -d
docker compose ps rabbitmq
```

### 7.2 — Create venv (example: user-service)

**macOS:**
```bash
cd backend/atomic/user-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 7.3 — Set local env for direct run

```bash
export SUPABASE_URL="https://your-project-ref.supabase.co"
export SUPABASE_SERVICE_KEY="eyJ..."
export RABBITMQ_URL="amqp://ticketblitz:123@localhost:5672/"
export REQUIRE_INTERNAL_AUTH=1
export INTERNAL_SERVICE_TOKEN="ticketblitz-internal-token"
export PORT=5002
```

**Windows (PowerShell):**
```powershell
$env:SUPABASE_URL="https://your-project-ref.supabase.co"
$env:SUPABASE_SERVICE_KEY="eyJ..."
$env:RABBITMQ_URL="amqp://ticketblitz:123@localhost:5672/"
$env:REQUIRE_INTERNAL_AUTH="1"
$env:INTERNAL_SERVICE_TOKEN="ticketblitz-internal-token"
$env:PORT=5002
```

> 💡 Tip: Create a `dev.sh` (macOS) or `dev.ps1` (Windows) file in each service  
> directory with these exports pre-filled. Add `dev.sh` and `dev.ps1` to `.gitignore`.

### 7.4 — Run the service

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

## 8. Stripe CLI Setup

### 8.1 — Install (macOS)

```bash
brew install stripe/stripe-cli/stripe
stripe --version
```

### 8.2 — Login

```bash
stripe login
```

### 8.3 — Start forwarding

```bash
stripe listen --forward-to localhost:8000/payment/webhook
```

### 8.4 — Update `.env.local` and recreate payment service

```env
STRIPE_WEBHOOK_SECRET=whsec_...
```

```bash
docker compose up -d --force-recreate --no-deps payment-service
```

### 8.5 — Trigger tests

```bash
stripe trigger payment_intent.succeeded
stripe trigger payment_intent.payment_failed
docker compose logs -f payment-service
```

---

## 9. RabbitMQ Exchange Setup

Exchanges persist in `rabbitmq-data` volume unless you run `docker compose down -v`.

### 9.1 — Ensure RabbitMQ healthy

```bash
docker compose up rabbitmq -d
docker compose ps rabbitmq
```

### 9.2 — Create exchanges via the Management UI

Go to: **http://localhost:15672**  
Login: username `ticketblitz` / password `123`

Create both exchanges:

| Exchange Name | Type | Durable | Use |
|---|---|---|---|
| `ticketblitz` | topic | Yes | Booking, seat release, notifications |
| `ticketblitz.price` | fanout | Yes | Flash sale pricing broadcasts |

### 9.3 — API commands

```bash
curl -u ticketblitz:123 \
  -X PUT http://localhost:15672/api/exchanges/%2F/ticketblitz \
  -H "Content-Type: application/json" \
  -d '{"type":"topic","durable":true}'

curl -u ticketblitz:123 \
  -X PUT http://localhost:15672/api/exchanges/%2F/ticketblitz.price \
  -H "Content-Type: application/json" \
  -d '{"type":"fanout","durable":true}'
```

**Windows (PowerShell):**
```powershell
$headers = @{
  Authorization = "Basic " + [Convert]::ToBase64String(
    [Text.Encoding]::ASCII.GetBytes("ticketblitz:123"))
  "Content-Type" = "application/json"
}

Invoke-RestMethod -Method Put -Uri "http://localhost:15672/api/exchanges/%2F/ticketblitz" `
  -Headers $headers -Body '{"type":"topic","durable":true}'

Invoke-RestMethod -Method Put -Uri "http://localhost:15672/api/exchanges/%2F/ticketblitz.price" `
  -Headers $headers -Body '{"type":"fanout","durable":true}'
```

### 9.4 — RabbitMQ Binding Keys Reference

| Binding Key | Exchange | Published by | Consumed by |
|---|---|---|---|
| `booking.confirmed` | `ticketblitz` | payment-service | booking-fulfillment-orchestrator |
| `seat.released` | `ticketblitz` | inventory-service | waitlist-promotion-orchestrator |
| `notification.send` | `ticketblitz` | orchestrators/services | notification-service |
| `price.broadcast` | `ticketblitz.price` | flash/pricing flows | price consumers/UI channels |

---

## 10. Kong API Gateway

Kong runs DB-less and loads all config from `kong/kong.yml`.

### 10.1 — Authentication model

- Customer routes (`/reserve`, `/reserve/confirm`, `/waitlist/confirm`) use `key-auth` with header `x-customer-api-key`.
- Organiser routes (`/event/.../status`, `/event/.../categories/prices`, `/flash-sale/launch`, `/flash-sale/end`) use `x-organiser-api-key` and ACL group `organisers`.
- Consumers configured:
  - `customer-frontend` key: `ticketblitz-customer-dev-key`
  - `organiser-dashboard` key: `ticketblitz-organiser-dev-key`

### 10.2 — Exposed route groups

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

### 10.3 — Reload Kong config

```bash
curl -X POST http://localhost:8001/config -F config=@kong/kong.yml
```

---

## 11. Verify the Full Stack

### 11.1 — Container health

```bash
docker compose ps
docker compose ps --format "table {{.Names}}\t{{.Status}}"
```

Workers should show `running` (without health check), HTTP services should reach `healthy`.

### 11.2 — API docs access points

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



---

## 12. Development Workflow

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

## 13. Useful Commands Reference

### Container management

```bash
docker compose ps
docker compose logs -f <service-name>
docker compose logs --tail=80 <service-name>
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

## 14. Troubleshooting

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

If you ran `docker compose down -v`, recreate `ticketblitz` and `ticketblitz.price` exchanges (Section 9).

### Local import errors for `shared.*`

Set `PYTHONPATH` to the `backend` directory before running services outside Docker.

---

*End of guide. Default debugging entrypoint: `docker compose logs <service-name>` and `docker compose config --environment`.*
