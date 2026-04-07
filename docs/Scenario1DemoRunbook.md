# Scenario 1 UI Demo Runbook (TicketBlitz)

Last validated: 2026-04-08
Supabase project: `cpxcpvcfbohvpiubbujg`

## 1) Goal

Run Scenario 1 end-to-end through the UI with reproducible checks for:

1. Step 1A: seat available -> `PAYMENT_PENDING` -> `PROCESSING` -> `CONFIRMED`
2. Step 1B: sold out -> `WAITLISTED` / `WAITING`
3. Step 1C: seat released -> `HOLD_OFFERED` -> `PAYMENT_PENDING` -> `CONFIRMED`
4. Step 1D: offer timeout -> `EXPIRED`

This runbook is aligned with:

- `docs/Setup.md`
- `docs/Scenarios.md`
- Frontend route behavior in:
  - `/ticket-purchase`
  - `/booking/pending/:holdID`
  - `/booking/result/:holdID`
  - `/waitlist/:waitlistID`
  - `/waitlist/confirm/:holdID`
  - `/my-tickets`

## 2) Constraints You Must Respect

## 2.1 Enforced by current application

- Reservation quantity is fixed to 1 (`qty=1`) in UI and backend (`/reserve`, `/inventory/hold`, `/waitlist/join`).
- Waitlist supports one active entry per user per event/category (`WAITING` or `HOLD_OFFERED`) via unique index.
- Hold default duration is 600 seconds (10 minutes) unless overridden by `HOLD_DURATION_SECONDS`.

## 2.2 Demo discipline (for clean judging and repeatability)

Even though historical data already contains users with multiple confirmed holds, run this demo with a one-ticket-per-user discipline:

- Use different fan accounts for each confirmed purchase outcome.
- Do not reuse a user for more than one confirmed ticket during this demo run.

## 3) Live Data Pack (from Supabase)

Primary event for Scenario 1:

- Event ID: `10000000-0000-0000-0000-000000000301`
- Event code: `EVT-301`
- Event name: `Coldplay Live 2026`
- Event status: `ACTIVE`

Current category snapshot for `EVT-301`:

- `CAT1`: available=5, pending_waitlist=3, sold=3, total=11
- `CAT2`: available=0, pending_waitlist=0, sold=3, total=3
- `PEN`: available=3, pending_waitlist=0, sold=7, total=10

Recommended category usage:

- Step 1A: `CAT1` (stable available)
- Step 1B: `CAT2` (stable sold out)
- Step 1C/1D: `PEN` (small pool, easy to force sold out then promote)

## 4) Demo User Matrix

Create these fan accounts using `/sign-up` (normal + incognito windows). Use the same password for all, for example `TicketBlitz#2026!`.

- Fan A: Step 1A confirmer
- Fan B: Step 1B waitlist-only user
- Fan C: PEN blocker hold #1 (no payment)
- Fan D: PEN blocker hold #2 (no payment)
- Fan E: PEN blocker hold #3 (no payment)
- Fan F: Step 1C waitlist promoted confirmer
- Fan G: Step 1D waitlist promoted timeout user

Suggested email format:

- `scenario1.ui.a.<timestamp>@ticketblitz.com`
- `scenario1.ui.b.<timestamp>@ticketblitz.com`
- ... up to Fan G

## 5) Preflight Setup

## 5.1 Start backend and frontend

```bash
docker compose --env-file .env.local up -d --build
cd frontend
npm install
npm run dev
```

## 5.2 Start Stripe webhook forwarding

```bash
stripe listen --forward-to localhost:8000/payment/webhook
```

Keep this terminal open.

If payment stays pending after confirmation, verify the currently active `whsec_...` matches `STRIPE_WEBHOOK_SECRET`, then restart payment service:

```bash
docker compose restart payment-service
```

## 5.3 Health checks

```bash
curl -s http://localhost:8000/events
curl -s http://localhost:6001/health
curl -s http://localhost:6002/health
curl -s http://localhost:5004/health
```

