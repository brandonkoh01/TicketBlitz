# TicketBlitz — Complete Project Setup & Development Guide

> **For:** All team members  
> **Updated:** 2026-03-31  
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
| **Scenario 3** | Fan cancels a booking — SAGA-based rollback of payment, inventory, and e-ticket |

**Tech Stack at a glance:**

| Layer | Technology |
|---|---|
| Language & Framework | Python 3 + Flask |
| API Gateway | Kong Gateway 3.9 (DB-less) |
| Message Broker | RabbitMQ 3 |
| Database | Supabase (PostgreSQL 15) |
| Payments | Stripe |
| Email | SendGrid |
| E-Ticket | OutSystems (external, not in Docker) |
| Containerisation | Docker + Docker Compose |

---

## 2. Architecture Overview

```
Fan Booking UI (port 3000)           Organiser Dashboard UI (port 3001)
        │                                          │
        └──────────────── HTTP ────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │   Kong API Gateway     │  ← All user-facing traffic enters here
                    │       port 8000        │    (Rate limiting, auth, routing)
                    └───────────┬───────────┘
                                │ HTTP routes to composites
          ┌─────────────────────┼──────────────────────┐
          │                     │                      │
  ┌───────▼──────┐   ┌──────────▼──────┐   ┌──────────▼──────┐
  │  Reservation │   │ Booking Status  │   │  Flash Sale     │
  │ Orchestrator │   │    Service      │   │  Orchestrator   │
  │  (port 6001) │   │  (port 6002)    │   │  (port 6003)    │
  └──────┬───────┘   └────────┬────────┘   └────────┬────────┘
         │                    │                     │
         │ HTTP (Docker DNS)  │                     │
         ▼                    ▼                     ▼
  ┌──────────────────────────────────────────────────────────┐
  │              Atomic Services (HTTP, Flask)                │
  │  event(5001) user(5002) inventory(5003) payment(5004)    │
  │  waitlist(5005)                                           │
  └──────────────────────────┬───────────────────────────────┘
                             │ AMQP
                    ┌────────▼────────┐
                    │   RabbitMQ      │  port 5672 (AMQP)
                    │  port 15672     │       port 15672 (Management UI)
                    └────────┬────────┘
                             │ AMQP (consumed by workers)
     ┌───────────────────────┼────────────────────┐
     │                       │                    │
     ▼                       ▼                    ▼
notification-service   booking-fulfillment   waitlist-promotion
(worker, no port)      -orchestrator         -orchestrator
                       (worker, no port)     (worker, no port)
```

**Communication rules:**
- UI → Kong → Composite services (HTTP through Kong port 8000)
- Composite → Atomic (HTTP via Docker DNS, e.g. `http://user-service:5000`, bypasses Kong)
- Atomic → RabbitMQ (AMQP publish)
- Worker services ← RabbitMQ (AMQP consume)
- Never route internal service-to-service calls through Kong

---

## 3. Two-Week Development Timeline

> Starting date: **1 April 2026**

### Week 1 — Foundation & Scenario 1

| Day | Date | Goal | Who |
|---|---|---|---|
| 1 | Tue 1 Apr | Repo setup, shared utilities (`db.py`, `mq.py`), `/health` on every service | All |
| 2 | Wed 2 Apr | Event Service + User Service (atomic) | Brandon |
| 2 | Wed 2 Apr | Inventory Service (atomic) | Shirin |
| 2 | Wed 2 Apr | Payment Service + Stripe integration (atomic) | Boone |
| 3 | Thu 3 Apr | Waitlist Service (atomic) | Jie Ching |
| 3 | Thu 3 Apr | Notification Service (atomic) | Ian |
| 4 | Fri 4 Apr | Atomic service integration test — all services healthy via `docker compose ps` | All |
| 5 | Sat 5 Apr | Reservation Orchestrator (composite HTTP, Step 1A) | Brandon + Shirin |
| 5 | Sat 5 Apr | Booking Status Service (composite HTTP) | Brandon |
| 6 | Sun 6 Apr | Booking Fulfillment Orchestrator (worker, Step 1A post-payment) | Brandon |
| 6 | Sun 6 Apr | Waitlist Promotion Orchestrator (worker, Steps 1C/1D) | Jie Ching |
| 7 | Mon 7 Apr | Expiry Scheduler Service (worker) + Scenario 1 E2E test via curl/Postman | All |

### Week 2 — UI, Scenarios 2 & 3, Demo

| Day | Date | Goal | Who |
|---|---|---|---|
| 8 | Tue 8 Apr | Fan Booking UI (all pages: browse, book, pending, confirmed, waitlist) | Brandon + Boone |
| 8 | Tue 8 Apr | Flash Sale Orchestrator (Scenario 2A + 2B) | Mik |
| 9 | Wed 9 Apr | Cancellation Orchestrator (Scenario 3) | Brandon |
| 9 | Wed 9 Apr | Organiser Dashboard UI (launch flash sale, analytics, manage events) | Boone |
| 10 | Thu 10 Apr | Scenario 2 E2E test (flash sale launch → dynamic pricing → broadcast) | Mik |
| 10 | Thu 10 Apr | Scenario 3 E2E test (cancellation SAGA rollback) | Shirin |
| 11 | Fri 11 Apr | Full integration test — all 3 scenarios back to back | All |
| 12 | Sat 12 Apr | Bug fixes, error handling polish, edge cases | All |
| 13 | Sun 13 Apr | Video demo recording (3 min max) + README.md finalization | All |
| 14 | Mon 14 Apr | **SUBMISSION DEADLINE** — slides, report, code, video on eLearn | All |

---

## 4. Service Build Sequence

Build strictly in this order. Never start a composite before all the atomics it calls are healthy.

