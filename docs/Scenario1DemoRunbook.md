# Scenario 1 UI Demo Runbook (TicketBlitz Frontend)

## Objective
Run Scenario 1 end-to-end using the frontend UI routes, while validating each state transition against the backend and Supabase.

Scenario 1 coverage in this runbook:

1. Step 1A: Seat available -> PAYMENT_PENDING -> PROCESSING -> CONFIRMED
2. Step 1B: Sold out -> WAITLISTED (WAITING + position polling)
3. Step 1C: Seat released -> HOLD_OFFERED -> PAYMENT_PENDING -> CONFIRMED
4. Step 1D: Timeout path -> EXPIRED

This runbook is aligned to:

- docs/Scenarios.md
- docs/Setup.md
- frontend route behavior in `ticket-purchase`, `booking/pending/:holdID`, `waitlist/:waitlistID`, `waitlist/confirm/:holdID`, `booking/result/:holdID`, `my-tickets`
- Supabase project `cpxcpvcfbohvpiubbujg`

## 1) Demo Data Pack (Live Snapshot)

Use this data pack as the default for demo execution.

### 1.1 Primary Event

- Event ID: `10000000-0000-0000-0000-000000000301`
- Event code: `EVT-301`
- Name: `Coldplay Live 2026`

### 1.2 Seat Categories for EVT-301

Snapshot used for this runbook:

- `CAT1`: available=5, pending_waitlist=3, sold=3, total=11
- `CAT2`: available=0, sold=3, total=3
- `PEN`: available=3, sold=7, total=10

Implications:

- Use `PEN` for stable "seat available" demos.
- Use `CAT2` for stable "already sold out" waitlist demos.
- Use `CAT1` for controlled release/promotion flow (1C/1D), because it has enough inventory to create and release a temporary hold.

### 1.3 Known Hold Fixtures (Optional Backup Checks)

These are useful for quick EXPIRED/CONFIRMED sanity checks if live flow timing is unstable:

- `9d300000-0000-0000-0000-000000000002` -> `EXPIRED`
- `9d300000-0000-0000-0000-000000000003` -> `CONFIRMED`
- `40000000-0000-0000-0000-000000000003` -> `EXPIRED`

### 1.4 Demo User Strategy

For a UI demo, create two fresh fan accounts from `/sign-up`:

- Fan A email: `scenario1.ui.a.<timestamp>@ticketblitz.com`
- Fan B email: `scenario1.ui.b.<timestamp>@ticketblitz.com`
- Password for both: `TicketBlitz#2026!`

Use separate browser sessions (normal + incognito) so Fan A and Fan B stay logged in simultaneously.

## 2) Preflight Setup

### 2.1 Environment

Frontend (`frontend/.env.local`):

- `VITE_API_BASE_URL=/api`
- `VITE_CUSTOMER_API_KEY=ticketblitz-customer-dev-key`
- `VITE_STRIPE_PUBLISHABLE_KEY=pk_test_...`

Backend (`.env.local` at repo root):

- `SUPABASE_URL`
- `SUPABASE_SERVICE_KEY`
- `RABBITMQ_URL`, `RABBITMQ_USER`, `RABBITMQ_PASSWORD`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `INTERNAL_SERVICE_TOKEN`
- `OUTSYSTEMS_BASE_URL`
- `OUTSYSTEMS_API_KEY`

### 2.2 Start backend stack

```bash
docker compose --env-file .env.local up -d --build
```

Quick checks:

```bash
curl -s http://localhost:8000/events
curl -s http://localhost:6001/health
curl -s http://localhost:6002/health
curl -s http://localhost:5004/health
```

### 2.3 Start frontend

```bash
cd frontend
npm install
npm run dev
```

### 2.4 Start Stripe webhook forwarding (required for CONFIRMED path)

```bash
stripe listen --forward-to localhost:8000/payment/webhook
```

If Stripe CLI prints a new `whsec_...`, update `STRIPE_WEBHOOK_SECRET` and restart payment service:

```bash
docker compose restart payment-service
```

## 3) UI Route Outcomes (Expected)

Use these route transitions as acceptance criteria:

