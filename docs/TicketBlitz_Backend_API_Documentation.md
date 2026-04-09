# TicketBlitz Backend API Documentation


## 1. Architecture Summary

TicketBlitz backend follows an atomic + composite + worker pattern:

- Atomic services own domain data and CRUD-like behavior.
- Composite services orchestrate multi-service workflows.
- Workers and schedulers handle asynchronous/event-driven behavior.

### 1.1 Service Inventory

| Service | Layer | Runtime | HTTP API | Host Port | Entry File |
|---|---|---|---|---|---|
| event-service | atomic | Flask | Yes | 5001 | `backend/atomic/event-service/event.py` |
| user-service | atomic | Flask + Blueprint | Yes | 5002 (localhost bind only) | `backend/atomic/user-service/user.py` |
| inventory-service | atomic | Flask + Flasgger | Yes | 5003 | `backend/atomic/inventory-service/inventory.py` |
| payment-service | atomic | Flask | Yes | 5004 | `backend/atomic/payment-service/payment.py` |
| waitlist-service | atomic | Flask + Blueprint | Yes | 5005 | `backend/atomic/waitlist-service/waitlist.py` |
| pricing-service | atomic | Flask | Yes | 5006 | `backend/atomic/pricing-service/pricing.py` |
| notification-service | atomic | RabbitMQ worker | No | N/A | `backend/atomic/notification-service/notification.py` |
| expiry-scheduler-service | atomic | scheduler worker | No | N/A | `backend/atomic/expiry-scheduler-service/expiry_scheduler.py` |
| reservation-orchestrator | composite | Flask + Blueprint | Yes | 6001 | `backend/composite/reservation-orchestrator/app.py` |
| booking-status-service | composite | Flask + Blueprint | Yes | 6002 | `backend/composite/booking-status-service/booking_status.py` |
| flash-sale-orchestrator | composite | Flask | Yes | 6003 | `backend/composite/flash-sale-orchestrator/flash_sale_orchestrator.py` |
| cancellation-orchestrator | composite | Flask + Blueprint | Yes | 6004 | `backend/composite/cancellation-orchestrator/cancellation_orchestrator.py` |
| booking-fulfillment-orchestrator | composite | RabbitMQ worker | No | N/A | `backend/composite/booking-fulfillment-orchestrator/booking_fulfillment_worker.py` |
| waitlist-promotion-orchestrator | composite | RabbitMQ worker | No | N/A | `backend/composite/waitlist-promotion-orchestrator/waitlist_promotion.py` |
| pricing-orchestrator | composite | RabbitMQ worker | No | N/A | `backend/composite/pricing-orchestrator/pricing_orchestrator.py` |

---

## 3. API Gateway Exposure (Kong)

Kong declarative config: `kong/kong.yml`

### 3.1 Global and Consumer Auth Setup

- Global CORS plugin is enabled with localhost origins for frontend dev and methods `GET, HEAD, PUT, PATCH, POST, DELETE, OPTIONS`.
- Customer API key header: `x-customer-api-key`
- Organiser API key header: `x-organiser-api-key`
- Consumers configured:
  - `customer-frontend` with key `ticketblitz-customer-dev-key`
  - `organiser-dashboard` with key `ticketblitz-organiser-dev-key` and ACL group `organisers`

### 3.2 Route Matrix (External Path -> Upstream)

