# Scenario 1 Demo Runbook (Unabridged End-to-End Implementation)

## Objective
Execute Scenario 1 exactly as defined in `docs/Scenarios.md`, from first request to final UI state, including all asynchronous handoffs:

1. Step 1A: Seat available -> `PAYMENT_PENDING` -> `PROCESSING` -> `CONFIRMED`
2. Step 1B: Sold out -> `WAITLISTED` (`WAITING` + position polling)
3. Step 1C: Seat released -> `PENDING_WAITLIST` -> `HOLD_OFFERED` -> `PAYMENT_PENDING` -> `CONFIRMED`
4. Step 1D: Timeout -> hold expires -> waitlist offer expires -> `EXPIRED`

This runbook is aligned to:

- `docs/Scenarios.md` (Scenario 1 architecture and contracts)
- `docs/Setup.md` (runtime setup)
- live Supabase project `cpxcpvcfbohvpiubbujg`
- current service behavior observed on 2026-04-05

## Scope And Non-Negotiable Design Rules

This runbook follows these Scenario 1 implementation rules from `docs/Scenarios.md`:

- All user-facing HTTP goes through Kong (`http://localhost:8000`).
- Reservation flow is synchronous up to payment setup; fulfillment is asynchronous.
- Booking status for pending pages is read from Booking Status Service polling.
- Waitlist Promotion Orchestrator never reads waitlist tables directly (uses Waitlist Service API).
- Expiry Scheduler never writes inventory directly (uses Inventory maintenance API).
- Waitlist release path protects seats as `PENDING_WAITLIST` to prevent public seat stealing.
- E-ticket integration boundary is OutSystems REST.

## 1) Baseline Demo Data

Use these IDs in payloads unless explicitly stated otherwise:

- Available branch event (`EVT-301`): `10000000-0000-0000-0000-000000000301`
- Sold-out/waitlist branch event (`EVT-501`): `10000000-0000-0000-0000-000000000501`
- Fan user (API demo): `eba6aebb-a848-410b-8d6e-1b8275c4ce9c`
- Deterministic expired hold fixture: `40000000-0000-0000-0000-000000000003`

## 2) Preflight (Do Not Skip)

### 2.1 Frontend environment

`frontend/.env.local` must include:

- `VITE_API_BASE_URL=/api`
- `VITE_CUSTOMER_API_KEY=ticketblitz-customer-dev-key`
- `VITE_STRIPE_PUBLISHABLE_KEY=pk_test_...`

### 2.2 Backend environment

Root `.env.local` must include:

- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `RABBITMQ_USER`
- `RABBITMQ_PASSWORD`
- `RABBITMQ_URL`
- `STRIPE_SECRET_KEY`
- `INTERNAL_SERVICE_TOKEN`
- `STRIPE_WEBHOOK_SECRET` (must match current Stripe CLI session)
- `OUTSYSTEMS_BASE_URL`
- `OUTSYSTEMS_API_KEY`

### 2.3 Start backend stack

From repository root:

```bash
docker compose --env-file .env.local up -d --build
```

Health checks:

```bash
curl -s http://localhost:8000/events
curl -s http://localhost:6001/health
curl -s http://localhost:6002/health
curl -s http://localhost:5004/health
```

### 2.4 Verify RabbitMQ exchanges (required for async branches)

```bash
docker compose exec rabbitmq rabbitmqctl list_exchanges name type | grep ticketblitz
```

Expected exchanges:

- `ticketblitz` (`topic`)
- `ticketblitz.price` (`fanout`, Scenario 2 only, optional for this runbook)

### 2.5 Start frontend

```bash
cd frontend
npm install
npm run dev
```

## 3) Stripe Webhook Setup (Required For 1A/1C Finalization)

Start webhook forwarding in a dedicated terminal:

```bash
stripe listen --forward-to localhost:8000/payment/webhook
```

Copy displayed `whsec_...` into root `.env.local`, then restart payment service:

```bash
docker compose restart payment-service
```

Optional webhook sanity check:

```bash
docker compose logs --tail 100 payment-service
```

## 4) Full Flow Map (From Scenarios.md)

Use this sequence as the source of truth while presenting:

1. UI -> Kong: `POST /reserve`
2. Reservation Orchestrator -> User Service: `GET /user/{userID}`
3. Reservation Orchestrator -> Inventory Service: `GET /inventory/{eventID}/{seatCategory}`
4. Reservation Orchestrator -> Inventory Service: `POST /inventory/hold` (`fromWaitlist:false`)
5. Reservation Orchestrator -> Payment Service: `POST /payment/initiate`
6. UI uses Stripe `clientSecret` and redirects to `/booking/pending/{holdID}`
7. UI polls `GET /booking-status/{holdID}`
8. Stripe webhook `payment_intent.succeeded` -> Payment Service
9. Payment Service publishes `booking.confirmed`
10. Booking Fulfillment Orchestrator confirms hold, generates e-ticket, publishes `notification.send`
11. Booking Status Service eventually returns `uiStatus=CONFIRMED`
12. For sold out path, Reservation Orchestrator joins waitlist and returns `WAITLISTED`
13. For release path, Inventory publishes `seat.released`, Waitlist Promotion offers hold, user pays via `/reserve/confirm`
14. For timeout path, Expiry Scheduler triggers hold expiry and Booking Status returns `EXPIRED`

## 5) Step 1A Implementation (Seat Available -> CONFIRMED)

### 5.1 Reserve an available seat

```bash
curl -s -X POST "http://localhost:8000/reserve" \
   -H "Content-Type: application/json" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key" \
   -H "X-User-ID: eba6aebb-a848-410b-8d6e-1b8275c4ce9c" \
   -d '{"userID":"eba6aebb-a848-410b-8d6e-1b8275c4ce9c","eventID":"10000000-0000-0000-0000-000000000301","seatCategory":"CAT2","qty":1}'
```

Expected:

- HTTP `200`
- `status: "PAYMENT_PENDING"`
- non-empty `holdID`, `paymentIntentID`, `clientSecret`, `holdExpiry`, `returnURL`

### 5.2 Verify pre-webhook status (`PROCESSING` expected)

```bash
curl -s "http://localhost:8000/booking-status/<HOLD_ID_FROM_5_1>" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key"
```

Expected:

- `uiStatus: "PROCESSING"`

### 5.3 Complete payment in UI

1. Open `http://localhost:5173/ticket-purchase`
2. Reserve `EVT-301` + `CAT2`
3. Confirm page route `/booking/pending/<holdID>`
4. Use Stripe test card
    - Success: `4242424242424242`
    - 3DS challenge: `4000002500003155`
    - Decline test: `4000000000009995`

### 5.4 Poll to terminal status

```bash
curl -s "http://localhost:8000/booking-status/<HOLD_ID_FROM_5_1>" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key"
```

Expected terminal response:

- `uiStatus: "CONFIRMED"`
- plus seat/ticket metadata when e-ticket is reachable

### 5.5 Validate async chain in logs

```bash
docker compose logs --tail 200 payment-service
docker compose logs --tail 200 booking-fulfillment-orchestrator
docker compose logs --tail 200 notification-service
```

Expected evidence:

- payment webhook accepted
- `booking.confirmed` consumed
- inventory hold confirmed
- notification event published/consumed

## 6) Step 1B Implementation (Sold Out -> WAITLISTED)

### 6.1 Request sold-out category reservation

```bash
curl -s -X POST "http://localhost:8000/reserve" \
   -H "Content-Type: application/json" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key" \
   -H "X-User-ID: eba6aebb-a848-410b-8d6e-1b8275c4ce9c" \
   -d '{"userID":"eba6aebb-a848-410b-8d6e-1b8275c4ce9c","eventID":"10000000-0000-0000-0000-000000000501","seatCategory":"CAT1","qty":1}'
```

Expected:

- HTTP `200`
- `status: "WAITLISTED"`
- non-empty `waitlistID`
- numeric `position`

### 6.2 Waitlist status polling

```bash
curl -s "http://localhost:8000/waitlist/<WAITLIST_ID_FROM_6_1>" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key"
```

Expected:

- `status: "WAITING"`
- valid position value

## 7) Step 1C Implementation (Seat Released -> WAITLIST_OFFERED -> PAYMENT_PENDING -> CONFIRMED)

This is the protected waitlist promotion path from `docs/Scenarios.md`.

### 7.1 Create a releasable hold on EVT-301 CAT1

```bash
curl -s -X POST "http://localhost:8000/reserve" \
   -H "Content-Type: application/json" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key" \
   -H "X-User-ID: eba6aebb-a848-410b-8d6e-1b8275c4ce9c" \
   -d '{"userID":"eba6aebb-a848-410b-8d6e-1b8275c4ce9c","eventID":"10000000-0000-0000-0000-000000000301","seatCategory":"CAT1","qty":1}'
```