- Reserve success path: `/ticket-purchase` -> `/booking/pending/:holdID` -> `/booking/result/:holdID?status=CONFIRMED`
- Sold-out path: `/ticket-purchase` -> `/waitlist/:waitlistID`
- Waitlist offer path: `/waitlist/:waitlistID` -> `/waitlist/confirm/:holdID` -> `/booking/pending/:holdID`
- Expired offer path: `/waitlist/confirm/:holdID` -> `/booking/result/:holdID?status=EXPIRED`
- Ticket visibility path: `/my-tickets` shows confirmed ticket cards

## 4) Step 1A (Seat Available -> CONFIRMED)

1. Sign in as Fan A.
2. Open `/ticket-purchase`.
3. Select event `EVT-301` and category `PEN`, qty `1`.
4. Click `Reserve Ticket`.
5. Verify redirect to `/booking/pending/:holdID`.
6. In Stripe Payment Element, use card `4242 4242 4242 4242`.
7. Click `Confirm Payment`.
8. Verify transition to booking result with confirmed state.
9. Open `/my-tickets` and verify one confirmed ticket appears.

Expected UI text:

- Booking result heading: `Booking Confirmed`
- My Tickets count increments by 1

Optional API proof:

```bash
curl -s "http://localhost:8000/booking-status/<HOLD_ID_FROM_UI>" \
  -H "x-customer-api-key: ticketblitz-customer-dev-key"
```

Expected terminal state: `uiStatus: "CONFIRMED"`.

## 5) Step 1B (Sold Out -> WAITLISTED)

1. Stay signed in as Fan A.
2. Open `/ticket-purchase`.
3. Select event `EVT-301`, category `CAT2`, qty `1`.
4. Click `Reserve Ticket`.
5. Verify redirect to `/waitlist/:waitlistID`.

Expected UI on waitlist page:

- Status displays `WAITLISTED`/`WAITING`
- Position is shown and updates while polling

Optional API proof:

```bash
curl -s "http://localhost:8000/waitlist/<WAITLIST_ID_FROM_UI>" \
  -H "x-customer-api-key: ticketblitz-customer-dev-key"
```

Expected: `status: "WAITING"`.

## 6) Step 1C (Seat Released -> HOLD_OFFERED -> PAYMENT_PENDING -> CONFIRMED)

This section uses two users to make the release and offer sequence deterministic without relying on missing seed files.

### 6.1 Fan B creates a temporary hold on CAT1

1. In Browser Session B (Fan B), open `/ticket-purchase`.
2. Reserve `EVT-301`, category `CAT1`, qty `5`.
3. Stop at `/booking/pending/:holdID` and do not complete payment.
4. Capture this hold ID as `HOLD_B_SOURCE`.

### 6.2 Fan A joins waitlist for CAT1

1. In Browser Session A (Fan A), open `/ticket-purchase`.
2. Reserve `EVT-301`, category `CAT1`, qty `1`.
3. Verify redirect to `/waitlist/:waitlistID` and capture `WAITLIST_A`.

If CAT1 still shows available seats, increase the held quantity from Fan B or create one additional temporary hold from Fan B, then retry.

### 6.3 Release Fan B hold to trigger promotion

Run from terminal:

```bash
curl -s -X PUT "http://localhost:5003/inventory/hold/<HOLD_B_SOURCE>/release" \
  -H "Content-Type: application/json" \
  -d '{"reason":"PAYMENT_TIMEOUT"}'
```

### 6.4 Verify waitlist offer in UI

1. Keep Fan A on `/waitlist/:waitlistID`.
2. Wait for polling to detect offer and redirect to `/waitlist/confirm/:holdID`.
3. Verify page indicates waitlist offer and active payment window.
4. Click `Continue To Payment`.
5. Verify redirect to `/booking/pending/:offeredHoldID`.

### 6.5 Complete payment from offer

1. On pending page for `offeredHoldID`, submit Stripe success card `4242 4242 4242 4242`.
2. Verify final state is confirmed and appears in `/my-tickets` for Fan A.

## 7) Step 1D (Timeout -> EXPIRED)

Use the same promoted hold flow as Step 1C, but intentionally do not pay.