| Kong Route Name | Methods | External Path Pattern | Upstream Service URL | Auth | Rate Limit |
|---|---|---|---|---|---|
| reserve | POST, OPTIONS | `/reserve` | `http://reservation-orchestrator:5000` | customer key-auth (`x-customer-api-key`) | 120/min |
| reserve-confirm | POST, OPTIONS | `/reserve/confirm` | `http://reservation-orchestrator:5000` | customer key-auth (`x-customer-api-key`) | 120/min |
| waitlist-confirm | GET, OPTIONS | `/waitlist/confirm` | `http://reservation-orchestrator:5000` | customer key-auth (`x-customer-api-key`) | 120/min |
| waitlist-my | GET, OPTIONS | `/reserve/waitlist/my` | `http://reservation-orchestrator:5000` | customer key-auth (`x-customer-api-key`) | 120/min |
| waitlist-leave | DELETE, OPTIONS | `/waitlist/leave` | `http://reservation-orchestrator:5000` | customer key-auth (`x-customer-api-key`) | 120/min |
| get-events | GET, OPTIONS | `/events` | `http://event-service:5000` | none | 120/min |
| get-event-by-id | GET, OPTIONS | `~/event/[^/]+$` | `http://event-service:5000` | none | 120/min |
| get-event-categories | GET, OPTIONS | `~/event/[^/]+/categories$` | `http://event-service:5000` | none | 120/min |
| update-event-status | PUT, OPTIONS | `~/event/[^/]+/status$` | `http://event-service:5000` | organiser key-auth + ACL organisers | 120/min |
| update-event-category-prices | PUT, OPTIONS | `~/event/[^/]+/categories/prices$` | `http://event-service:5000` | organiser key-auth + ACL organisers | 120/min |
| get-event-flash-sale-status | GET, OPTIONS | `~/event/[^/]+/flash-sale/status$` | `http://event-service:5000` | none | 120/min |
| get-event-price-history | GET, OPTIONS | `~/event/[^/]+/price-history$` | `http://event-service:5000` | none | 120/min |
| waitlist-public | GET, POST, PUT, DELETE, OPTIONS | `/waitlist` | `http://waitlist-service:5000` | none at Kong layer | 120/min |
| inventory-api | GET, OPTIONS | `/inventory` | `http://inventory-service:5000` | none | 180/min |
| booking-status | GET, OPTIONS | `~/booking-status/[^/]+$` | `http://booking-status-service:5000` | none | 240/min |
| cancel-booking | POST, OPTIONS | `~/bookings/cancel/[^/]+$` | `http://cancellation-orchestrator:5000` | none at Kong layer | 120/min |
| cancellation-status | GET, OPTIONS | `~/bookings/cancel/status/[^/]+$` | `http://cancellation-orchestrator:5000` | none at Kong layer | 120/min |
| cancellation-reallocation-confirm | POST, OPTIONS | `/orchestrator/cancellation/reallocation/confirm` | `http://cancellation-orchestrator:5000` | none at Kong layer | 120/min |
| cancellation-orchestrator-direct | POST, OPTIONS | `/orchestrator/cancellation` | `http://cancellation-orchestrator:5000` | none at Kong layer | 120/min |
| stripe-webhook | POST | `/payment/webhook` | `http://payment-service:5000` | none at Kong layer (Stripe signature validated upstream) | none |
| payment-user-bookings | GET, OPTIONS | `~/payments/user/[^/]+/bookings$` | `http://payment-service:5000` | none | none |
| get-pricing-snapshot | GET, OPTIONS | `~/pricing/[^/]+$` | `http://pricing-service:5000` | none | 120/min |
| get-pricing-history | GET, OPTIONS | `~/pricing/[^/]+/history$` | `http://pricing-service:5000` | none | 120/min |
| get-pricing-active-flash-sale | GET, OPTIONS | `~/pricing/[^/]+/flash-sale/active$` | `http://pricing-service:5000` | none | 120/min |
| flash-sale-launch | POST, OPTIONS | `/flash-sale/launch` | `http://flash-sale-orchestrator:5000` | organiser key-auth + ACL organisers | 30/min |
| flash-sale-end | POST, OPTIONS | `/flash-sale/end` | `http://flash-sale-orchestrator:5000` | organiser key-auth + ACL organisers | 30/min |
| flash-sale-status | GET, OPTIONS | `~/flash-sale/[^/]+/status$` | `http://flash-sale-orchestrator:5000` | none | 30/min |
| eticket-generate | POST, OPTIONS | `/eticket/generate` | `https://personal-kgqqcaoh.outsystemscloud.com/ETicket_API/rest/v1` | none at route level | none |
| eticket-user-list | GET, OPTIONS | `~/etickets/user/[^/]+$` | `https://personal-kgqqcaoh.outsystemscloud.com/ETicket_API/rest/v1` | customer key-auth (`x-customer-api-key`) | none |

### 3.3 Kong Regex Route Notes

- Routes using `~` are regex paths in Kong.
- `strip_path: false` is used for all configured routes, so upstream receives the same path prefix.
- Some orchestration/security checks are still enforced in upstream Flask services even when Kong route auth is open.

---

## 4. HTTP API Reference

## 4.1 event-service

Base URL (container): `http://event-service:5000`

Docs:
- Swagger UI: `/apidocs/`

### Endpoints

| Method | Path | Auth | Request | Success | Error Codes | Notes |
|---|---|---|---|---|---|---|
| GET | `/health` | none | none | 200 health object | - | Includes Supabase and RabbitMQ configured flags |
| GET | `/events` | none | none | 200 `{ events: [...] }` | 503, 500 | Returns non-deleted events |
| GET | `/event/{event_id}` | none | path `event_id` UUID | 200 event | 400, 404, 503 | Single event fetch |
| GET | `/event/{event_id}/categories` | none | path `event_id` UUID | 200 category list | 400, 404, 503, 500 | Returns seat categories for event |
| GET | `/event/{event_id}/flash-sale/status` | none | path `event_id` UUID | 200 flash sale status payload | 400, 404, 503, 500 | Combines `inventory_event_state` + `flash_sales` |
| GET | `/event/{event_id}/price-history` | none | path `event_id`, optional `limit` (1-200) | 200 history rows | 400, 422, 503, 500 | Enriches with category metadata |
| PUT | `/event/{event_id}/status` | Kong organiser auth | JSON `{ status }` | 200 updated event | 409, 422, 500, 503 | Enforces event state transitions |
| PUT | `/event/{event_id}/categories/prices` | Kong organiser auth | JSON `{ reason, updates[], ... }` | 200 updated categories | 404, 409, 422, 500, 503 | Updates category prices + writes price audit + integration event |

### Event status rules

Allowed status values:
- `SCHEDULED`
- `ACTIVE`
- `FLASH_SALE_ACTIVE`
- `CANCELLED`
- `COMPLETED`

Allowed transitions:
- `SCHEDULED -> ACTIVE | CANCELLED`
- `ACTIVE -> FLASH_SALE_ACTIVE | CANCELLED | COMPLETED`
- `FLASH_SALE_ACTIVE -> ACTIVE | CANCELLED | COMPLETED`
- Terminal states: `CANCELLED`, `COMPLETED`

Price change reasons:
- `FLASH_SALE`
- `ESCALATION`
- `REVERT`
- `MANUAL_ADJUSTMENT`

Published integration events:
- `event.status.updated`
- `event.prices.updated`
- `category.sold_out` (when category sells out after hold confirmation)

---

## 4.2 user-service

Base URL (container): `http://user-service:5000`

Docs:
- OpenAPI JSON: `/openapi.json`
- Swagger UI: `/docs`

### Auth model

`before_request` enforces internal auth for all non-health routes when enabled.

