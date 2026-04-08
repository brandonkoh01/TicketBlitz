# Scenario 1 UI Demo Runbook (TicketBlitz Frontend)

## Objective
Run Scenario 1 end-to-end from the frontend UI while validating key state transitions through Kong-backed APIs and Supabase (project `cpxcpvcfbohvpiubbujg`).

This runbook covers:

1. Step 1A: `PAYMENT_PENDING` -> `PROCESSING` -> `CONFIRMED`
2. Step 1B: sold-out purchase -> `WAITLISTED` (`WAITING`)
3. Step 1C: waitlist promotion -> `WAITLIST_OFFERED` -> `PAYMENT_PENDING` -> `CONFIRMED`
4. Step 1D: offer timeout -> `EXPIRED`

This runbook is aligned to:

- `docs/Setup.md`
- `docs/Scenarios.md`
- frontend routes in `/ticket-purchase`, `/booking/pending/:holdID`, `/waitlist/:waitlistID`, `/waitlist/confirm/:holdID`, `/booking/result/:holdID`, `/my-tickets`

## 1) Context and Constraints

### 1.1 Architecture assumptions (from Setup + Scenarios)

- UI calls go through Kong (`localhost:8000`).
- Reservation flow is orchestrated via `reservation-orchestrator` and polled via `booking-status-service`.
- Payment confirmation is webhook-driven (Stripe -> payment-service -> async orchestration).
- Waitlist promotion is async (`seat.released` -> waitlist-promotion-orchestrator).

### 1.2 Enforced constraints (verified in current code + DB)

- Reservation quantity is hard-limited to `qty=1`.
- Inventory hold creation is hard-limited to `qty=1`.
- Waitlist join is hard-limited to `qty=1`.
- Active waitlist uniqueness is enforced by DB index:
  `waitlist_entries_active_user_uk` on `(event_id, category_id, user_id)` for statuses `WAITING`/`HOLD_OFFERED`.
- One active hold per seat is enforced by DB index:
  `seat_holds_active_seat_uk` for `status='HELD'`.

### 1.3 Demo policy

To satisfy the one-ticket-per-user demo policy, this runbook uses separate fan accounts for each confirmed purchase path.

## 2) Live Data Pack (Supabase snapshot on 2026-04-08)

### 2.1 Primary event

- Event ID: `10000000-0000-0000-0000-000000000301`
- Event code: `EVT-301`
- Name: `Coldplay Live 2026`
- Status: `ACTIVE`
- Booking window: `booking_opens_at=2026-03-15 01:00:00+00`, `booking_closes_at=2026-06-01 11:00:00+00`

### 2.2 Category snapshot for EVT-301

- `CAT1`: available=4, pending_waitlist=3, held=0, sold=4, total=11
- `CAT2`: available=0, pending_waitlist=0, held=0, sold=3, total=3
- `PEN`: available=3, pending_waitlist=0, held=0, sold=7, total=10

Recommended use:

- `PEN` for stable Step 1A (seat available).
- `CAT2` for stable Step 1B (immediate waitlist).
- `CAT1` for controlled Step 1C/1D promotion and timeout.

### 2.3 Known fixture IDs (optional fallback checks)

Holds:

- `9d300000-0000-0000-0000-000000000001` -> `EXPIRED`
- `9d300000-0000-0000-0000-000000000002` -> `EXPIRED`
- `9d300000-0000-0000-0000-000000000003` -> `CONFIRMED`
- `40000000-0000-0000-0000-000000000003` -> `EXPIRED`
- `40000000-0000-0000-0000-000000000004` -> `CONFIRMED`

Transactions observed:

- `9d300...0003` -> `SUCCEEDED`
- `9d300...0001` -> `PENDING` (multiple attempts)

## 3) Demo User Matrix (One Ticket Per User)

Create these from `/sign-up` with password `TicketBlitz#2026!`:

- Fan A: `scenario1.ui.a.<timestamp>@ticketblitz.com` (Step 1A only)
- Fan B: `scenario1.ui.b.<timestamp>@ticketblitz.com` (Step 1B only)
- Fan C: `scenario1.ui.c.<timestamp>@ticketblitz.com` (Step 1C only)
- Fan D: `scenario1.ui.d.<timestamp>@ticketblitz.com` (Step 1D only)

Temporary seeder users for CAT1 supply (no payment completion):

- Seeder emails: `scenario1.seed.1.<timestamp>@ticketblitz.com`, `scenario1.seed.2...`, etc.
- Create as many seeders as current CAT1 available count (`N`).
- From snapshot above, start with `N=4`.

Session setup:

- Keep one normal browser window and multiple incognito/profile windows.
- Keep each account signed in on exactly one window for cleaner hold/waitlist tracing.

## 4) Preflight Setup

### 4.1 Environment

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

### 4.2 Start backend

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

