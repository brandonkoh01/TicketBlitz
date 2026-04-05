# Scenario 1 Demo Runbook (Live-Validated)

## Objective
Demonstrate the full Scenario 1 flow end-to-end with no skipped steps:

1. 1A: Seat available -> `PAYMENT_PENDING`
2. 1B: Sold out -> `WAITLISTED`
3. 1C: Waitlist promoted -> `WAITLIST_OFFERED` -> `PAYMENT_PENDING`
4. 1D: Timeout path -> `EXPIRED`

This runbook is aligned to:

- `docs/Setup.md`
- `docs/Scenarios.md`
- live Supabase project `cpxcpvcfbohvpiubbujg`
- current service behavior observed on 2026-04-05

## 1) Live Data Baseline Used In This Runbook

Use these known-good IDs for demo payloads:

- Event (available branch): `10000000-0000-0000-0000-000000000301` (`EVT-301`)
- Event (waitlist branch): `10000000-0000-0000-0000-000000000501` (`EVT-501`)
- Fan user (API demo): `eba6aebb-a848-410b-8d6e-1b8275c4ce9c` (`user1@gmail.com`)
- Deterministic expired hold fixture: `40000000-0000-0000-0000-000000000003`

## 2) Preflight (Do Not Skip)

### 2.1 Verify frontend env

`frontend/.env.local` must include:

- `VITE_API_BASE_URL=/api`
- `VITE_CUSTOMER_API_KEY=ticketblitz-customer-dev-key`
- `VITE_STRIPE_PUBLISHABLE_KEY=pk_test_...`

### 2.2 Verify backend env

Root `.env.local` must include:

- `SUPABASE_URL` + `SUPABASE_SERVICE_KEY`
- `RABBITMQ_USER`, `RABBITMQ_PASSWORD`, `RABBITMQ_URL`
- `STRIPE_SECRET_KEY`
- `INTERNAL_SERVICE_TOKEN`

For webhook-driven status progression, also set:

- `STRIPE_WEBHOOK_SECRET=whsec_...`

For terminal `CONFIRMED` status from booking-status, ensure OutSystems integration is configured and reachable:

- `OUTSYSTEMS_BASE_URL`
- `OUTSYSTEMS_API_KEY`

### 2.3 Start stack

From repository root:

```bash
docker compose --env-file .env.local up -d --build
```

Check core endpoints:

```bash
curl -s http://localhost:8000/events
curl -s http://localhost:6001/health
curl -s http://localhost:6002/health
curl -s http://localhost:5004/health
```

### 2.4 Start frontend

```bash
cd frontend
npm install
npm run dev
```

## 3) Stripe Test Setup (Recommended)

Use Stripe CLI to forward signed webhooks:

```bash
stripe listen --forward-to localhost:8000/payment/webhook
```

Copy printed `whsec_...` secret into root `.env.local`, then:

```bash
docker compose restart payment-service
```

## 4) Scenario 1A: Seat Available -> PAYMENT_PENDING

### 4.1 API input (working)

```bash
curl -s -X POST "http://localhost:8000/reserve" \
   -H "Content-Type: application/json" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key" \
   -H "X-User-ID: eba6aebb-a848-410b-8d6e-1b8275c4ce9c" \
   -d '{"userID":"eba6aebb-a848-410b-8d6e-1b8275c4ce9c","eventID":"10000000-0000-0000-0000-000000000301","seatCategory":"CAT2","qty":1}'
```

### 4.2 Expected output

- HTTP `200`
- `status: "PAYMENT_PENDING"`
- non-empty `holdID`, `paymentIntentID`, `clientSecret`, `holdExpiry`
- `returnURL` like `/booking/pending/<holdID>`

Sample observed output:

```json
{
   "status": "PAYMENT_PENDING",
   "holdID": "2d2ce8c4-7bce-4de0-b5f1-51b0bdd9b2e1",
   "paymentIntentID": "pi_3TImaN3qZndukFh40jEC9jH6",
   "seatCategory": "CAT2"
}
```

### 4.3 UI demonstration steps

1. Open `http://localhost:5173/ticket-purchase`
2. Reserve EVT-301 + CAT2
3. Verify route -> `/booking/pending/<holdID>`
4. In payment element, use Stripe test cards:
    - Success: `4242424242424242`
    - 3DS challenge: `4000002500003155`
    - Decline: `4000000000009995`
    - Any future expiry, any CVC, any postal code

## 5) Scenario 1B: Sold Out -> WAITLISTED

### 5.1 API input (working)

```bash
curl -s -X POST "http://localhost:8000/reserve" \
   -H "Content-Type: application/json" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key" \
   -H "X-User-ID: eba6aebb-a848-410b-8d6e-1b8275c4ce9c" \
   -d '{"userID":"eba6aebb-a848-410b-8d6e-1b8275c4ce9c","eventID":"10000000-0000-0000-0000-000000000501","seatCategory":"CAT1","qty":1}'
```

### 5.2 Expected output

- HTTP `200`
- `status: "WAITLISTED"`
- non-empty `waitlistID`
- numeric `position`

Sample observed output:

```json
{
   "status": "WAITLISTED",
   "waitlistID": "265ead7f-4e2f-47a5-8ccd-4622d82cd330",
   "position": 3,
   "eventID": "10000000-0000-0000-0000-000000000501",
   "seatCategory": "CAT1"
}
```

## 6) Scenario 1C: Waitlist Promotion -> WAITLIST_OFFERED -> PAYMENT_PENDING

This branch requires triggering `seat.released`, which the waitlist-promotion worker consumes.

### 6.1 Create a releasable CAT1 hold