## 5.4 Kong API key expectation

This runbook assumes frontend customer key `ticketblitz-customer-dev-key` is active in Kong for `x-customer-api-key`.

## 6) Route and UI Assertions

Expected route outcomes:

- Available reservation: `/ticket-purchase` -> `/booking/pending/:holdID` -> `/booking/result/:holdID?status=CONFIRMED`
- Sold-out reservation: `/ticket-purchase` -> `/waitlist/:waitlistID`
- Waitlist offer: `/waitlist/:waitlistID` -> `/waitlist/confirm/:holdID` -> `/booking/pending/:holdID`
- Offer expiry: `/waitlist/confirm/:holdID` -> `/booking/result/:holdID?status=EXPIRED`

Expected booking result headings:

- `CONFIRMED` -> `Booking Confirmed`
- `EXPIRED` -> `Hold Expired`
- `FAILED_PAYMENT` -> `Payment Failed`

## 7) Step-by-Step Execution

## 7.1 Step 1A (Seat Available -> CONFIRMED)

1. Sign in as Fan A.
2. Open `/ticket-purchase`.
3. Select event `EVT-301`, category `CAT1`.
4. Click `Reserve Ticket`.
5. Confirm route is `/booking/pending/:holdID`.
6. Use Stripe test card `4242 4242 4242 4242` and confirm payment.
7. Verify `/booking/result/:holdID?status=CONFIRMED`.
8. Open `/my-tickets`, verify a new confirmed ticket card.

Capture `HOLD_1A`.

## 7.2 Step 1B (Sold Out -> WAITLISTED)

1. Sign in as Fan B.
2. Open `/ticket-purchase`.
3. Select event `EVT-301`, category `CAT2`.
4. Click `Reserve Ticket`.
5. Verify redirect to `/waitlist/:waitlistID`.
6. Verify waitlist status page shows waiting/position polling.

Capture `WAITLIST_1B`.

## 7.3 Prepare Step 1C/1D by forcing PEN sold out

You need `PEN` to become sold out so promotion can be demonstrated deterministically.

1. Fan C reserves `EVT-301` + `PEN`, stops at `/booking/pending/:holdID` (do not pay). Capture `HOLD_PEN_C`.
2. Fan D reserves `EVT-301` + `PEN`, stops at pending (do not pay). Capture `HOLD_PEN_D`.
3. Fan E reserves `EVT-301` + `PEN`, stops at pending (do not pay). Capture `HOLD_PEN_E`.

After this, `PEN` should have no public available seats.

## 7.4 Step 1C (Release -> HOLD_OFFERED -> CONFIRMED)

1. Sign in as Fan F.
2. Reserve `EVT-301` + `PEN`.
3. Confirm redirect to `/waitlist/:waitlistID`. Capture `WAITLIST_1C`.
4. In terminal, release one blocker hold (example uses Fan C hold):

```bash
curl -s -X PUT "http://localhost:5003/inventory/hold/<HOLD_PEN_C>/release" \
  -H "Content-Type: application/json" \
  -d '{"reason":"MANUAL_RELEASE"}'
```

5. Keep Fan F on waitlist page; verify auto-redirect to `/waitlist/confirm/:holdID` when offer arrives.
6. Click `Continue To Payment`.
7. Verify redirect to `/booking/pending/:holdID`.
8. Complete payment with Stripe card `4242 4242 4242 4242`.
9. Verify terminal state `/booking/result/:holdID?status=CONFIRMED` and ticket visibility in `/my-tickets`.

Capture `HOLD_1C`.

## 7.5 Step 1D (Offer Timeout -> EXPIRED)

1. Sign in as Fan G.
2. Reserve `EVT-301` + `PEN`.
3. Confirm redirect to `/waitlist/:waitlistID`. Capture `WAITLIST_1D`.
4. Release another blocker hold (for example `HOLD_PEN_D`) to trigger promotion:

```bash
curl -s -X PUT "http://localhost:5003/inventory/hold/<HOLD_PEN_D>/release" \
  -H "Content-Type: application/json" \
  -d '{"reason":"PAYMENT_TIMEOUT"}'
```

5. Verify redirect to `/waitlist/confirm/:holdID` and capture `HOLD_1D`.
6. Do not click continue and do not pay.
7. Wait for hold expiry (default about 10 minutes) plus scheduler interval.
8. Verify redirect to `/booking/result/:holdID?status=EXPIRED`.

## 8) API Spot Checks During Demo

Use these only as supporting evidence.

```bash
curl -s "http://localhost:8000/booking-status/<HOLD_ID>" \
  -H "x-customer-api-key: ticketblitz-customer-dev-key"
```

```bash
curl -s "http://localhost:8000/waitlist/<WAITLIST_ID>" \
  -H "x-customer-api-key: ticketblitz-customer-dev-key"
```

## 9) Supabase Validation Queries (Read-Only)

Run in SQL Editor after demo. Use the `postgres` role for full admin visibility, or switch role explicitly when testing RLS behavior.

## 9.1 Category inventory snapshot

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

## 9.2 Hold lifecycle for captured IDs

```sql
select
  hold_id,
  user_id,
  from_waitlist,
  status,
  hold_expires_at,
  confirmed_at,
  expired_at,
  released_at,
  release_reason,
  updated_at
from public.seat_holds
where hold_id in (
  '<HOLD_1A>',
  '<HOLD_PEN_C>',
  '<HOLD_PEN_D>',
  '<HOLD_PEN_E>',
  '<HOLD_1C>',
  '<HOLD_1D>'
)
order by updated_at desc;
```

## 9.3 Waitlist lifecycle

```sql
select
  waitlist_id,
  user_id,
  event_id,
  category_id,
  status,
  source,
  hold_id,
  joined_at,
  offered_at,
  confirmed_at,
  expired_at,
  metadata
from public.waitlist_entries
where waitlist_id in ('<WAITLIST_1B>', '<WAITLIST_1C>', '<WAITLIST_1D>')
   or hold_id in ('<HOLD_1C>', '<HOLD_1D>')
order by coalesce(confirmed_at, expired_at, offered_at, joined_at) desc;
```

## 9.4 Payment transactions

```sql
select
  hold_id,
  stripe_payment_intent_id,
  status,
  amount,
  currency,
  created_at,
  updated_at
from public.transactions
where hold_id in ('<HOLD_1A>', '<HOLD_1C>', '<HOLD_1D>')
order by updated_at desc;
```

## 9.5 One-ticket-per-user demo guardrail check

This should return zero rows for your demo users.

```sql
select user_id, event_id, count(*) as confirmed_count
from public.seat_holds
where status = 'CONFIRMED'
  and user_id in (
    '<FAN_A_USER_ID>',
    '<FAN_F_USER_ID>'
  )
group by user_id, event_id
having count(*) > 1;
```

## 10) Presentation Order (Concise)

1. Show services healthy and Stripe `listen` running.
2. Step 1A with Fan A (confirmed booking).
3. Step 1B with Fan B (waitlisted due to sold-out category).
4. Build PEN sold-out condition with Fans C/D/E (pending holds, no payment).
5. Step 1C with Fan F (promotion then confirmed payment).
6. Step 1D with Fan G (promotion then timeout to expired).
7. Run SQL validation queries for evidence.

## 11) Troubleshooting

Payment stuck in pending:

```bash
docker compose logs --tail 200 payment-service
docker compose restart payment-service
```

Waitlist offer not appearing:

```bash
docker compose logs --tail 200 waitlist-promotion-orchestrator
docker compose logs --tail 200 inventory-service
```

Expiry not triggering:

```bash
docker compose logs --tail 200 expiry-scheduler-service
docker compose logs --tail 200 waitlist-promotion-orchestrator
```

If runtime behavior does not match source routes, rebuild affected containers to avoid stale images:

```bash
docker compose up -d --build --force-recreate
```