### 4.3 Start frontend

```bash
cd frontend
npm install
npm run dev
```

### 4.4 Start Stripe forwarding (required for confirmed paths)

```bash
stripe listen --forward-to localhost:8000/payment/webhook
```

Context7 (Stripe CLI) guidance:

- `listen --forward-to` is the correct local webhook path.
- `stripe trigger payment_intent.succeeded` and `stripe trigger payment_intent.payment_failed` are valid test triggers.

If the displayed signing secret differs from your current backend value, update `STRIPE_WEBHOOK_SECRET` and restart payment service:

```bash
docker compose restart payment-service
```

## 5) Route and UI Assertions

Use these route transitions as acceptance criteria:

- Reserve success: `/ticket-purchase` -> `/booking/pending/:holdID` -> `/booking/result/:holdID?status=CONFIRMED`
- Sold out: `/ticket-purchase` -> `/waitlist/:waitlistID`
- Waitlist offer: `/waitlist/:waitlistID` -> `/waitlist/confirm/:holdID` -> `/booking/pending/:holdID`
- Offer expiry: `/waitlist/confirm/:holdID` (or pending polling) -> `/booking/result/:holdID?status=EXPIRED`

Expected UI labels:

- Waitlist page heading: `You are waitlisted.`
- Waitlist confirm button: `Continue To Payment`
- Booking result headings: `Booking Confirmed`, `Hold Expired`, `Payment Failed`, `Booking Processing`

## 6) Scenario 1 Execution

## 6.1 Step 1A (Seat Available -> CONFIRMED)

1. Sign in as Fan A.
2. Go to `/ticket-purchase`.
3. Select `EVT-301`, seat category `PEN`.
4. Click `Reserve Ticket`.
5. Verify redirect to `/booking/pending/:holdID`.
6. Submit Stripe payment with test card `4242 4242 4242 4242`.
7. Verify `/booking/result/:holdID?status=CONFIRMED`.
8. Open `/my-tickets` and verify one new confirmed ticket card appears.

Optional API proof:

```bash
curl -s "http://localhost:8000/booking-status/<HOLD_ID_1A>" \
  -H "x-customer-api-key: ticketblitz-customer-dev-key"
```

Expected: `uiStatus: "CONFIRMED"`.

## 6.2 Step 1B (Sold Out -> WAITLISTED)

1. Sign in as Fan B.
2. Go to `/ticket-purchase`.
3. Select `EVT-301`, seat category `CAT2`.
4. Click `Reserve Ticket`.
5. Verify redirect to `/waitlist/:waitlistID`.
6. Confirm page shows waitlist status and queue position.

Optional API proof:

```bash
curl -s "http://localhost:8000/waitlist/<WAITLIST_ID_1B>" \
  -H "x-customer-api-key: ticketblitz-customer-dev-key"
```

Expected: `status: "WAITING"`.

## 6.3 Prepare CAT1 promotion pool (UI-led seeding)

Goal: make CAT1 sold out so Fan C/Fan D can enter waitlist, then release one hold at a time to drive 1C and 1D.

1. For each Seeder user, sign in and open `/ticket-purchase`.
2. Reserve `EVT-301`, category `CAT1` once (qty is fixed to 1 by backend).
3. Stop at `/booking/pending/:holdID`; do not pay.
4. Capture each Seeder hold ID in a list `SEED_HOLDS`.
5. Repeat until CAT1 reservations for non-seeder users route to waitlist (or until CAT1 available hits 0 in SQL check).

## 6.4 Step 1C (Promotion -> WAITLIST_OFFERED -> CONFIRMED)

1. Sign in as Fan C.
2. Reserve `EVT-301`, `CAT1` from `/ticket-purchase`.
3. Verify redirect to `/waitlist/:waitlistID` and capture `WAITLIST_ID_1C`.
4. Release one Seeder hold to trigger promotion:

```bash
curl -s -X PUT "http://localhost:5003/inventory/hold/<SEED_HOLD_ID_FOR_1C>/release" \
  -H "Content-Type: application/json" \
  -d '{"reason":"PAYMENT_TIMEOUT"}'
```

5. Keep Fan C on waitlist page and wait for auto-redirect to `/waitlist/confirm/:holdID`.
6. Verify UI status is offered (`WAITLIST_OFFERED` on confirm page payload).
7. Click `Continue To Payment`.
8. On pending page, submit Stripe success card `4242 4242 4242 4242`.
9. Verify final confirmed route and ticket appears in Fan C `/my-tickets`.

## 6.5 Step 1D (Offer timeout -> EXPIRED)

1. Sign in as Fan D.
2. Reserve `EVT-301`, `CAT1` until redirected to `/waitlist/:waitlistID`.
3. Release another Seeder hold to trigger a new offer:

```bash
curl -s -X PUT "http://localhost:5003/inventory/hold/<SEED_HOLD_ID_FOR_1D>/release" \
  -H "Content-Type: application/json" \
  -d '{"reason":"PAYMENT_TIMEOUT"}'
```

4. Wait for `/waitlist/confirm/:holdID` for Fan D.
5. Do not click `Continue To Payment`.
6. Wait past hold-expiry window plus scheduler/poll interval.
7. Verify `/booking/result/:holdID?status=EXPIRED`.
8. Verify result heading shows `Hold Expired`.

Optional API proof:

```bash
curl -s "http://localhost:8000/booking-status/<EXPIRED_HOLD_ID_1D>" \
  -H "x-customer-api-key: ticketblitz-customer-dev-key"
```

Expected: `uiStatus: "EXPIRED"`.

## 7) Supabase Validation Queries (Read-Only)

Run after demo execution.

### 7.1 Category inventory snapshot (EVT-301)

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

### 7.2 Hold lifecycle for demo IDs

```sql
select
  h.hold_id,
  h.user_id,
  u.email,
  h.status,
  h.hold_expires_at,
  h.confirmed_at,
  h.expired_at,
  h.released_at,
  h.updated_at
from public.seat_holds h
left join public.users u on u.user_id = h.user_id
where h.hold_id in (
  '<HOLD_ID_1A>',
  '<SEED_HOLD_ID_FOR_1C>',
  '<OFFERED_HOLD_ID_1C>',
  '<SEED_HOLD_ID_FOR_1D>',
  '<EXPIRED_HOLD_ID_1D>'
)
order by h.updated_at desc;
```

### 7.3 Waitlist lifecycle for Step 1B/1C/1D

```sql
select
  w.waitlist_id,
  w.user_id,
  u.email,
  c.category_code,
  w.status,
  w.hold_id,
  w.joined_at,
  w.offered_at,
  w.confirmed_at,
  w.expired_at
from public.waitlist_entries w
join public.seat_categories c on c.category_id = w.category_id
left join public.users u on u.user_id = w.user_id
where w.waitlist_id in ('<WAITLIST_ID_1B>', '<WAITLIST_ID_1C>', '<WAITLIST_ID_1D>')
   or w.hold_id in ('<OFFERED_HOLD_ID_1C>', '<EXPIRED_HOLD_ID_1D>')
order by coalesce(w.confirmed_at, w.expired_at, w.offered_at, w.joined_at) desc;
```

### 7.4 Payment transaction state for demo holds

```sql
select
  hold_id,
  stripe_payment_intent_id,
  status,
  amount,
  currency,
  updated_at
from public.transactions
where hold_id in ('<HOLD_ID_1A>', '<OFFERED_HOLD_ID_1C>', '<EXPIRED_HOLD_ID_1D>')
order by updated_at desc;
```

### 7.5 One-ticket-per-user demo assertion

Use your demo start timestamp in UTC.

```sql
select
  u.email,
  count(*) filter (where h.status = 'CONFIRMED') as confirmed_holds_during_demo
from public.seat_holds h
join public.users u on u.user_id = h.user_id
where h.created_at >= '<DEMO_START_UTC>'
  and u.email in (
    '<FAN_A_EMAIL>',
    '<FAN_B_EMAIL>',
    '<FAN_C_EMAIL>',
    '<FAN_D_EMAIL>'
  )
group by u.email
order by u.email;
```

Expected: each user is `0` or `1`, never greater than `1`.

## 8) Condensed Presenter Script

1. Show stack health and active Stripe listener.
2. Execute Step 1A with Fan A (`PEN`) and show confirmed result + My Tickets.
3. Execute Step 1B with Fan B (`CAT2`) and show waitlist status page.
4. Seed CAT1 temporary holds (UI-only reserve, no payment).
5. Execute Step 1C with Fan C (waitlist -> offer -> pay -> confirmed).
6. Execute Step 1D with Fan D (waitlist -> offer -> do not pay -> expired).
7. Run Supabase validation SQL to prove state transitions.

## 9) Troubleshooting

### Payment remains pending

```bash
docker compose logs --tail 200 payment-service
docker compose restart payment-service
```

Also confirm webhook forwarding is active and signing secret matches backend env.

### Waitlist offer does not appear

```bash
docker compose logs --tail 200 waitlist-promotion-orchestrator
docker compose logs --tail 200 inventory-service
```

Confirm released Seeder hold category matches the waiting user category (`CAT1`).

### Expiry does not trigger

```bash
docker compose logs --tail 200 expiry-scheduler-service
docker compose logs --tail 200 waitlist-promotion-orchestrator
```

### My Tickets missing newly confirmed entry

- Refresh `/my-tickets`.
- Recheck `/booking/result/:holdID` status query.
- Verify OutSystems connectivity/env keys for e-ticket generation.