```bash
curl -s -X POST "http://localhost:8000/reserve" \
   -H "Content-Type: application/json" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key" \
   -H "X-User-ID: eba6aebb-a848-410b-8d6e-1b8275c4ce9c" \
   -d '{"userID":"eba6aebb-a848-410b-8d6e-1b8275c4ce9c","eventID":"10000000-0000-0000-0000-000000000301","seatCategory":"CAT1","qty":1}'
```

Capture returned `holdID` as `HOLD_RELEASE_SOURCE`.

### 6.2 Release that hold with timeout reason (publishes `seat.released`)

```bash
curl -s -X PUT "http://localhost:5003/inventory/hold/<HOLD_RELEASE_SOURCE>/release" \
   -H "Content-Type: application/json" \
   -d '{"reason":"PAYMENT_TIMEOUT"}'
```

Expected: response has `holdStatus: "RELEASED"` and seat becomes `PENDING_WAITLIST`.

### 6.3 Get promoted waitlist hold from Supabase SQL editor

```sql
select w.waitlist_id, w.user_id, c.category_code, w.status, w.hold_id, w.offered_at
from public.waitlist_entries w
left join public.seat_categories c on c.category_id = w.category_id
where w.event_id = '10000000-0000-0000-0000-000000000301'
   and c.category_code = 'CAT1'
order by w.updated_at desc
limit 5;
```

Expected: at least one row with `status='HOLD_OFFERED'` and non-null `hold_id`.

### 6.4 Validate waitlist confirm context

```bash
curl -s "http://localhost:8000/waitlist/confirm/<OFFERED_HOLD_ID>" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key" \
   -H "X-User-ID: <OFFERED_USER_ID>"
```

Expected output:

- HTTP `200`
- `uiStatus: "WAITLIST_OFFERED"`
- waitlist object has `status: "HOLD_OFFERED"`

Sample observed output:

```json
{
   "uiStatus": "WAITLIST_OFFERED",
   "hold": { "holdID": "36e60e16-7011-4b98-965a-508ae27cd0c7", "holdStatus": "HELD" },
   "waitlist": { "waitlistID": "9bb20000-0000-0000-0000-000000000001", "status": "HOLD_OFFERED" }
}
```

### 6.5 Continue to payment from waitlist offer

```bash
curl -s -X POST "http://localhost:8000/reserve/confirm" \
   -H "Content-Type: application/json" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key" \
   -H "X-User-ID: <OFFERED_USER_ID>" \
   -d '{"holdID":"<OFFERED_HOLD_ID>","userID":"<OFFERED_USER_ID>"}'
```

Expected output:

- HTTP `200`
- `status: "PAYMENT_PENDING"`
- `clientSecret`, `paymentIntentID`, `returnURL`

## 7) Scenario 1D: Timeout / Expired Hold

### 7.1 Deterministic expired hold input

```bash
curl -s "http://localhost:8000/waitlist/confirm/40000000-0000-0000-0000-000000000003" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key" \
   -H "X-User-ID: 00000000-0000-0000-0000-000000000001"
```

Expected output:

- HTTP `200`
- `uiStatus: "EXPIRED"`
- hold `holdStatus: "EXPIRED"`
- waitlist `status: "EXPIRED"`

### 7.2 Booking status endpoint confirmation

```bash
curl -s "http://localhost:8000/booking-status/40000000-0000-0000-0000-000000000003" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key"
```

Expected output:

- `uiStatus: "EXPIRED"`
- `dependencyStatus.payment: "skipped"`

## 8) Working Inputs and Expected Outputs (Quick Matrix)

| Scenario | Working input | Expected output |
|---|---|---|
| 1A Available -> payment | `POST /reserve` user `eba6aebb-a848-410b-8d6e-1b8275c4ce9c`, event `EVT-301`, `CAT2` | `status=PAYMENT_PENDING`, route `/booking/pending/<holdID>` |
| 1B Sold out -> waitlist | `POST /reserve` user `eba6aebb-a848-410b-8d6e-1b8275c4ce9c`, event `EVT-501`, `CAT1` | `status=WAITLISTED`, `waitlistID`, `position` |
| 1C Promotion offer | Release a CAT1 hold with reason `PAYMENT_TIMEOUT`, then `GET /waitlist/confirm/<offered_hold>` | `uiStatus=WAITLIST_OFFERED`, then `/reserve/confirm` returns `PAYMENT_PENDING` |
| 1D Timeout terminal state | `GET /waitlist/confirm/40000000-0000-0000-0000-000000000003` and `GET /booking-status/...` | `uiStatus=EXPIRED` |

## 9) Important Demo Caveat (Current Runtime)

`booking-status` may remain `PROCESSING` even after payment `SUCCEEDED` when e-ticket cannot be fetched/generated.

You can still demonstrate correctness by showing:

- `paymentStatus: "SUCCEEDED"`
- `holdStatus: "CONFIRMED"`
- `dependencyStatus.eticket` as `not_found` or `unavailable`

For terminal `CONFIRMED` in UI:

1. ensure OutSystems endpoint and API key are valid, and
2. ensure webhook forwarding is running with current `STRIPE_WEBHOOK_SECRET`.

## 10) Troubleshooting (Fast)

### Payment does not move from pending

1. Check webhook forwarding terminal is running.
2. Confirm `STRIPE_WEBHOOK_SECRET` in root `.env.local` matches current `stripe listen` output.
3. Restart payment service:

```bash
docker compose restart payment-service
```

### Waitlist promotion not happening

1. Confirm waitlist-promotion worker is running:

```bash
docker compose ps waitlist-promotion-orchestrator
```

2. Check logs:

```bash
docker compose logs -f waitlist-promotion-orchestrator --tail 200
```

### Stale code behavior

```bash
docker compose build --no-cache reservation-orchestrator booking-status-service inventory-service payment-service
docker compose up -d reservation-orchestrator booking-status-service inventory-service payment-service
```
