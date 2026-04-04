# Scenario 1 Demo Runbook

## Goal
Drive the full Scenario 1 fan flow from reserve to booking result using the current TicketBlitz stack.

## Prerequisites
1. Docker services are running with .env.local.
2. Frontend env points to Kong:
   - VITE_API_BASE_URL=/api
   - VITE_CUSTOMER_API_KEY=ticketblitz-customer-dev-key
3. Stripe publishable key is still required for full card-entry UI in Booking Pending page:
   - Set VITE_STRIPE_PUBLISHABLE_KEY in frontend/.env.local
4. Local webhook fallback is enabled for demo automation:
   - STRIPE_WEBHOOK_SECRET=whsec_ticketblitz_local_demo

## Start Services
Run from repository root.

```bash
 docker compose --env-file .env.local up -d
```

## Frontend Startup
Run from frontend folder.

```bash
 npm install
 npm run dev
```

## Scenario 1A: Available Seat Path
1. Open fan UI at /ticket-purchase.
2. Choose active event with available inventory.
3. Click Reserve Ticket.
4. Expected response path: PAYMENT_PENDING.
5. UI should route to /booking/pending/:holdID.

## Scenario 1B: Waitlist Path
1. Choose sold-out event and category.
2. Click Reserve Ticket.
3. Expected response path: WAITLISTED with waitlistID.
4. UI should route to /waitlist/:waitlistID and show queue status.

## Scenario 1C: Waitlist Offer to Payment
1. When promoted, UI auto-routes to /waitlist/confirm/:holdID.
2. Click Continue To Payment.
3. UI should route to /booking/pending/:holdID.

## Scenario 1D: Payment Confirmation and Ticket Visibility

### Option A: Real Stripe flow
1. Configure VITE_STRIPE_PUBLISHABLE_KEY.
2. Install Stripe CLI and run listener:

```bash
 stripe listen --forward-to http://localhost:5004/payment/webhook
```

3. Copy generated signing secret into STRIPE_WEBHOOK_SECRET in .env.local.
4. Restart payment-service.
5. Complete payment from Booking Pending page.
6. Expected progression:
   - booking-status uiStatus: PROCESSING -> CONFIRMED
   - UI route transitions to /booking/result/:holdID
   - Ticket appears in /my-tickets

### Option B: Local webhook simulation (no Stripe CLI)
1. Capture paymentIntentID from reserve response.
2. Trigger signed webhook from repository root.
    Use amount in minor units from reserve response (e.g. 160.00 SGD -> 16000):

```bash
 ./scripts/trigger_payment_webhook_success.sh <payment_intent_id> <amount_minor> [currency]
```

3. Poll booking status:

```bash
 curl -s http://localhost:8000/booking-status/<hold_id> | jq
```

4. Expected progression:
   - paymentStatus becomes SUCCEEDED
   - booking fulfillment processes booking.confirmed
   - uiStatus transitions PROCESSING -> CONFIRMED once ticket issuance is available

## Quick API Smoke Commands

```bash
 USER_ID=$(curl -s -H "X-Internal-Token: ticketblitz-internal-token" "http://localhost:5002/users?pageSize=1" | jq -r '.users[0].userID')
 EVENT_ID=10000000-0000-0000-0000-000000000301
 CATEGORY=CAT1

 curl -s -X POST "http://localhost:8000/reserve" \
   -H "Content-Type: application/json" \
   -H "x-customer-api-key: ticketblitz-customer-dev-key" \
   -H "X-User-ID: ${USER_ID}" \
   -d "{\"userID\":\"${USER_ID}\",\"eventID\":\"${EVENT_ID}\",\"seatCategory\":\"${CATEGORY}\",\"qty\":1}" | jq
```

## Known Limitations
1. Without VITE_STRIPE_PUBLISHABLE_KEY, Stripe Payment Element cannot mount in UI.
2. If you skip Stripe CLI, use local webhook simulation to progress payment state.
3. If endpoints unexpectedly 404 despite source definitions, rebuild stale images:

```bash
 docker compose --env-file .env.local build --no-cache <service>
 docker compose --env-file .env.local up -d <service>
```