Capture `holdID` as `HOLD_RELEASE_SOURCE`.

### 7.2 Release hold with timeout reason (publishes `seat.released`)

```bash
curl -s -X PUT "http://localhost:5003/inventory/hold/<HOLD_RELEASE_SOURCE>/release" \
   -H "Content-Type: application/json" \
   -d '{"reason":"PAYMENT_TIMEOUT"}'
```

Expected:

- hold response indicates `RELEASED`
- released seat transitions to waitlist-protected availability (`PENDING_WAITLIST`)

### 7.3 Confirm waitlist entry offered a new hold

Run in Supabase SQL editor:

```sql
select
   w.waitlist_id,
   w.user_id,
   c.category_code,
   w.status,
   w.hold_id,
   w.offered_at
from public.waitlist_entries w
left join public.seat_categories c on c.category_id = w.category_id
where w.event_id = '10000000-0000-0000-0000-000000000301'
   and c.category_code = 'CAT1'
order by w.updated_at desc
limit 5;
```

Expected:

- at least one row with `status = 'HOLD_OFFERED'`
- `hold_id` not null (capture as `OFFERED_HOLD_ID`)
- capture corresponding `user_id` as `OFFERED_USER_ID`

### 7.4 Validate `/waitlist/confirm/{holdID}` context

```bash
curl -s "http://localhost:8000/waitlist/confirm/<OFFERED_HOLD_ID>" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key" \
   -H "X-User-ID: <OFFERED_USER_ID>"
```

Expected:

- HTTP `200`
- `uiStatus: "WAITLIST_OFFERED"`
- hold shows active offer
- waitlist object `status: "HOLD_OFFERED"`

### 7.5 Continue from waitlist offer to payment setup

```bash
curl -s -X POST "http://localhost:8000/reserve/confirm" \
   -H "Content-Type: application/json" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key" \
   -H "X-User-ID: <OFFERED_USER_ID>" \
   -d '{"holdID":"<OFFERED_HOLD_ID>","userID":"<OFFERED_USER_ID>"}'
```

Expected:

- HTTP `200`
- `status: "PAYMENT_PENDING"`
- non-empty `clientSecret`, `paymentIntentID`, `returnURL`

### 7.6 Complete payment and validate terminal `CONFIRMED`

1. Open waitlist payment route in UI (`/waitlist/confirm/<OFFERED_HOLD_ID>`).
2. Submit Stripe success card `4242424242424242`.
3. Confirm redirect to pending route.
4. Poll:

```bash
curl -s "http://localhost:8000/booking-status/<OFFERED_HOLD_ID>" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key"
```

Expected terminal state:

- `uiStatus: "CONFIRMED"`

### 7.7 Validate required async events occurred

```bash
docker compose logs --tail 200 waitlist-promotion-orchestrator
docker compose logs --tail 200 booking-fulfillment-orchestrator
docker compose logs --tail 200 notification-service
```

Expected evidence:

- consumed `seat.released`
- waitlist updated to offered then confirmed
- fulfillment completed and notification sent

## 8) Step 1D Implementation (Timeout / Expired)

### 8.1 Deterministic timeout fixture check

```bash
curl -s "http://localhost:8000/waitlist/confirm/40000000-0000-0000-0000-000000000003" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key" \
   -H "X-User-ID: 00000000-0000-0000-0000-000000000001"
```

Expected:

- HTTP `200`
- `uiStatus: "EXPIRED"`
- hold status expired
- waitlist status expired

### 8.2 Booking status expiration confirmation

```bash
curl -s "http://localhost:8000/booking-status/40000000-0000-0000-0000-000000000003" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key"
```

Expected:

- `uiStatus: "EXPIRED"`
- payment dependency marked skipped/not applicable for this expired fixture

### 8.3 Live timeout path validation (optional, fully aligned to Scenarios.md)

Use this if you want to demonstrate scheduler-driven expiry rather than fixture lookup.

1. Produce a `HOLD_OFFERED` record using Step 1C up to 7.5.
2. Do not complete payment.
3. Wait for hold expiry window and scheduler interval.
4. Verify expiry processing logs:

```bash
docker compose logs --tail 200 expiry-scheduler-service
docker compose logs --tail 200 inventory-service
docker compose logs --tail 200 waitlist-promotion-orchestrator
```

5. Verify timed-out hold state:

```bash
curl -s "http://localhost:8000/booking-status/<TIMED_OUT_HOLD_ID>" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key"
```

Expected:

- `uiStatus: "EXPIRED"`
- downstream promotion either offers next user or returns seat to `AVAILABLE` when waitlist empty

## 9) Data Validation Queries (Supabase SQL)

Use these queries to prove every state transition end-to-end.

### 9.1 Hold lifecycle

```sql
select hold_id, user_id, status, hold_expiry, updated_at
from public.seat_holds
where hold_id in (
   '<HOLD_ID_FROM_1A>',
   '<OFFERED_HOLD_ID_FROM_1C>',
   '40000000-0000-0000-0000-000000000003'
)
order by updated_at desc;
```

### 9.2 Waitlist lifecycle

```sql
select waitlist_id, user_id, status, hold_id, offered_at, updated_at
from public.waitlist_entries
where event_id = '10000000-0000-0000-0000-000000000301'
order by updated_at desc
limit 20;
```

### 9.3 Payment lifecycle

```sql
select hold_id, stripe_payment_intent_id, status, amount, updated_at
from public.transactions
where hold_id in ('<HOLD_ID_FROM_1A>', '<OFFERED_HOLD_ID_FROM_1C>')
order by updated_at desc;
```

### 9.4 Seat state ownership check

```sql
select s.seat_id, s.status, c.category_code, s.updated_at
from public.seats s
join public.seat_categories c on c.category_id = s.category_id
where s.event_id = '10000000-0000-0000-0000-000000000301'
   and c.category_code in ('CAT1', 'CAT2')
order by s.updated_at desc
limit 20;
```

## 10) Expected Outcomes Matrix (Complete)

| Scenario branch | Input | Mandatory output |
|---|---|---|
| 1A reserve available | `POST /reserve` (EVT-301 CAT2) | `status=PAYMENT_PENDING`, then booking status reaches `CONFIRMED` |
| 1B sold out join waitlist | `POST /reserve` (EVT-501 CAT1) | `status=WAITLISTED`, with `waitlistID` and `position` |
| 1C waitlist promotion | release hold with reason `PAYMENT_TIMEOUT`, then `GET /waitlist/confirm/{holdID}` + `POST /reserve/confirm` | `uiStatus=WAITLIST_OFFERED`, then `status=PAYMENT_PENDING`, then booking status `CONFIRMED` after payment |
| 1D timeout terminal | fixture hold or live expiry path | booking status `uiStatus=EXPIRED` |

## 11) Important Runtime Caveat

`booking-status` can remain `PROCESSING` after payment success when e-ticket fetch/generation is unavailable.

In that case, still treat flow as correct if you can show:

- payment status is `SUCCEEDED`
- inventory hold status is `CONFIRMED`
- e-ticket dependency marked unavailable/not found

To get terminal `CONFIRMED` in UI:

1. ensure OutSystems endpoint + API key are valid
2. ensure Stripe webhook forwarding is running and `STRIPE_WEBHOOK_SECRET` matches current listener

## 12) Fast Troubleshooting

### Payment does not leave pending

1. Confirm Stripe listener is running.
2. Confirm `STRIPE_WEBHOOK_SECRET` matches current `stripe listen` output.
3. Restart payment service:

```bash
docker compose restart payment-service
```

### Waitlist promotion not firing

```bash
docker compose ps waitlist-promotion-orchestrator
docker compose logs -f waitlist-promotion-orchestrator --tail 200
```

### Expiry flow not firing

```bash
docker compose ps expiry-scheduler-service
docker compose logs -f expiry-scheduler-service --tail 200
docker compose logs -f inventory-service --tail 200
```

### Stale runtime behavior

```bash
docker compose build --no-cache reservation-orchestrator booking-status-service inventory-service payment-service waitlist-promotion-orchestrator expiry-scheduler-service
docker compose up -d reservation-orchestrator booking-status-service inventory-service payment-service waitlist-promotion-orchestrator expiry-scheduler-service
```

## 13) Demo Script (Condensed Verbal Walkthrough)

Use this exact order for presentation:

1. Show stack health + Stripe webhook listener.
2. Run 1A reserve and show `PAYMENT_PENDING`, then complete payment and show `CONFIRMED`.
3. Run 1B sold-out reserve and show `WAITLISTED` + position.
4. Run 1C release/promotion and show `WAITLIST_OFFERED` -> payment -> `CONFIRMED`.
5. Run 1D fixture hold and show `EXPIRED`.
6. Show logs proving async events (`booking.confirmed`, `seat.released`, `notification.send`).
7. Show SQL validation of hold/waitlist/payment transitions.