```
Phase 1 — Infrastructure (Day 1)
  └── shared/db.py + shared/mq.py

Phase 2 — Atomic Services (Days 2-3, parallel)
  ├── 1. event-service          ← no dependencies; seed data for everyone
  ├── 2. user-service           ← no dependencies
  ├── 3. inventory-service      ← depends on event data (seed)
  ├── 4. payment-service        ← Stripe integration (takes longest)
  ├── 5. waitlist-service           ← no dependencies
  └── 6. notification-service   ← RabbitMQ consumer worker

Phase 3 — Composite Services, Scenario 1 (Days 5-7)
  ├── 7. reservation-orchestrator     ← needs user, inventory, payment, waitlist
  ├── 8. booking-status-service       ← needs inventory, payment
  ├── 9. booking-fulfillment-orch.    ← needs inventory, waitlist, RabbitMQ
  ├── 10. waitlist-promotion-orch.    ← needs inventory, waitlist, user, RabbitMQ
  └── 11. expiry-scheduler-service    ← needs inventory

Phase 4 — UI Layer (Days 8-9)
  ├── 12. fan-booking-ui
  └── 13. organiser-dashboard-ui

Phase 5 — Scenarios 2 & 3 (Days 8-9)
  ├── 14. flash-sale-orchestrator     ← needs event, inventory, waitlist, RabbitMQ
  ├── 15. pricing-orchestrator        ← needs event, RabbitMQ (fanout)
  └── 16. cancellation-orchestrator   ← needs inventory, payment, waitlist
```

Within each service, always build in this order:
1. `/health` endpoint
2. GET endpoints (read)
3. POST endpoints (create)
4. PUT endpoints (update state)
5. Error responses (400, 404, 409)
6. Docker build confirmed with `docker compose up --build`
7. Tested through Kong port 8000 (not direct port)

---

## 5. Prerequisites Check

Run in **Terminal (macOS)** or **PowerShell (Windows)**.

```bash
docker --version          # Docker Desktop 4.x+
docker compose version    # v2.x+ (note: "docker compose", not "docker-compose")
git --version             # 2.x+
python3 --version         # 3.11+ (for local venv, Option A only)
code --version            # VS Code
```

> ⚠️ **Windows:** Use **PowerShell** or **Windows Terminal**, not Command Prompt (cmd).  
> ⚠️ **macOS:** Ensure Docker Desktop is running from Applications before any `docker` command.  
> ⚠️ Use `docker compose` (v2, space) not `docker-compose` (v1, hyphen). They behave differently.

---

## 6. Clone the Repository

```bash
git clone https://github.com/<your-org>/ticketblitz.git
cd ticketblitz
```

Confirm the folder structure matches exactly before continuing:

```
ticketblitz/
├── docker-compose.yml
├── .env.example
├── .gitignore
├── .dockerignore
├── docker/
│   ├── Dockerfile.flask       ← shared template for all HTTP Flask services
│   └── Dockerfile.worker      ← shared template for all worker/consumer services
├── kong/
│   └── kong.yml               ← Kong DB-less declarative config
├── database/
│   └── ticketblitz_schema_v2.sql
├── atomic/
│   ├── shared/
│   │   ├── db.py              ← Supabase client helper (build Day 1)
│   │   ├── mq.py              ← pika RabbitMQ helper (build Day 1)
│   │   └── __init__.py
│   ├── event-service/
│   ├── user-service/
│   ├── inventory-service/
│   ├── payment-service/
│   ├── waitlist-service/
│   └── notification-service/
├── composite/
│   └── scenario-1/
│       ├── reservation-orchestrator/
│       ├── booking-fulfillment-orchestrator/
│       ├── booking-status-service/
│       ├── waitlist-promotion-orchestrator/
│       └── expiry-scheduler-service/
└── ui/
    ├── fan-booking-ui/
    └── organiser-dashboard-ui/
```

---

## 7. Environment Variables

All services share **one** root `.env` file. This is the single most important file to get right.

### 7.1 — Create your local `.env`

**macOS:**
```bash
cp .env.example .env
```

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

### 7.2 — Open in VS Code and fill in every value

```bash
code .env
```

```env
# ============================================================
# TicketBlitz — Environment Variables
# Shared by all services via env_file in docker-compose.yml
# ============================================================

# ── Supabase ─────────────────────────────────────────────────
# Dashboard → Project Settings → API
SUPABASE_URL=https://your-project-ref.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# ── RabbitMQ ─────────────────────────────────────────────────
RABBITMQ_USER=ticketblitz
RABBITMQ_PASSWORD=change_me_before_demo
RABBITMQ_URL=amqp://ticketblitz:change_me_before_demo@rabbitmq:5672/
# ↑ Uses Docker DNS "rabbitmq". For local venv outside Docker:
#   RABBITMQ_URL=amqp://ticketblitz:change_me_before_demo@localhost:5672/

# ── Stripe ───────────────────────────────────────────────────
# Dashboard → Developers → API keys
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=
# ↑ Leave blank now. Fill in AFTER running: stripe listen (Step 10)

# ── SendGrid ─────────────────────────────────────────────────
SENDGRID_API_KEY=SG....
SENDGRID_FROM_EMAIL=noreply@ticketblitz.com
SENDGRID_TEMPLATE_BOOKING_CONFIRMED=d-...
SENDGRID_TEMPLATE_WAITLIST_JOINED=d-...
SENDGRID_TEMPLATE_SEAT_AVAILABLE=d-...
SENDGRID_TEMPLATE_HOLD_EXPIRED=d-...

# ── OutSystems E-Ticket Service ──────────────────────────────
OUTSYSTEMS_BASE_URL=https://your-env.outsystemscloud.com
OUTSYSTEMS_API_KEY=your-outsystems-api-key

# ── Internal Service URLs (Docker DNS) ───────────────────────
# Used by composite services to call atomics DIRECTLY (bypass Kong)
EVENT_SERVICE_URL=http://event-service:5000
USER_SERVICE_URL=http://user-service:5000
INVENTORY_SERVICE_URL=http://inventory-service:5000
PAYMENT_SERVICE_URL=http://payment-service:5000
WAITLIST_SERVICE_URL=http://waitlist-service:5000

# ── Flask ────────────────────────────────────────────────────
FLASK_ENV=development
FLASK_DEBUG=0

# ── Internal Service Auth ────────────────────────────────────
# Used by internal-only endpoints on atomic services (for example user/waitlist)
REQUIRE_INTERNAL_AUTH=1
INTERNAL_SERVICE_TOKEN=ticketblitz-internal-token
USER_SERVICE_AUTH_HEADER=X-Internal-Token
WAITLIST_SERVICE_AUTH_HEADER=X-Internal-Token

# ── Expiry Scheduler ─────────────────────────────────────────
EXPIRY_INTERVAL_SECONDS=60
```