Config keys:
- `REQUIRE_INTERNAL_AUTH` (default true)
- `USER_SERVICE_AUTH_HEADER` (default `X-Internal-Token`)
- `INTERNAL_SERVICE_TOKEN`

### Endpoints

| Method | Path | Auth | Request | Success | Error Codes | Notes |
|---|---|---|---|---|---|---|
| GET | `/health` | none | none | 200 | - | Health + Supabase configured |
| GET | `/user/{user_id}` | internal token | path `user_id`; query `includeDeleted` | 200 user contract | 400, 401, 404, 503, 500 | Falls back from `user_id` lookup to `auth_user_id` |
| GET | `/users` | internal token | query `page`, `pageSize`, `search`, `includeDeleted` | 200 `{ users, pagination }` | 400, 401, 503, 500 | `search` max length 120 |
| POST | `/users` | internal token | JSON `{ name/fullName/full_name, email, phone?, metadata? }` | 201 created user | 400, 401, 409, 503, 500 | Duplicate users mapped to 409 |
| PUT | `/user/{user_id}` | internal token | partial JSON update payload | 200 updated user | 400, 401, 404, 503, 500 | Rejects empty update payload |

---

## 4.3 inventory-service

Base URL (container): `http://inventory-service:5000`

Docs:
- Swagger JSON: `/inventory/openapi.json`
- Swagger UI: `/inventory/docs/`

### Hold and seat state model

Hold duration default:
- `HOLD_DURATION_SECONDS` default 600

Valid release reasons:
- `PAYMENT_TIMEOUT`
- `CANCELLATION`
- `MANUAL_RELEASE`
- `SYSTEM_CLEANUP`

Seat statuses:
- `AVAILABLE`
- `PENDING_WAITLIST`
- `HELD`
- `SOLD`

Allowed seat transitions:
- `AVAILABLE -> HELD | PENDING_WAITLIST`
- `PENDING_WAITLIST -> HELD | AVAILABLE`
- `HELD -> AVAILABLE | PENDING_WAITLIST | SOLD`
- `SOLD -> AVAILABLE | PENDING_WAITLIST`

### Endpoints

| Method | Path | Auth | Request | Success | Error Codes | Notes |
|---|---|---|---|---|---|---|
| GET | `/health` | none | none | 200 | - | Health + dependency flags |
| PUT | `/inventory/{event_id}/flash-sale` | none | JSON `{ active, flashSaleID? }` | 200 state object | 400, 500, 503 | Upserts `inventory_event_state` |
| GET | `/inventory/{event_id}/{seat_category}` | none | path params | 200 availability object | 400, 404, 500, 503 | Returns `status` as AVAILABLE/SOLD_OUT |
| POST | `/inventory/hold` | none | JSON `{ eventID, userID, seatCategory, qty?, fromWaitlist?, idempotencyKey? }` | 201 created or 200 idempotent | 400, 404, 409, 500, 503 | Uses RPC `inventory_create_hold`; enforces qty=1 |
| GET | `/inventory/hold/{hold_id}` | none | path hold UUID | 200 hold object | 400, 404, 500, 503 | Hold lookup |
| PUT | `/inventory/hold/{hold_id}/confirm` | none | JSON `{ correlationID? }` | 200 hold object | 400, 404, 409, 500, 503 | Uses RPC `inventory_confirm_hold`; can trigger sold-out event |
| PUT | `/inventory/hold/{hold_id}/release` | none | JSON `{ reason }` | 200 hold object | 400, 404, 409, 500, 503 | Publishes `seat.released` on successful release |
| PUT | `/inventory/seat/{seat_id}/status` | none | JSON `{ status }` | 200 seat state | 400, 404, 409, 500, 503 | Guards transition validity |
| POST | `/inventory/maintenance/expire-holds` | none | JSON optional | 200 batch payload | 500, 503 | Expires stale holds via RPC and publishes `seat.released` with reason `PAYMENT_TIMEOUT` |

Published events from inventory paths:
- `seat.released` (release/expire flows)
- `category.sold_out` (when post-confirmation category available count reaches zero)

---

## 4.4 payment-service

Base URL (container): `http://payment-service:5000`

Docs:
- OpenAPI JSON: `/openapi.json` (configurable via env)
- Swagger UI: `/docs` (configurable via env)

### Auth model

Internal auth is enforced on selected endpoints when `PAYMENT_INTERNAL_TOKEN` is set.
Header used: `X-Internal-Token`.

### Primary endpoints

| Method | Path | Auth | Request | Success | Error Codes | Notes |
|---|---|---|---|---|---|---|
| GET | `/health` | none | none | 200 | - | Health includes Stripe configured flag |
| POST | `/payment/initiate` | internal token | JSON `{ holdID, userID, amount, idempotencyKey? }` | 201 or 200 | 400, 401, 404, 409, 502, 503, 500 | Creates Stripe PaymentIntent; default idempotency key prefix `payment-initiate:{holdID}` |
| GET | `/payment/hold/{hold_id}` | no internal auth by default | query `reconcile=true|false` | 200 payment state | 404, 503, 500 | Optional reconciliation against Stripe PaymentIntent |
| POST | `/payment/webhook` | Stripe signature auth | raw Stripe event + `Stripe-Signature` | 200 accepted | 400, 503, 500 | Handles `payment_intent.succeeded` and `payment_intent.payment_failed`; webhook idempotency tracked |