1. Reach `/waitlist/confirm/:holdID` for Fan A.
2. Do not click `Continue To Payment`.
3. Wait past hold expiry window plus scheduler/polling interval.
4. Verify redirect to `/booking/result/:holdID?status=EXPIRED`.

Expected UI text:

- Heading: `Hold Expired`
- Message indicates payment window expired

Optional API proof:

```bash
curl -s "http://localhost:8000/booking-status/<EXPIRED_HOLD_ID>" \
  -H "x-customer-api-key: ticketblitz-customer-dev-key"
```

Expected: `uiStatus: "EXPIRED"`.

## 8) Supabase Validation Queries (Read-Only)

Run these in Supabase SQL editor to validate state transitions after the UI demo.

### 8.1 Event/category availability snapshot

```sql
select
  c.event_id,
  e.event_code,
  c.category_code,
  c.name as category_name,
  count(*) filter (where s.status = 'AVAILABLE') as available_seats,
  count(*) filter (where s.status = 'PENDING_WAITLIST') as pending_waitlist_seats,
  count(*) filter (where s.status = 'HELD') as held_seats,
  count(*) filter (where s.status = 'SOLD') as sold_seats,
  count(*) as total_seats
from public.seat_categories c
join public.events e on e.event_id = c.event_id
left join public.seats s on s.category_id = c.category_id
where c.event_id = '10000000-0000-0000-0000-000000000301'
group by c.event_id, e.event_code, c.category_code, c.name
order by c.category_code;
```

### 8.2 Hold lifecycle for captured IDs

```sql
select hold_id, user_id, status, hold_expires_at, confirmed_at, expired_at, release_reason, updated_at
from public.seat_holds
where hold_id in (
  '<HOLD_ID_1A>',
  '<HOLD_B_SOURCE>',
  '<OFFERED_HOLD_ID_1C>',
  '<EXPIRED_HOLD_ID_1D>'
)
order by updated_at desc;
```

### 8.3 Waitlist lifecycle

```sql
select waitlist_id, user_id, event_id, status, hold_id, joined_at, offered_at, confirmed_at, expired_at
from public.waitlist_entries
where waitlist_id in ('<WAITLIST_A>')
   or hold_id in ('<OFFERED_HOLD_ID_1C>', '<EXPIRED_HOLD_ID_1D>')
order by coalesce(confirmed_at, expired_at, offered_at, joined_at) desc;
```

### 8.4 Payment transaction state

```sql
select hold_id, stripe_payment_intent_id, status, amount, updated_at
from public.transactions
where hold_id in ('<HOLD_ID_1A>', '<OFFERED_HOLD_ID_1C>', '<EXPIRED_HOLD_ID_1D>')
order by updated_at desc;
```

## 9) Condensed Demo Script (Presentation Order)

1. Show stack health and Stripe webhook listener.
2. Sign up/sign in Fan A and Fan B in separate sessions.
3. Execute Step 1A and show confirmed ticket in `/my-tickets`.
4. Execute Step 1B and show waitlist position in `/waitlist/:waitlistID`.
5. Execute Step 1C with controlled release and show promotion to `/waitlist/confirm/:holdID`.
6. Complete payment and show confirmed result.
7. Execute Step 1D once by waiting out an offer and show expired result route.
8. Run Supabase validation queries to prove all state transitions.

## 10) Fast Troubleshooting

### Payment remains pending

```bash
docker compose logs --tail 200 payment-service
docker compose restart payment-service
```

Also verify the active Stripe CLI secret matches `STRIPE_WEBHOOK_SECRET`.

### Waitlist offer does not appear

```bash
docker compose logs --tail 200 waitlist-promotion-orchestrator
docker compose logs --tail 200 inventory-service
```

Confirm that the released hold category matches the waitlisted category.

### Expiry does not trigger

```bash
docker compose logs --tail 200 expiry-scheduler-service
docker compose logs --tail 200 waitlist-promotion-orchestrator
```

### My Tickets missing newly confirmed entry

- Hard refresh `/my-tickets` after booking result confirms.
- Verify `/etickets/user/{userID}` is reachable through Kong.
- Verify OutSystems credentials in backend env.