> ⚠️ `.env` is in `.gitignore`. Run `git status` to confirm it does **not** appear.  
> ⚠️ Never hardcode secrets inside Python files or Dockerfiles.

---

## 8. Option A — Local Python Virtual Environment

> Use this when you want to **run a single service directly on your machine** for faster  
> debugging, faster restarts, or IDE code completion. The database and RabbitMQ  
> still run in Docker.

### 8.1 — Start only infrastructure in Docker

```bash
# Start only the services that other services depend on
docker compose up rabbitmq -d
# Wait until healthy:
docker compose ps rabbitmq
```

### 8.2 — Create a virtual environment per service

Navigate to the service directory and create a venv:

**macOS:**
```bash
cd atomic/user-service
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell):**
```powershell
cd atomic\user-service
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> If PowerShell blocks script execution, run once:  
> `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

### 8.3 — Set local environment variables

When running outside Docker, the internal Docker DNS hostnames (`rabbitmq`, `user-service`) do not resolve. Override them to `localhost` for local runs.

**macOS:**
```bash
export SUPABASE_URL="https://your-project-ref.supabase.co"
export SUPABASE_SERVICE_KEY="eyJ..."
export RABBITMQ_URL="amqp://ticketblitz:change_me_before_demo@localhost:5672/"
export REQUIRE_INTERNAL_AUTH=1
export INTERNAL_SERVICE_TOKEN="ticketblitz-internal-token"
export PORT=5002
```

**Windows (PowerShell):**
```powershell
$env:SUPABASE_URL="https://your-project-ref.supabase.co"
$env:SUPABASE_SERVICE_KEY="eyJ..."
$env:RABBITMQ_URL="amqp://ticketblitz:change_me_before_demo@localhost:5672/"
$env:REQUIRE_INTERNAL_AUTH="1"
$env:INTERNAL_SERVICE_TOKEN="ticketblitz-internal-token"
$env:PORT=5002
```

> 💡 Tip: Create a `dev.sh` (macOS) or `dev.ps1` (Windows) file in each service  
> directory with these exports pre-filled. Add `dev.sh` and `dev.ps1` to `.gitignore`.

### 8.4 — Run the service

```bash
python app.py
```

The service starts on `localhost:5002` (or whatever `PORT` you set).

### 8.5 — VS Code Python configuration

Open VS Code in the service directory and select the venv interpreter:
1. `Ctrl+Shift+P` → **Python: Select Interpreter**
2. Choose `.venv/bin/python` (macOS) or `.venv\Scripts\python.exe` (Windows)

This enables IntelliSense, linting, and auto-imports for your installed packages.

### 8.6 — Minimum `requirements.txt` for every service

```txt
flask==3.1.0
flask-cors==5.0.0
supabase==2.10.0
python-dotenv==1.0.1
requests==2.32.3
```

Additional packages by service type:

| Service | Additional packages |
|---|---|
| payment-service | `stripe==11.4.0` |
| notification-service | `pika==1.3.2`, `sendgrid==6.11.0` |
| Any worker/consumer | `pika==1.3.2` |
| expiry-scheduler-service | `pika==1.3.2` |

### 8.7 — Deactivate the virtual environment

**macOS:**
```bash
deactivate
```

**Windows (PowerShell):**
```powershell
deactivate
```

---

## 9. Option B — Docker (Primary Workflow)

> This is the **standard daily workflow**. All services run in containers.  
> No local Python setup required beyond IDE support.

### 9.1 — Project Dockerfiles

**`docker/Dockerfile.flask`** — used by all HTTP Flask services:

```dockerfile
FROM python:3-slim

# Install curl for Docker healthcheck endpoint
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user for security
RUN useradd --create-home --no-log-init --shell /bin/bash appuser

WORKDIR /app

# Copy requirements first — maximises Docker layer cache.
# This layer is only rebuilt when requirements.txt changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

USER appuser

EXPOSE 5000

STOPSIGNAL SIGTERM

# app.py must read PORT from environment:
# port = int(os.environ.get("PORT", 5000))
# app.run(host="0.0.0.0", port=port)
CMD ["python", "app.py"]
```

**`docker/Dockerfile.worker`** — used by all worker/consumer services:

```dockerfile
FROM python:3-slim

# No curl needed — workers have no HTTP endpoint to health-check
RUN useradd --create-home --no-log-init --shell /bin/bash appuser

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

USER appuser

STOPSIGNAL SIGTERM