### Legacy/alias and cancellation-support endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/payments/verify/{booking_id}` | none | Booking verification payload for cancellation orchestration |
| GET | `/payments/verify-policy/{booking_id}` | none | 48-hour policy eligibility check |
| GET | `/payments/user/{user_id}/bookings` | none | User booking payment history |
| PUT | `/payments/status/{booking_id}` | internal token | Update payment/refund status |
| PUT | `/payments/update/{booking_id}` | internal token | Alias of `/payments/status/{booking_id}` |
| PUT | `/payments/processing/{booking_id}` | internal token | Mark processing refund state |
| PUT | `/payments/success/{booking_id}` | internal token | Mark refund success state |
| PUT | `/payments/status/fail` | internal token | Mark refund failed state |
| POST | `/payments/create` | internal token | Alias payment creation endpoint |
| POST | `/payments/refund/{booking_id}` | internal token | Execute Stripe refund flow |
| POST | `/payments/refund` | internal token | Alias refund endpoint using booking or transaction identifiers |

### Payment/refund behavior highlights

- Refund success ratio constant: 90 percent (`REFUND_SUCCESS_RATIO = 0.90`)
- Max refund attempts: 3
- Simulated refund failure is blocked in production envs
- Webhook events tracked in persistence for idempotency and processing status

Published notification event types from payment/cancellation flow usage:
- `REFUND_SUCCESSFUL`
- `REFUND_ERROR`

---

## 4.5 waitlist-service

Base URL (container): `http://waitlist-service:5000`

Docs:
- OpenAPI JSON: `/openapi.json`
- Swagger UI: `/docs`

### Status model

Statuses:
- `WAITING`
- `HOLD_OFFERED`
- `CONFIRMED`
- `EXPIRED`
- `CANCELLED`

Transition constraints:
- `WAITING -> HOLD_OFFERED`
- `HOLD_OFFERED -> CONFIRMED`
- `HOLD_OFFERED -> EXPIRED`

Cancellation endpoint (`DELETE /waitlist/{waitlist_id}`) requires current status `WAITING`.

### Auth model

- Mutating methods require internal auth when `REQUIRE_INTERNAL_AUTH=true`.
- Sensitive reads also require auth:
  - `/waitlist`
  - `/waitlist/next`
  - `/waitlist/by-hold/{hold_id}`
  - `/waitlist/status/{hold_id}`
- `/waitlist/{waitlist_id}` requires auth only when `includeEmail=true`.

### Endpoints

| Method | Path | Auth | Request | Success | Error Codes | Notes |
|---|---|---|---|---|---|---|
| GET | `/health` | none | none | 200 | - | Health + Supabase configured |
| GET | `/waitlist` | internal token | filters: `eventID,userID,status,seatCategory,includeEmail,limit` | 200 list payload | 400, 401, 404, 503, 500 | Requires `eventID` when `seatCategory` provided |
| POST | `/waitlist/join` | internal token | JSON `{ userID, eventID, seatCategory, qty?, source?, metadata?, priorityScore? }` | 201 join payload | 400, 401, 404, 409, 503, 500 | qty must be 1 |
| GET | `/waitlist/next` | internal token | query `eventID, seatCategory` | 200 entry | 400, 401, 404, 503, 500 | Returns earliest WAITING entry |
| GET | `/waitlist/by-hold/{hold_id}` | internal token | hold UUID | 200 entry | 400, 401, 404, 503, 500 | Latest by hold |
| GET | `/waitlist/status/{hold_id}` | internal token | hold UUID, query `limit` | 200 summary payload | 400, 401, 404, 503, 500 | Provides queue context for hold |
| DELETE | `/waitlist/users/{user_id}` | internal token | query `holdID` | 200 dequeued summary | 400, 401, 404, 503, 500 | Cancels active WAITING entry in hold context |
| DELETE | `/waitlist/{waitlist_id}` | internal token | optional JSON `{ userID }` | 200 cancelled summary | 400, 401, 404, 409, 503, 500 | Enforces ownership and WAITING state |
| GET | `/waitlist/{waitlist_id}` | conditional | path + query `includeEmail` | 200 entry | 400, 404, 500 | includeEmail true requires internal auth |
| PUT | `/waitlist/{waitlist_id}/offer` | internal token | JSON `{ holdID }` | 200 transition summary | 400, 401, 404, 409, 503, 500 | Requires holdID |
| PUT | `/waitlist/{waitlist_id}/confirm` | internal token | JSON `{ holdID? }` | 200 transition summary | 400, 401, 404, 409, 503, 500 | HOLD_OFFERED to CONFIRMED |
| PUT | `/waitlist/{waitlist_id}/expire` | internal token | JSON `{ holdID? }` | 200 transition summary | 400, 401, 404, 409, 503, 500 | HOLD_OFFERED to EXPIRED |

---

## 4.6 pricing-service

Base URL (container): `http://pricing-service:5000`

Docs:
- No integrated OpenAPI route currently exposed

### Endpoints