# worker.py must handle SIGTERM gracefully for clean shutdown:
# import signal
# signal.signal(signal.SIGTERM, lambda sig, frame: sys.exit(0))
CMD ["python", "worker.py"]
```

### 9.2 — `.dockerignore`

Place this file in the project root to keep images lean:

```
__pycache__/
*.pyc
*.pyo
.env
.env.*
!.env.example
*.egg-info/
dist/
build/
.pytest_cache/
.coverage
htmlcov/
.git/
.gitignore
README.md
docs/
.DS_Store
Thumbs.db
.vscode/
.idea/
docker-compose.yml
docker-compose.*.yml
Dockerfile*
dev.sh
dev.ps1
.venv/
```

### 9.3 — `docker-compose.yml`

Place in the project root:

```yaml
name: ticketblitz

services:

  # ── Infrastructure ────────────────────────────────────────

  rabbitmq:
    image: rabbitmq:3-management-alpine
    container_name: ticketblitz-rabbitmq
    restart: on-failure
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_USER}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_PASSWORD}
    ports:
      - "5672:5672"     # AMQP
      - "15672:15672"   # Management UI → http://localhost:15672
    volumes:
      - rabbitmq-data:/var/lib/rabbitmq
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    networks:
      - ticketblitz-net

  kong:
    image: kong/kong-gateway:3.9
    container_name: ticketblitz-kong
    restart: on-failure
    environment:
      KONG_DATABASE:           "off"
      KONG_DECLARATIVE_CONFIG: /kong/declarative/kong.yml
      KONG_PROXY_LISTEN:       "0.0.0.0:8000"
      KONG_ADMIN_LISTEN:       "0.0.0.0:8001"
      KONG_PROXY_ACCESS_LOG:   /dev/stdout
      KONG_ADMIN_ACCESS_LOG:   /dev/stdout
      KONG_PROXY_ERROR_LOG:    /dev/stderr
      KONG_ADMIN_ERROR_LOG:    /dev/stderr
      KONG_LOG_LEVEL:          info
    volumes:
      - ./kong:/kong/declarative:ro
    ports:
      - "8000:8000"    # Proxy — all user traffic enters here
      - "8001:8001"    # Admin API
    healthcheck:
      test: ["CMD", "kong", "health"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 15s
    networks:
      - ticketblitz-net

  # ── Atomic Services ──────────────────────────────────────
  # All run on :5000 internally. Host ports are for dev/test only.
  # Service-to-service calls use Docker DNS: http://user-service:5000

  event-service:
    build:
      context: ./atomic/event-service
      dockerfile: ../../docker/Dockerfile.flask
    image: ticketblitz/event-service:latest
    container_name: ticketblitz-event-service
    restart: on-failure
    env_file: .env
    environment:
      PORT: "5000"
      SERVICE_NAME: event-service
    ports:
      - "5001:5000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s
    networks:
      - ticketblitz-net

  user-service:
    build:
      context: ./atomic/user-service
      dockerfile: ../../docker/Dockerfile.flask
    image: ticketblitz/user-service:latest
    container_name: ticketblitz-user-service
    restart: on-failure
    env_file: .env
    environment:
      PORT: "5000"
      SERVICE_NAME: user-service
    ports:
      - "5002:5000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s
    networks:
      - ticketblitz-net

  inventory-service:
    build:
      context: ./atomic/inventory-service
      dockerfile: ../../docker/Dockerfile.flask
    image: ticketblitz/inventory-service:latest
    container_name: ticketblitz-inventory-service
    restart: on-failure
    env_file: .env
    environment:
      PORT: "5000"
      SERVICE_NAME: inventory-service
    ports:
      - "5003:5000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s
    networks:
      - ticketblitz-net

  payment-service:
    build:
      context: ./atomic/payment-service
      dockerfile: ../../docker/Dockerfile.flask
    image: ticketblitz/payment-service:latest
    container_name: ticketblitz-payment-service
    restart: on-failure
    env_file: .env
    environment:
      PORT: "5000"
      SERVICE_NAME: payment-service
    ports:
      - "5004:5000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s
    networks:
      - ticketblitz-net

  waitlist-service:
    build:
      context: ./atomic/waitlist-service
      dockerfile: ../../docker/Dockerfile.flask
    image: ticketblitz/waitlist-service:latest
    container_name: ticketblitz-waitlist-service
    restart: on-failure
    env_file: .env
    environment:
      PORT: "5000"
      SERVICE_NAME: waitlist-service
    ports:
      - "5005:5000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s
    networks:
      - ticketblitz-net

  notification-service:
    build:
      context: ./atomic/notification-service
      dockerfile: ../../docker/Dockerfile.worker
    image: ticketblitz/notification-service:latest
    container_name: ticketblitz-notification-service
    restart: on-failure
    env_file: .env
    environment:
      SERVICE_NAME: notification-service
    depends_on:
      rabbitmq:
        condition: service_healthy
    networks:
      - ticketblitz-net

  # ── Composite Services — HTTP ────────────────────────────

  reservation-orchestrator:
    build:
      context: ./composite/scenario-1/reservation-orchestrator
      dockerfile: ../../../docker/Dockerfile.flask
    image: ticketblitz/reservation-orchestrator:latest
    container_name: ticketblitz-reservation-orchestrator
    restart: on-failure
    env_file: .env
    environment:
      PORT: "5000"
      SERVICE_NAME: reservation-orchestrator
    ports:
      - "6001:5000"
    depends_on:
      rabbitmq:
        condition: service_healthy
      user-service:
        condition: service_healthy
      inventory-service:
        condition: service_healthy
      payment-service:
        condition: service_healthy
      waitlist-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 20s
    networks:
      - ticketblitz-net

  booking-status-service:
    build:
      context: ./composite/scenario-1/booking-status-service
      dockerfile: ../../../docker/Dockerfile.flask
    image: ticketblitz/booking-status-service:latest
    container_name: ticketblitz-booking-status-service
    restart: on-failure
    env_file: .env
    environment:
      PORT: "5000"
      SERVICE_NAME: booking-status-service
    ports:
      - "6002:5000"
    depends_on:
      inventory-service:
        condition: service_healthy
      payment-service:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s
    networks:
      - ticketblitz-net

  # ── Composite Services — Workers (no HTTP port) ──────────

  booking-fulfillment-orchestrator:
    build:
      context: ./composite/scenario-1/booking-fulfillment-orchestrator
      dockerfile: ../../../docker/Dockerfile.worker
    image: ticketblitz/booking-fulfillment-orchestrator:latest
    container_name: ticketblitz-booking-fulfillment-orchestrator
    restart: on-failure
    env_file: .env
    environment:
      SERVICE_NAME: booking-fulfillment-orchestrator
    depends_on:
      rabbitmq:
        condition: service_healthy
      inventory-service:
        condition: service_healthy
      waitlist-service:
        condition: service_healthy
    networks:
      - ticketblitz-net

  waitlist-promotion-orchestrator:
    build:
      context: ./composite/scenario-1/waitlist-promotion-orchestrator
      dockerfile: ../../../docker/Dockerfile.worker
    image: ticketblitz/waitlist-promotion-orchestrator:latest
    container_name: ticketblitz-waitlist-promotion-orchestrator
    restart: on-failure
    env_file: .env
    environment:
      SERVICE_NAME: waitlist-promotion-orchestrator
    depends_on:
      rabbitmq:
        condition: service_healthy
      inventory-service:
        condition: service_healthy
      waitlist-service:
        condition: service_healthy
      user-service:
        condition: service_healthy
    networks:
      - ticketblitz-net

  expiry-scheduler-service:
    build:
      context: ./composite/scenario-1/expiry-scheduler-service
      dockerfile: ../../../docker/Dockerfile.worker
    image: ticketblitz/expiry-scheduler-service:latest
    container_name: ticketblitz-expiry-scheduler-service
    restart: on-failure
    env_file: .env
    environment:
      SERVICE_NAME:            expiry-scheduler-service
      EXPIRY_INTERVAL_SECONDS: "60"
    depends_on:
      inventory-service:
        condition: service_healthy
    networks:
      - ticketblitz-net

  # ── UI Services ──────────────────────────────────────────

  fan-booking-ui:
    image: nginx:alpine
    container_name: ticketblitz-fan-ui
    restart: on-failure
    volumes:
      - ./ui/fan-booking-ui:/usr/share/nginx/html:ro
    ports:
      - "3000:80"
    depends_on:
      kong:
        condition: service_healthy
    networks:
      - ticketblitz-net

  organiser-dashboard-ui:
    image: nginx:alpine
    container_name: ticketblitz-organiser-ui
    restart: on-failure
    volumes:
      - ./ui/organiser-dashboard-ui:/usr/share/nginx/html:ro
    ports:
      - "3001:80"
    depends_on:
      kong:
        condition: service_healthy
    networks:
      - ticketblitz-net

networks:
  ticketblitz-net:
    driver: bridge

volumes:
  rabbitmq-data:
    driver: local
```

### 9.4 — Port Reference

| Service | Host Port | Internal Port | Purpose |
|---|---|---|---|
| Kong Proxy | **8000** | 8000 | All UI traffic enters here |
| Kong Admin | **8001** | 8001 | Reload config, inspect routes |
| RabbitMQ AMQP | **5672** | 5672 | pika connections |
| RabbitMQ UI | **15672** | 15672 | http://localhost:15672 |
| event-service | 5001 | 5000 | Dev/test direct access |
| user-service | 5002 | 5000 | Dev/test direct access |
| inventory-service | 5003 | 5000 | Dev/test direct access |
| payment-service | 5004 | 5000 | Dev/test direct access |
| waitlist-service | 5005 | 5000 | Dev/test direct access |
| reservation-orchestrator | 6001 | 5000 | Dev/test direct access |
| booking-status-service | 6002 | 5000 | Dev/test direct access |
| Fan Booking UI | **3000** | 80 | http://localhost:3000 |
| Organiser UI | **3001** | 80 | http://localhost:3001 |

### 9.5 — First-time build

```bash
# From the project root (where docker-compose.yml lives)
docker compose up --build
```

This builds all images and starts all containers. Allow 3–5 minutes on first run.

### 9.6 — Subsequent starts

```bash
# No rebuild (code unchanged)
docker compose up -d

# Rebuild and restart a single service after a code change
docker compose up --build <service-name> -d

# Examples:
docker compose up --build inventory-service -d
docker compose up --build reservation-orchestrator -d
```

---

## 10. Stripe CLI Setup

The Stripe CLI forwards real Stripe webhook events to your local Kong gateway. Run this in a **dedicated terminal window** every development session.

### 10.1 — Install

**macOS (Homebrew):**
```bash
brew install stripe/stripe-cli/stripe
```

**Windows (Scoop):**
```powershell
scoop bucket add stripe https://github.com/stripe/scoop-stripe-cli.git
scoop install stripe
```

**Windows (Direct download):**  
Download the `.exe` from https://github.com/stripe/stripe-cli/releases and add it to your PATH.

Verify:
```bash
stripe --version
```

### 10.2 — Log in to the shared test account

```bash
stripe login
```

A browser window opens. Log in with the **shared team Stripe credentials**.  
The CLI stores your key locally — you do not need to re-login each session.

### 10.3 — Start webhook forwarding (run AFTER Docker is up)

```bash
stripe listen --forward-to localhost:8000/payment/webhook
```

Output:
```
> Ready! You are using Stripe API Version [2024-xx-xx]
> Your webhook signing secret is whsec_abc123xyz...
```

### 10.4 — Copy the webhook secret into `.env`

```env
STRIPE_WEBHOOK_SECRET=whsec_abc123xyz...
```

Then restart payment-service to load the new value:
```bash
docker compose restart payment-service
```

> ⚠️ **Critical:** The `whsec_...` value **changes every time** you run `stripe listen`.  
> You must update `.env` and restart `payment-service` at the start of every session.

### 10.5 — Trigger test events

```bash
stripe trigger payment_intent.succeeded
stripe trigger payment_intent.payment_failed
```

Verify the events arrive:
```bash
docker compose logs -f payment-service
```

---

## 11. RabbitMQ Exchange Setup

Exchanges must be created **once** after the first boot. They persist in the `rabbitmq-data` volume.

### 11.1 — Wait for RabbitMQ to be healthy

```bash
docker compose up rabbitmq -d
docker compose ps rabbitmq
# STATUS should show: healthy
```

### 11.2 — Create exchanges via the Management UI

Go to: **http://localhost:15672**  
Login: username `ticketblitz` / password `change_me_before_demo`

Create both exchanges:

| Exchange Name | Type | Durable | When used |
|---|---|---|---|
| `ticketblitz` | **topic** | ✅ Yes | Scenario 1 — `booking.confirmed`, `seat.released`, `notification.send` |
| `ticketblitz.price` | **fanout** | ✅ Yes | Scenario 2 — `price.broadcast` to ALL UI + notification consumers |

Steps per exchange: **Exchanges** tab → **Add a new exchange** → fill name + type + check Durable → **Add exchange**

### 11.3 — Create exchanges via API (one command each)

**macOS:**
```bash
curl -u ticketblitz:change_me_before_demo \
  -X PUT http://localhost:15672/api/exchanges/%2F/ticketblitz \
  -H "Content-Type: application/json" \
  -d '{"type":"topic","durable":true}'

curl -u ticketblitz:change_me_before_demo \
  -X PUT http://localhost:15672/api/exchanges/%2F/ticketblitz.price \
  -H "Content-Type: application/json" \
  -d '{"type":"fanout","durable":true}'
```

**Windows (PowerShell):**
```powershell
$headers = @{
  Authorization = "Basic " + [Convert]::ToBase64String(
    [Text.Encoding]::ASCII.GetBytes("ticketblitz:change_me_before_demo"))
  "Content-Type" = "application/json"
}

Invoke-RestMethod -Method Put -Uri "http://localhost:15672/api/exchanges/%2F/ticketblitz" `
  -Headers $headers -Body '{"type":"topic","durable":true}'

Invoke-RestMethod -Method Put -Uri "http://localhost:15672/api/exchanges/%2F/ticketblitz.price" `
  -Headers $headers -Body '{"type":"fanout","durable":true}'
```

### 11.4 — RabbitMQ Binding Keys Reference

| Binding Key | Exchange | Published by | Consumed by |
|---|---|---|---|
| `booking.confirmed` | `ticketblitz` (topic) | Payment Service | Booking Fulfillment Orchestrator |
| `seat.released` | `ticketblitz` (topic) | Inventory Service | Waitlist Promotion Orchestrator |
| `notification.send` | `ticketblitz` (topic) | Orchestrators | Notification Service |
| `price.broadcast` | `ticketblitz.price` (fanout) | Flash Sale/Pricing Orch. | Notification + all UI consumers |

---

## 12. Kong API Gateway

Kong is DB-less — its configuration lives entirely in `kong/kong.yml`. No database required.

Event write endpoints are protected with Kong `key-auth` and `acl` plugins. For local development, use header `x-organiser-api-key: ticketblitz-organiser-dev-key` on:
- `PUT /event/{eventID}/status`
- `PUT /event/{eventID}/categories/prices`

### 12.1 — `kong/kong.yml`

```yaml
_format_version: "3.0"
_transform: true

services:

  - name: event-service
    url: http://event-service:5000
    connect_timeout: 5000
    read_timeout: 10000
    write_timeout: 5000
    routes:
      - name: get-events
        paths: [/events]
        methods: [GET, OPTIONS]
        strip_path: false
    plugins:
      - name: rate-limiting
        config:
          minute: 120
          policy: local
          fault_tolerant: true

consumers:
  - username: organiser-dashboard
    keyauth_credentials:
      - key: ticketblitz-organiser-dev-key
    acls:
      - group: organisers

  - name: reservation-orchestrator
    url: http://reservation-orchestrator:5000
    connect_timeout: 10000
    read_timeout: 60000
    write_timeout: 10000
    routes:
      - name: reserve
        paths: [/reserve]
        methods: [POST, OPTIONS]
        strip_path: false
      - name: reserve-confirm
        paths: [/reserve/confirm]
        methods: [POST, OPTIONS]
        strip_path: false
      - name: waitlist-confirm
        paths: [/waitlist/confirm]
        methods: [GET, OPTIONS]
        strip_path: false
    plugins:
      - name: rate-limiting
        config:
          minute: 30
          hour: 200
          policy: local
          fault_tolerant: true

  - name: booking-status-service
    url: http://booking-status-service:5000
    connect_timeout: 5000
    read_timeout: 10000
    write_timeout: 5000
    routes:
      - name: booking-status
        paths: [/booking-status]
        methods: [GET, OPTIONS]
        strip_path: false
    plugins:
      - name: rate-limiting
        config:
          minute: 120
          policy: local
          fault_tolerant: true

  - name: waitlist-service-public
    url: http://waitlist-service:5000
    connect_timeout: 5000
    read_timeout: 10000
    write_timeout: 5000
    routes:
      - name: waitlist-status
        paths: [/waitlist]
        methods: [GET, OPTIONS]
        strip_path: false
    plugins:
      - name: rate-limiting
        config:
          minute: 60
          policy: local
          fault_tolerant: true

  - name: payment-webhook
    url: http://payment-service:5000
    connect_timeout: 5000
    read_timeout: 30000
    write_timeout: 10000
    routes:
      - name: stripe-webhook
        paths: [/payment/webhook]
        methods: [POST]
        strip_path: false
```

### 12.2 — Reload Kong without restart

After editing `kong/kong.yml`:

```bash
curl -X POST http://localhost:8001/config \
     -F config=@kong/kong.yml
```

---

## 13. Verify the Full Stack

### 13.1 — Check all containers

```bash
docker compose ps
```

Expected output:

```
NAME                                          STATUS
ticketblitz-rabbitmq                          running (healthy)
ticketblitz-kong                              running (healthy)
ticketblitz-event-service                     running (healthy)
ticketblitz-user-service                      running (healthy)
ticketblitz-inventory-service                 running (healthy)
ticketblitz-payment-service                   running (healthy)
ticketblitz-waitlist-service                      running (healthy)
ticketblitz-notification-service              running
ticketblitz-reservation-orchestrator          running (healthy)
ticketblitz-booking-status-service            running (healthy)
ticketblitz-booking-fulfillment-orchestrator  running
ticketblitz-waitlist-promotion-orchestrator   running
ticketblitz-expiry-scheduler-service          running
ticketblitz-fan-ui                            running
ticketblitz-organiser-ui                      running
```

Workers show `running` without `(healthy)` — that is correct, they have no HTTP endpoint.

### 13.2 — Smoke test through Kong

**macOS:**
```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/events
# Expected: 200
```

**Windows (PowerShell):**
```powershell
(Invoke-WebRequest -Uri "http://localhost:8000/events" -UseBasicParsing).StatusCode
# Expected: 200
```

Swagger docs (event service):

```text
http://localhost:5001/apidocs/
```

Protected organiser write route check:

```bash
# Missing API key (expected 401)
curl -i -X PUT http://localhost:8000/event/<eventID>/status \
  -H "Content-Type: application/json" \
  -d '{"status":"ACTIVE"}'

# With API key (expected 200/409 depending on current state)
curl -i -X PUT http://localhost:8000/event/<eventID>/status \
  -H "Content-Type: application/json" \
  -H "x-organiser-api-key: ticketblitz-organiser-dev-key" \
  -d '{"status":"ACTIVE"}'
```

### 13.3 — Access points

| Interface | URL | Credentials |
|---|---|---|
| Fan Booking UI | http://localhost:3000 | — |
| Organiser Dashboard UI | http://localhost:3001 | — |
| RabbitMQ Management | http://localhost:15672 | ticketblitz / change_me_before_demo |
| Kong Admin API | http://localhost:8001 | — |

### 13.4 — Scenario 1 end-to-end smoke test

```bash
# Step 1 — reserve a seat (returns holdID + Stripe clientSecret)
curl -X POST http://localhost:8000/reserve \
  -H "Content-Type: application/json" \
  -d '{
    "userID": "00000000-0000-0000-0000-000000000001",
    "eventID": "00000000-0000-0000-0000-000000000001",
    "seatCategory": "CAT1",
    "qty": 1
  }'

# Step 2 — simulate Stripe payment success
stripe trigger payment_intent.succeeded

# Step 3 — poll booking status
curl http://localhost:8000/booking-status/<holdID>
# Expected: {"status": "CONFIRMED", ...}
```

---

## 14. Daily Development Workflow

### Starting your session (every day)

```bash
# 1. Pull latest changes
git pull

# 2. Start all containers (detached)
docker compose up -d

# 3. In a SEPARATE terminal — start Stripe forwarding
stripe listen --forward-to localhost:8000/payment/webhook

# 4. Copy the new whsec_... value into .env → STRIPE_WEBHOOK_SECRET
# 5. Restart payment-service to pick it up
docker compose restart payment-service

# 6. Confirm everything is healthy
docker compose ps
```

### Making and testing a code change

```bash
# 1. Edit the source file in VS Code
# 2. Rebuild and restart only the changed service
docker compose up --build <service-name> -d

# 3. Watch its logs
docker compose logs -f <service-name>

# 4. Test the endpoint (direct for dev, through Kong for integration)
curl http://localhost:<host-port>/your-endpoint
curl http://localhost:8000/your-kong-route
```

### Development bind mount (optional, for instant code reload)

Add a `volumes` bind mount to any service in `docker-compose.yml` during active development:

```yaml
inventory-service:
  volumes:
    - ./atomic/inventory-service:/app   # ← add this line