| Method | Path | Auth | Request | Success | Error Codes | Notes |
|---|---|---|---|---|---|---|
| GET | `/health` | none | none | 200 | - | Health + Supabase configured |
| POST | `/pricing/flash-sale/configure` | none (internal by network) | JSON `{ eventID, discountPercentage, durationMinutes, escalationPercentage?, launchedByUserID? }` | 200 configured sale payload | 400, 404, 409, 500, 503 | Creates active `flash_sales` record |
| GET | `/pricing/{event_id}/flash-sale/active` | none | path event UUID | 200 active sale | 400, 404, 500, 503 | Active sale lookup |
| GET | `/pricing/flash-sales/expired` | none | query: `eventID?,limit?,includeEnded?,endedWindowMinutes?` | 200 list payload | 400, 500, 503 | Used by flash-sale reconciliation |
| POST | `/pricing/escalate` | none | JSON `{ eventID, flashSaleID?, soldOutCategory, remainingCategories[], escalationPercentage? }` | 200 escalation payload | 400, 404, 500, 503 | Computes price escalations for remaining categories |
| PUT | `/pricing/{flash_sale_id}/end` | none | path sale UUID | 200 ended payload | 400, 404, 409, 500, 503 | Finalizes active sale |
| GET | `/pricing/{event_id}` | none | path event UUID | 200 pricing snapshot | 400, 404, 500, 503 | Includes seat availability-derived status per category |
| GET | `/pricing/{event_id}/history` | none | path event UUID, query `flashSaleID?`, `limit?` | 200 history payload | 400, 500, 503 | Price change audit stream |

---

## 4.7 reservation-orchestrator

Base URL (container): `http://reservation-orchestrator:5000`

Docs:
- OpenAPI JSON: `/openapi.json`
- Swagger UI: `/docs`

### Key request constraints

- Requires user-binding header by default (`REQUIRE_AUTHENTICATED_USER_HEADER=true`)
- Header chain checked:
  - primary: `AUTHENTICATED_USER_HEADER` (default `X-User-ID`)
  - fallback list: `FALLBACK_AUTHENTICATED_USER_HEADERS`
- Payload `userID` must match authenticated header when present

### Endpoints

| Method | Path | Auth | Request | Success | Error Codes | Notes |
|---|---|---|---|---|---|---|
| GET | `/health` | none | none | 200 | - | Includes RabbitMQ and OutSystems configured flags |
| POST | `/reserve` | authenticated user header | JSON `{ userID, eventID, seatCategory, qty?, correlationID? }` | 200 `{ status: PAYMENT_PENDING ... }` or `{ status: WAITLISTED ... }` | 400, 404, 409, 502, 503, 500 | If inventory available, creates hold + initiates payment; otherwise joins waitlist |
| POST | `/reserve/confirm` | authenticated user header | JSON `{ holdID, userID, correlationID? }` | 200 `{ status: CONFIRMED ... }` or `{ status: PAYMENT_PENDING ... }` | 400, 404, 409, 502, 503, 500 | Handles resumed confirmation and optional e-ticket generation path |
| GET | `/waitlist/confirm/{hold_id}` | authenticated user header (default required) | hold UUID | 200 waitlist confirmation state | 400, 404, 409, 502, 503, 500 | Returns `uiStatus` values: WAITLIST_OFFERED, WAITLIST_PENDING, PAID_PROCESSING, CONFIRMED, EXPIRED, PROCESSING |
| DELETE | `/waitlist/leave/{waitlist_id}` | authenticated user header required | waitlist UUID | 200 cancelled payload | 400, 404, 409, 502, 503, 500 | Cancels entry via waitlist-service |
| GET | `/reserve/waitlist/my` | authenticated user header required | none | 200 list payload | 400, 502, 503, 500 | Active WAITING/HOLD_OFFERED entries for current user |

### OutSystems calls from this service

When OutSystems config is present (`OUTSYSTEMS_BASE_URL` and `OUTSYSTEMS_API_KEY`):
- `GET /eticket/hold/{holdID}`
- `POST /eticket/generate`

---

## 4.8 booking-status-service

Base URL (container): `http://booking-status-service:5000`

Docs:
- OpenAPI JSON: `/openapi.json`
- Swagger UI: `/docs`

### Endpoint

| Method | Path | Auth | Request | Success | Error Codes | Notes |
|---|---|---|---|---|---|---|
| GET | `/health` | none | none | 200 | - | Reports dependency URL presence |
| GET | `/booking-status/{hold_id}` | none | path hold UUID, query `reconcilePayment` boolean | 200 booking status payload | 400, 404, 503, 500 | Aggregates inventory + payment + OutSystems e-ticket for polling UI |

### UI status resolution

Possible `uiStatus`:
- `PROCESSING`
- `CONFIRMED`
- `FAILED_PAYMENT`
- `EXPIRED`

Important behavior:
- Expired holds are terminal even if payment is still unresolved.
- `reconcilePayment=true` triggers payment-service reconciliation with Stripe.
- If payment succeeded + hold confirmed but ticket missing:
  - returns PROCESSING unless `BOOKING_STATUS_ALLOW_CONFIRMED_WITHOUT_TICKET=true`

---

## 4.9 cancellation-orchestrator

Base URL (container): `http://cancellation-orchestrator:5000`

Docs:
- OpenAPI JSON: `/openapi.json`
- Swagger UI: `/docs`

### Endpoints

| Method | Path | Auth | Request | Success | Error Codes | Notes |
|---|---|---|---|---|---|---|
| GET | `/health` | none | none | 200 | - | Dependency configured flags |
| POST | `/orchestrator/cancellation` | business validation, no hard internal gate | JSON `{ bookingID, userID, reason?, correlationID?, simulateRefundFailure? }` | 200, 202 | 400, 401, 409, 502, 503, 500 | Main cancellation workflow |
| POST | `/bookings/cancel/{booking_id}` | same as above | path + body | 200, 202 | 400, 401, 409, 502, 503, 500 | Kong-facing alias endpoint |
| GET | `/bookings/cancel/status/{booking_id}` | none | query `userID`, optional `newHoldID` | 200 | 400, 409, 500 | Returns cancellation/reallocation status snapshot |
| POST | `/orchestrator/cancellation/reallocation/confirm` | internal token required | JSON with `bookingID,newHoldID,waitlistID,...` | 200 | 400, 401, 409, 502, 503, 500 | Finalizes waitlist reallocation after payment succeeded |

### Cancellation workflow highlights

Main sequence:
1. Verify booking/payment policy via payment-service.
2. Validate ownership and policy window.
3. Set payment to `PROCESSING_REFUND`.
4. Publish `CANCELLATION_CONFIRMED`.
5. Execute refund.
6. On success: cancel old e-ticket, release hold, publish `REFUND_SUCCESSFUL`.
7. If waitlist exists: create new waitlist hold + payment + `SEAT_AVAILABLE` notification.
8. If no waitlist: set seat `AVAILABLE` and publish `TICKET_AVAILABLE_PUBLIC`.

Failure branch:
- Refund failure sets `REFUND_FAILED` and e-ticket `CANCELLATION_IN_PROGRESS`, then publishes `REFUND_ERROR`.

---

## 4.10 flash-sale-orchestrator

Base URL (container): `http://flash-sale-orchestrator:5000`

Docs:
- No integrated OpenAPI route currently exposed

### Endpoints

| Method | Path | Auth | Request | Success | Error Codes | Notes |
|---|---|---|---|---|---|---|
| GET | `/health` | none | none | 200 | - | Includes dependency URLs and RabbitMQ flag |
| POST | `/flash-sale/launch` | Kong organiser auth | JSON `{ eventID, discountPercentage, durationMinutes, escalationPercentage?, correlationID? }` | 200 launch payload | 400, 5xx mapped downstream | Coordinates pricing configure + event status + event prices + inventory flash-state + fanout broadcast |
| POST | `/flash-sale/end` | Kong organiser auth | JSON `{ eventID, flashSaleID, correlationID? }` | 200 end payload | 400, 5xx mapped downstream | Reverts prices, closes sale, resets event status/inventory state, broadcasts end |
| POST | `/internal/flash-sale/reconcile-expired` | internal token required | JSON `{ eventID?, limit?, correlationID? }` | 200 reconciliation summary | 400, 401, 502 | Batch closes expired active sales |
| GET | `/flash-sale/{event_id}/status` | none | path event UUID | 200 status payload | 400, 5xx mapped downstream | Merges event flash status + pricing active sale |

Published fanout events to `ticketblitz.price`:
- `FLASH_SALE_LAUNCHED`
- `FLASH_SALE_ENDED`

---

## 5. Non-HTTP Backend Processes

## 5.1 booking-fulfillment-orchestrator

File: `backend/composite/booking-fulfillment-orchestrator/booking_fulfillment_worker.py`

Consumes:
- Exchange `ticketblitz` (topic)
- Routing key `booking.confirmed`

Queue model:
- Main queue default: `booking-fulfillment-orchestrator.booking.confirmed`
- Retry queue: `<main>.retry` with TTL
- Retry header: `x-bfo-retry`
- Max retries default: 3

Flow per message:
1. Validate payload fields (`holdID,userID,eventID,email`).
2. Confirm hold in inventory (`PUT /inventory/hold/{holdID}/confirm`).
3. Generate OutSystems ticket (`POST /eticket/generate` via Kong).
4. Confirm waitlist entry when present.
5. Resolve event name.
6. Publish `notification.send` type `BOOKING_CONFIRMED`.

Terminal incidents:
- On terminal processing failure, publishes incident notification type `BOOKING_FULFILLMENT_INCIDENT` to configured incident email.

## 5.2 waitlist-promotion-orchestrator

File: `backend/composite/waitlist-promotion-orchestrator/waitlist_promotion.py`

Consumes:
- Exchange `ticketblitz` (topic)
- Routing key `seat.released`

Flow:
1. Parse release event (`eventID, seatID, seatCategory, reason, expiredHoldID?`).
2. On payment timeout + expired hold, mark waitlist entry expired and publish `HOLD_EXPIRED`.
3. Fetch next waitlist candidate.
4. If none, set seat status back to `AVAILABLE`.
5. If candidate exists, create waitlist hold with deterministic idempotency key.
6. Mark waitlist entry `HOLD_OFFERED`.
7. Publish `SEAT_AVAILABLE` with payment URL.

Retry strategy:
- Retry queue with TTL and dead-letter back to main route.
- Retry header: `x-waitlist-promotion-retry`.

## 5.3 pricing-orchestrator

File: `backend/composite/pricing-orchestrator/pricing_orchestrator.py`

Consumes:
- Exchange `ticketblitz` (topic)
- Routing key `category.sold_out`

Produces:
- Fanout exchange `ticketblitz.price`
- Event type `PRICE_ESCALATED`

Flow:
1. Validate sold-out event payload.
2. Ensure active flash sale matches payload sale ID.
3. Ensure event not already escalated (history dedupe by context).
4. Build remaining categories still available.
5. Call pricing-service `/pricing/escalate`.
6. Persist escalated prices to event-service `/event/{id}/categories/prices` with reason `ESCALATION`.
7. Publish fanout escalation event.

## 5.4 notification-service

File: `backend/atomic/notification-service/notification.py`

Consumes both:
- Topic queue for `notification.send`
- Fanout queue for `ticketblitz.price`