```

Code changes now reflect instantly without rebuilding. Remove before final submission.

### Ending your session

```bash
# Stop all containers (keeps volumes — RabbitMQ data preserved)
docker compose down

# Full reset (wipes RabbitMQ data — re-run exchange setup after)
docker compose down -v
```

### Committing your work

```bash
git add .
git commit -m "feat(inventory): add seat hold expiry endpoint"
git push
```

Use conventional commit prefixes: `feat:`, `fix:`, `refactor:`, `test:`, `docs:`

---

## 15. Writing a Service — Standard Template

### Flask service (`app.py`)

Every HTTP service must follow this exact structure:

```python
import os
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ── Health endpoint (REQUIRED — Kong healthcheck calls this) ──
@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": os.environ.get("SERVICE_NAME", "unknown")
    }), 200

# ── Your endpoints here ───────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal error: {e}")
    return jsonify({"error": "Internal server error"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
```

### Supabase client (`atomic/shared/db.py`)

```python
import os
from supabase import create_client, Client

_client: Client = None

def get_db() -> Client:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_SERVICE_KEY")
        if not url or not key:
            raise RuntimeError("SUPABASE_URL or SUPABASE_SERVICE_KEY not set")
        _client = create_client(url, key)
    return _client
```

Usage:
```python
from atomic.shared.db import get_db

db = get_db()
result = db.table("users").select("*").eq("user_id", user_id).execute()
```

Or, if running as a standalone service without the shared module:
```python
import os
from supabase import create_client
db = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
```

### RabbitMQ publisher helper (`atomic/shared/mq.py`)

```python
import os
import pika

def get_connection():
    url = os.environ.get("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    params = pika.URLParameters(url)
    params.heartbeat = 60
    return pika.BlockingConnection(params)

def publish(routing_key: str, body: str, exchange: str = "ticketblitz"):
    conn = get_connection()
    channel = conn.channel()
    channel.basic_publish(
        exchange=exchange,
        routing_key=routing_key,
        body=body,
        properties=pika.BasicProperties(
            delivery_mode=2,        # persistent message
            content_type="application/json"
        )
    )
    conn.close()
```

### Worker service (`worker.py`)

```python
import os
import json
import signal
import sys
import pika
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def handle_message(ch, method, properties, body):
    try:
        data = json.loads(body)
        logger.info(f"Received: {data}")
        # your business logic here
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def main():
    url = os.environ.get("RABBITMQ_URL")
    params = pika.URLParameters(url)
    params.heartbeat = 60

    connection = pika.BlockingConnection(params)
    channel = connection.channel()

    queue_name = os.environ.get("SERVICE_NAME", "worker")
    channel.queue_declare(queue=queue_name, durable=True)
    channel.queue_bind(
        exchange="ticketblitz",
        queue=queue_name,
        routing_key="your.binding.key"
    )

    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=queue_name, on_message_callback=handle_message)

    # Graceful shutdown on SIGTERM (Docker stop sends SIGTERM)
    def shutdown(sig, frame):
        logger.info("Shutting down...")
        channel.stop_consuming()
        connection.close()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info(f"[{queue_name}] Waiting for messages...")
    channel.start_consuming()

if __name__ == "__main__":
    main()
```

---

## 16. Useful Commands Reference

### Container management
```bash
# Status of all containers
docker compose ps

# Real-time logs for one service
docker compose logs -f <service-name>

# Logs for multiple services simultaneously
docker compose logs -f reservation-orchestrator payment-service

# Rebuild and restart after code change
docker compose up --build <service-name> -d

# Restart without rebuild (picks up new .env values)
docker compose restart <service-name>

# Shell into a running container for debugging
docker compose exec <service-name> /bin/bash

# CPU + memory usage per container
docker stats

# Stop everything (keeps volumes)
docker compose down

# Stop + wipe all volumes (full reset)
docker compose down -v
```

### Stripe CLI
```bash
stripe listen --forward-to localhost:8000/payment/webhook
stripe trigger payment_intent.succeeded
stripe trigger payment_intent.payment_failed
```

### RabbitMQ
```bash
# List all queues
docker compose exec rabbitmq rabbitmqctl list_queues

# List all exchanges
docker compose exec rabbitmq rabbitmqctl list_exchanges

# Purge a queue (clear stuck messages during testing)
docker compose exec rabbitmq rabbitmqctl purge_queue <queue-name>
```

### Kong
```bash
# Reload config without restarting the container
curl -X POST http://localhost:8001/config -F config=@kong/kong.yml

# List all routes
curl http://localhost:8001/routes

# List all services
curl http://localhost:8001/services
```

### Cleanup
```bash
# Remove stopped containers + unused images + build cache
docker system prune -f

# Full wipe including volumes (WARNING: destroys RabbitMQ data)
docker system prune -af --volumes
```

---

## 17. Troubleshooting

### A service keeps restarting or shows "unhealthy"
```bash
docker compose logs <service-name>
```
Most common causes: missing or wrong `.env` value; RabbitMQ not ready yet; Supabase URL wrong.
```bash
docker compose restart <service-name>
```

### "Cannot connect to RabbitMQ" in worker logs
The worker started before RabbitMQ was fully initialised. Workers with `depends_on: condition: service_healthy` handle this on first boot, but manual restarts skip the check.
```bash
docker compose restart notification-service
docker compose restart booking-fulfillment-orchestrator
```

### Kong returns 503 for a route
The upstream service is not running or not healthy.
```bash
docker compose ps              # find which service is down
docker compose up -d <name>    # bring it back
```

### Stripe webhook returns 400 (signature mismatch)
`STRIPE_WEBHOOK_SECRET` in `.env` is stale. Stop `stripe listen`, restart it, copy the new `whsec_...` into `.env`, then:
```bash
docker compose restart payment-service
```

### Port already in use on startup

**macOS — find and kill:**
```bash
lsof -i :8000          # find PID using port 8000
kill -9 <PID>
```

**Windows (PowerShell):**
```powershell
netstat -ano | findstr :8000
Stop-Process -Id <PID> -Force
```

### Dockerfile path error on `docker compose up --build`
The `dockerfile: ../../docker/Dockerfile.flask` path is relative to the `context` directory (the service folder), not `docker-compose.yml`. Always run `docker compose` from the **project root**:
```bash
cd ticketblitz        # must be here
docker compose up --build
```

### `docker compose` command not found (Windows)
You have Docker Compose v1 (`docker-compose`). Update Docker Desktop to get v2 (`docker compose`). v1 is no longer supported.

### RabbitMQ exchanges missing after `docker compose down -v`
The `-v` flag wipes volumes including RabbitMQ's data. Re-run the exchange setup from **Section 11** after any full volume reset.

### VS Code doesn't recognise imports from `atomic/shared/`
Select the correct Python interpreter: `Ctrl+Shift+P` → **Python: Select Interpreter** → choose `.venv` for your service. Then add the project root to `sys.path` in a `.pth` file inside the venv, or use relative imports within the service.

---

*End of guide. When in doubt: `docker compose logs <service>` — the error is almost always there.*