Supported notification types:
- `BOOKING_CONFIRMED`
- `WAITLIST_JOINED`
- `SEAT_AVAILABLE`
- `HOLD_EXPIRED`
- `BOOKING_FULFILLMENT_INCIDENT`
- `CANCELLATION_CONFIRMED`
- `CANCELLATION_DENIED`
- `REFUND_SUCCESSFUL`
- `REFUND_ERROR`
- `TICKET_AVAILABLE_PUBLIC`
- `TICKET_CONFIRMATION`
- `FLASH_SALE_LAUNCHED`
- `PRICE_ESCALATED`
- `FLASH_SALE_ENDED`

Features:
- Required-field validation per type
- Topic single-recipient and fanout multi-recipient handling
- SendGrid dynamic template dispatch
- Non-production fallback option for specific auth failures
- Queue-level retry with TTL + retry header `x-notification-retry`

## 5.5 expiry-scheduler-service

File: `backend/atomic/expiry-scheduler-service/expiry_scheduler.py`

Behavior:
- Periodically calls inventory maintenance endpoint:
  - `POST /inventory/maintenance/expire-holds`
- Optional flash-sale reconciliation call:
  - `POST /internal/flash-sale/reconcile-expired` (flash-sale-orchestrator)

Control knobs:
- Interval: `EXPIRY_INTERVAL_SECONDS` (default 60)
- Error retry delay/jitter
- HTTP retry strategy for POST calls
- Internal auth header/token support

---

## 6. RabbitMQ Topology and Event Contracts

## 6.1 Exchanges

| Exchange | Type | Purpose |
|---|---|---|
| `ticketblitz` | topic | Core backend domain events and notifications |
| `ticketblitz.price` | fanout | Flash-sale and pricing broadcast events |

## 6.2 Key routing keys and producers/consumers

| Routing Key | Producer(s) | Consumer(s) | Typical Payload Keys |
|---|---|---|---|
| `booking.confirmed` | inventory/booking flow | booking-fulfillment-orchestrator | `holdID,userID,eventID,email,correlationID,...` |
| `seat.released` | inventory-service | waitlist-promotion-orchestrator | `eventID,seatCategory,seatID,reason,expiredHoldID?` |
| `category.sold_out` | event-service | pricing-orchestrator | `eventID,category,flashSaleID,soldAt,...` |
| `notification.send` | orchestrators/services | notification-service | `type,...type-specific fields...` |
| fanout empty routing key | flash/pricing orchestrators | notification-service + price subscribers | `FLASH_SALE_LAUNCHED`, `PRICE_ESCALATED`, `FLASH_SALE_ENDED` payloads |

## 6.3 Shared MQ implementation

`backend/shared/mq.py` provides:
- `rabbitmq_configured()`
- `get_connection()` with heartbeat and retry env knobs
- `publish_json()` with configurable exchange/type/durable

---

## 7. OutSystems E-Ticket Integration

Reference guide:
- `docs/tests/OutSystems_ETicket_Service_Implementation_Guide.md`

Canonical OutSystems REST endpoints expected by project design:
1. `POST /eticket/generate`
2. `GET /eticket/hold/{holdID}`
3. `GET /eticket/validate`
4. `PUT /etickets/status/{ticketID}`
5. `POST /etickets/update`
6. `GET /etickets/user/{userID}`

### 7.1 Current backend call sites

Implemented direct call usage in Python backend:
- Reservation orchestrator:
  - `GET /eticket/hold/{holdID}`
  - optional `POST /eticket/generate`
- Booking status service:
  - `GET /eticket/hold/{holdID}`
- Booking fulfillment worker:
  - `POST /eticket/generate` via Kong route `/eticket/generate`
- Cancellation orchestrator:
  - Uses transfer/update style behavior through OutSystems helper calls in cancellation flow for ticket ownership and transfer/reissue state updates
 
# E-Ticket Service Endpoints

| Method | Path | Auth | Request | Success | Error Codes | Notes |
|---|---|---|---|---|---|---|
| POST | /eticket/generate | Custom internal auth (API key/header) | JSON { holdID, transactionID?, userID, eventID, seatID, seatNumber, correlationID?, metadata? } | 201 created, 200 idempotent replay | 400, 500 | Only endpoint that returns 201 on new create. |
| GET | /eticket/hold/{holdID} | Custom internal auth (API key/header) | path holdID | 200 ticket by hold | 400, 404, 500 | Used by booking-status polling. |
| GET | /eticket/validate | Custom internal auth (API key/header) | query ticketID, userID | 200 validation result | 400, 403, 404, 409, 500 | 403 owner mismatch, 409 non-VALID ticket state. |
| PUT | /etickets/status/{ticketID} | Custom internal auth (API key/header) | path ticketID, JSON { status, correlationID? } | 200 status updated | 400, 404, 409, 500 | Enforces allowed status transitions only. |
| POST | /etickets/update | Custom internal auth (API key/header) | JSON { oldTicketID, operation, newOwnerUserID?, newHoldID?, newSeatID?, newSeatNumber?, correlationID?, newTransactionID? } | 200 cancel-only / transfer / replay | 400, 404, 409, 500 | Supports CANCEL_ONLY and TRANSFER_AND_REISSUE. |
| GET | /etickets/user/{userID} | Custom internal auth (API key/header) | path userID | 200 ticket list + count | 400, 500 | Returns empty list with 200 when user has no tickets. |

## Short Error Code Legend

| Code | Meaning |
|---|---|
| 400 | Bad request (missing/invalid input) |
| 401 | Unauthorized (invalid/missing auth token/key) |
| 403 | Forbidden (owner mismatch / not allowed) |
| 404 | Not found (ticket/hold/resource missing) |
| 409 | Conflict (invalid state/transition/business rule conflict) |
| 500 | Internal server error (unexpected failure) |


### 7.2 Integration configuration

Common env keys:
- `OUTSYSTEMS_BASE_URL`
- `OUTSYSTEMS_API_KEY`
- `OUTSYSTEMS_AUTH_HEADER` or `OUTSYSTEMS_API_KEY_HEADER`

Gateway config currently proxies OutSystems API route group under Kong service `eticket-service`.

---

## 8. Data Ownership and Persistence Boundaries

## 8.1 Atomic ownership

| Service | Primary Tables/Views Used |
|---|---|
| user-service | `users` (with `auth_user_id` fallback) |
| event-service | `events`, `seat_categories`, `price_changes`, `integration_events` |
| inventory-service | `seats`, `seat_holds`, `inventory_event_state`, seat-category lookups |
| waitlist-service | `waitlist_entries`, `seat_categories`, `users`, `v_waitlist_ranked`, `seat_holds` context lookup |
| payment-service | `transactions`, `seat_holds`, `users`, `waitlist_entries`, `payment_webhook_events` |
| pricing-service | `flash_sales`, `price_changes`, `seat_categories`, `events`, seat counts |

## 8.2 Composite/services behavior

- reservation-orchestrator and booking-status-service are orchestration/read-composition layers; they do not own standalone storage.
- cancellation-orchestrator coordinates payment, inventory, waitlist, user, event, and OutSystems without owning core domain tables.
- workers orchestrate state transitions through service APIs rather than direct DB writes (except where service-local behavior requires it).

---

## 9. Docker and Containerization Analysis

## 9.1 Dockerfile implementation pattern

Across backend services:
- Base image: `python:3.11-slim`
- `PYTHONDONTWRITEBYTECODE=1` and related env setup
- Shared requirements copied first, then service requirements
- `pip install --no-cache-dir`
- Source copied under `/app`
- Runtime user: non-root `appuser`
- HTTP services expose port `5000`
- CMD executes service entry file directly

Worker Dockerfiles follow same base pattern, without exposed port.

## 9.2 Compose behavior

`docker-compose.yml` includes:
- One service per backend process
- `depends_on` with health conditions for startup ordering
- Healthchecks for HTTP services via `/health`
- RabbitMQ with durable volume `rabbitmq-data`
- Internal bridge network `ticketblitz-net`
- Kong in DB-less declarative mode

Port map highlights:
- event 5001, user 5002 (localhost bind), inventory 5003, payment 5004, waitlist 5005, pricing 5006
- reservation 6001, booking-status 6002, flash-sale 6003, cancellation 6004
- kong 8000/8001

## 9.3 Docker security posture (current)

Implemented:
- Non-root runtime users in service images
- Env-file based secret injection at runtime
- Logs to stdout/stderr through container runtime

Important considerations:
- Service secrets remain env-based, not Docker secrets
- Some HTTP services are publicly exposed on localhost host ports by design

---

## 10. OpenAPI and Documentation Endpoints

| Service | OpenAPI/Swagger JSON | Docs UI |
|---|---|---|
| user-service | `/openapi.json` | `/docs` |
| waitlist-service | `/openapi.json` | `/docs` |
| reservation-orchestrator | `/openapi.json` | `/docs` |
| booking-status-service | `/openapi.json` | `/docs` |
| cancellation-orchestrator | `/openapi.json` | `/docs` |
| payment-service | `/openapi.json` | `/docs` |
| inventory-service | `/inventory/openapi.json` | `/inventory/docs/` |
| event-service | flasgger-generated | `/apidocs/` |
| pricing-service | not exposed | not exposed |
| flash-sale-orchestrator | not exposed | not exposed |

Centralized spec source used by several services:
- `backend/shared/swagger/ticketblitz-service-specs.json`

---

## 11. Known Contract and Operational Notes

- Quantity remains constrained to 1 seat for reservation/waitlist/hold creation paths.
- Payment reconciliation can recover delayed Stripe webhook state via booking-status query parameter.
- Late reconciliation can still produce terminal expired outcomes if hold already expired before fulfillment.
- User identity handling supports fallback from domain `user_id` to `auth_user_id`.
- Notification delivery depends on valid SendGrid configuration in running container env; stale container env can cause false auth-failure diagnosis.

---

## 12. Context7 Alignment Notes (Flask + Docker)

This backend implementation aligns with key framework guidance:

Flask-aligned patterns:
- Widespread use of app factory or factory-like construction (`create_app` in many services)
- Blueprint modularization for several services (`user`, `waitlist`, `reservation`, `booking-status`, `cancellation`)
- Structured JSON error handling and service-level error handlers
- Request and application context usage for config and request headers

Docker-aligned patterns:
- Slim base images
- Layered dependency installation with `.dockerignore`
- Non-root runtime user
- Compose health checks and explicit dependency ordering
- Environment variable driven runtime configuration

---

## 13. Appendix: Quick Endpoint Index

The backend currently implements these route families:
- Event lifecycle and pricing admin endpoints
- User CRUD/list endpoints
- Inventory hold lifecycle and maintenance endpoints
- Payment initiation/webhook/refund and cancellation-support endpoints
- Waitlist lifecycle and state transitions
- Reservation orchestration and waitlist self-service endpoints
- Booking polling status endpoint
- Cancellation orchestration and reallocation endpoints
- Pricing and flash-sale admin/computation endpoints
- Flash-sale orchestration and reconciliation endpoints

For exact schemas on OpenAPI-enabled services, use the service-local `/openapi.json` endpoints listed above.
