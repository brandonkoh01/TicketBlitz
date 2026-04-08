# Reservation Orchestrator Manual Swagger Test Cases

## 0. Test Design Reasoning

### 0.1 What is being tested

- Reservation Orchestrator API behavior through Swagger:
  - `GET /health`
  - `POST /reserve`
  - `POST /reserve/confirm`
  - `GET /waitlist/confirm/{hold_id}`
  - docs/spec endpoints (`/docs`, `/openapi.json`)

### 0.2 Expected behavior from project context

Derived from Setup and Scenarios documents:

- Scenario 1A: seats available -> create hold + initiate payment -> return `PAYMENT_PENDING`.
- Scenario 1B: sold out -> join waitlist -> return `WAITLISTED`.
- Scenario 1C/1D: waitlist confirmation page should map hold/waitlist/payment/ticket state to UI status.
- User-facing routes are authenticated via Kong and user identity must be bound to request user.

### 0.3 Dependencies and what can go wrong

- Dependencies: user-service, event-service, inventory-service, payment-service, waitlist-service, RabbitMQ, optional OutSystems e-ticket service.
- Risk areas covered:
  - identity mismatch and missing auth header
  - invalid payload shape and field validation
  - not-found and conflict state transitions
  - sold-out vs available branch correctness
  - waitlist-confirm state mapping (`EXPIRED`, `WAITLIST_OFFERED`, `WAITLIST_PENDING`, `PAID_PROCESSING`, `PROCESSING`, `CONFIRMED`)

### 0.4 Test type

- Primary: manual integration tests via Swagger UI.
- Secondary: DB verification and setup SQL in Supabase for deterministic edge-state cases.

## 1. Scope and Entry Points

- Direct service base URL: `http://localhost:6001`
- Swagger UI: `http://localhost:6001/docs`
- OpenAPI JSON: `http://localhost:6001/openapi.json`

Notes:

- This suite is designed for direct Swagger execution on the orchestrator container.
- Kong also protects reservation routes with key-auth; gateway parity checks are listed separately in Section 10.

## 2. Context Sources Used

- Setup guide: `docs/Setup.md`
- Scenario flows: `docs/Scenarios.md`
- Existing manual test pattern references:
  - `docs/payment-service-swagger-manual-test-cases.md`
  - `docs/InventoryServiceSwaggerManualTestSuite.md`
- Supabase project context: `cpxcpvcfbohvpiubbujg`
- Context7 references:
  - Swagger UI (`/swagger-api/swagger-ui`) for try-it-out behavior and response-code verification
  - OpenAPI specification (`/websites/spec_openapis_oas_v3_0_3`) for response/status coverage and reusable component expectations

## 3. Global Components (Reusable)

Use these in every case where applicable.

### 3.1 Headers

- `GC-HDR-JSON`
  - `Content-Type: application/json`
- `GC-HDR-USER-1`
  - `X-User-ID: 00000000-0000-0000-0000-000000000001`
- `GC-HDR-USER-2`
  - `X-User-ID: 00000000-0000-0000-0000-000000000002`
- `GC-HDR-USER-5`
  - `X-User-ID: 00000000-0000-0000-0000-000000000005`
- `GC-HDR-CORR`
  - `X-Correlation-ID: 11111111-1111-1111-1111-111111111111`

### 3.2 Common assertions

- `GC-RES-ERR`
  - Response has `error` string.
  - HTTP status matches expected.
- `GC-RES-PAYMENT-PENDING`
  - Includes `status=PAYMENT_PENDING`, `holdID`, `paymentIntentID`, `clientSecret`, `holdExpiry`, `amount`, `currency`, `returnURL`, `correlationID`.
- `GC-RES-WAITLISTED`
  - Includes `status=WAITLISTED`, `waitlistID`, `position`, `eventID`, `seatCategory`, `correlationID`.
- `GC-RES-CONFIRMED`
  - Includes `status=CONFIRMED`, `holdID`, `paymentStatus`, `ticket` (nullable object), `correlationID`.

### 3.3 Deterministic IDs from Supabase snapshot

- `DS-EVENT-MAIN`: `10000000-0000-0000-0000-000000000301` (EVT-301)
- `DS-EVENT-ALT`: `10000000-0000-0000-0000-000000000401`
- `DS-USER-1`: `00000000-0000-0000-0000-000000000001`
- `DS-USER-2`: `00000000-0000-0000-0000-000000000002`
- `DS-USER-5`: `00000000-0000-0000-0000-000000000005`
- `DS-HOLD-EXPIRED`: `40000000-0000-0000-0000-000000000003`
- `DS-HOLD-CONFIRMED-1`: `40000000-0000-0000-0000-000000000004`
- `DS-HOLD-CONFIRMED-2`: `40000000-0000-0000-0000-000000000005`
- `DS-HOLD-RELEASED`: `4b100000-0000-0000-0000-000000000002`
- `DS-WAITLIST-CONFIRMED`: `60000000-0000-0000-0000-000000000002`
- `DS-WAITLIST-EXPIRED`: `60000000-0000-0000-0000-000000000003`

### 3.4 Known inventory snapshot for EVT-301 (at authoring)

- CAT1: available `0`
- CAT2: available `0`
- PEN: available `2`

### 3.5 Captured runtime variables

Capture these while executing:

- `CAP-HOLD-PEN-01`: hold created in reserve happy path
- `CAP-RESERVE-CORR-01`: correlation ID from reserve response

## 4. Preflight and Determinism Setup

### 4.1 Service health preflight

1. `GET /health` should return HTTP 200.
2. Confirm all downstream atomics are healthy in Docker.

### 4.2 Recommended deterministic setting for this suite

To avoid external OutSystems dependency failures in Swagger runs, set:

- `OUTSYSTEMS_BASE_URL=`
- `OUTSYSTEMS_API_KEY=`

Then restart reservation-orchestrator. This keeps `existingETicket`/`ticket` paths deterministic (nullable).

### 4.3 Optional SQL preflight queries (Supabase)

```sql
select event_id, event_code, name, status
from public.events
where event_id in (
  '10000000-0000-0000-0000-000000000301',
  '10000000-0000-0000-0000-000000000401'
)
order by event_id;

select hold_id, user_id, status
from public.seat_holds
where hold_id in (
  '40000000-0000-0000-0000-000000000003',
  '40000000-0000-0000-0000-000000000004',
  '40000000-0000-0000-0000-000000000005',
  '4b100000-0000-0000-0000-000000000002'
)
order by hold_id;
```

## 5. Manual Test Cases (Swagger)

Naming style: `should_<expected>_when_<condition>`

---

### Group A: Health and Documentation

| ID | Test name | Swagger input | Expected output |
|---|---|---|---|
| A01 | should_return_health_payload_when_health_is_called | `GET /health` no headers/body | HTTP `200`; body includes `status="ok"`, `service="reservation-orchestrator"`, `rabbitmqConfigured` boolean, `outsystemsConfigured` boolean |
| A02 | should_return_openapi_spec_when_openapi_json_is_called | `GET /openapi.json` | HTTP `200`; body includes `openapi` and `paths` containing `/reserve`, `/reserve/confirm`, `/waitlist/confirm/{hold_id}`, `/health` |
| A03 | should_render_swagger_ui_when_docs_is_opened | Browser `GET /docs` | HTTP `200`; Swagger UI rendered and operations visible |

---

### Group B: Reserve Endpoint Validation and Auth Binding

| ID | Test name | Swagger input | Expected output |
|---|---|---|---|
| B01 | should_return_400_when_request_body_is_not_json_object | `POST /reserve`; send invalid/non-object body | HTTP `400`; `GC-RES-ERR`; `error="Request body must be a JSON object"` |
| B02 | should_return_400_when_authenticated_user_header_missing | `POST /reserve`; headers `GC-HDR-JSON`; body `{"userID":"00000000-0000-0000-0000-000000000001","eventID":"10000000-0000-0000-0000-000000000301","seatCategory":"PEN"}` | HTTP `400`; `error="Authenticated user header is required"` |
| B03 | should_return_400_when_authenticated_user_header_is_not_uuid | same as B02 but header `X-User-ID: not-a-uuid` | HTTP `400`; `error` contains `X-User-ID must be a valid UUID` |
| B04 | should_return_409_when_authenticated_user_does_not_match_payload_user | headers `GC-HDR-JSON` + `GC-HDR-USER-2`; body userID=`DS-USER-1` | HTTP `409`; `error="userID does not match authenticated user"` |
| B05 | should_return_400_when_payload_user_id_invalid | headers `GC-HDR-JSON` + `GC-HDR-USER-1`; body userID=`not-a-uuid` | HTTP `400`; `error` contains `userID must be a valid UUID` |
| B06 | should_return_400_when_payload_event_id_invalid | headers valid; body eventID=`not-a-uuid` | HTTP `400`; `error` contains `eventID must be a valid UUID` |
| B07 | should_return_400_when_seat_category_is_not_string | headers valid; body `seatCategory: 123` | HTTP `400`; `error="seatCategory must be a string"` |
| B08 | should_return_400_when_seat_category_blank | headers valid; body `seatCategory:"   "` | HTTP `400`; `error="seatCategory is required"` |
| B09 | should_return_400_when_qty_not_integer | headers valid; body `qty:"one"` | HTTP `400`; `error="qty must be an integer"` |
| B10 | should_return_400_when_qty_not_one | headers valid; body `qty:2` | HTTP `400`; `error="Only qty=1 is supported"` |
| B11 | should_return_404_when_event_not_found | headers valid; body eventID=`11111111-1111-1111-1111-111111111111` | HTTP `404`; `error="Event not found"` |
| B12 | should_return_404_when_inventory_category_not_found | headers valid; body `eventID=DS-EVENT-MAIN`, `seatCategory:"VIP_DOES_NOT_EXIST"` | HTTP `404`; `error` from inventory, typically `Category not found for event` |

---

### Group C: Reserve Endpoint Business Paths

| ID | Test name | Swagger input | Expected output |
|---|---|---|---|
| C01 | should_return_waitlisted_when_category_is_sold_out | headers `GC-HDR-JSON` + `GC-HDR-USER-1` + `GC-HDR-CORR`; body `{"userID":"00000000-0000-0000-0000-000000000001","eventID":"10000000-0000-0000-0000-000000000301","seatCategory":"CAT2","qty":1}` | HTTP `200`; `GC-RES-WAITLISTED`; response `status="WAITLISTED"`, `eventID` same, `seatCategory="CAT2"`, `waitlistID` uuid, `position` integer, response header `X-Correlation-ID` present |
| C02 | should_return_payment_pending_when_seat_is_available | headers `GC-HDR-JSON` + `GC-HDR-USER-1` + `GC-HDR-CORR`; body `{"userID":"00000000-0000-0000-0000-000000000001","eventID":"10000000-0000-0000-0000-000000000301","seatCategory":"PEN","qty":1}` | HTTP `200`; `GC-RES-PAYMENT-PENDING`; `status="PAYMENT_PENDING"`; capture `holdID` as `CAP-HOLD-PEN-01`; `returnURL` starts with `/booking/pending/`; `seatCategory="PEN"` |
| C03 | should_return_503_when_dependent_service_unavailable | Stop `user-service` container, then repeat C02 input | HTTP `503`; `error` contains `user-service is unavailable`; restart dependency after case |

---

### Group D: Reserve Confirm Endpoint

| ID | Test name | Swagger input | Expected output |
|---|---|---|---|
| D01 | should_return_400_when_confirm_header_missing | `POST /reserve/confirm`; headers `GC-HDR-JSON`; body `{"holdID":"40000000-0000-0000-0000-000000000003","userID":"00000000-0000-0000-0000-000000000001"}` | HTTP `400`; `error="Authenticated user header is required"` |
| D02 | should_return_409_when_confirm_header_mismatch | headers `GC-HDR-JSON` + `GC-HDR-USER-2`; body userID=`DS-USER-1` | HTTP `409`; `error="userID does not match authenticated user"` |
| D03 | should_return_400_when_hold_id_invalid | headers valid; body `holdID:"not-a-uuid"` | HTTP `400`; `error` contains `holdID must be a valid UUID` |
| D04 | should_return_404_when_hold_not_found | headers valid; body holdID=`22222222-2222-2222-2222-222222222222`, userID=`DS-USER-1` | HTTP `404`; `error` contains `Hold not found` |
| D05 | should_return_409_when_hold_not_owned_by_user | headers `GC-HDR-JSON` + `GC-HDR-USER-1`; body `{"holdID":"40000000-0000-0000-0000-000000000004","userID":"00000000-0000-0000-0000-000000000001"}` | HTTP `409`; `error="holdID does not belong to userID"` |
| D06 | should_return_409_when_hold_not_in_held_status | headers `GC-HDR-JSON` + `GC-HDR-USER-1`; body `{"holdID":"40000000-0000-0000-0000-000000000003","userID":"00000000-0000-0000-0000-000000000001"}` | HTTP `409`; `error="Hold is not in HELD status"` |
| D07 | should_return_confirmed_when_hold_already_confirmed | headers `GC-HDR-JSON` + `GC-HDR-USER-5`; body `{"holdID":"40000000-0000-0000-0000-000000000004","userID":"00000000-0000-0000-0000-000000000005"}` | HTTP `200`; `GC-RES-CONFIRMED`; `status="CONFIRMED"`; `holdID` matches input; `paymentStatus` string present |
| D08 | should_return_payment_pending_for_fresh_held_hold | Precondition: execute C02 first and capture `CAP-HOLD-PEN-01`; headers `GC-HDR-JSON` + `GC-HDR-USER-1`; body `{"holdID":"<CAP-HOLD-PEN-01>","userID":"00000000-0000-0000-0000-000000000001"}` | HTTP `200`; `status="PAYMENT_PENDING"`; includes `paymentIntentID`, `clientSecret`, `holdExpiry`, `returnURL` |

---

### Group E: Waitlist Confirm Endpoint

| ID | Test name | Swagger input | Expected output |
|---|---|---|---|
| E01 | should_return_400_when_waitlist_confirm_hold_id_invalid | `GET /waitlist/confirm/{hold_id}` with `hold_id=not-a-uuid` | HTTP `400`; `error` contains `holdID must be a valid UUID` |
| E02 | should_return_404_when_waitlist_confirm_hold_not_found | `GET /waitlist/confirm/33333333-3333-3333-3333-333333333333` | HTTP `404`; `error` contains `Hold not found` |
| E03 | should_return_expired_ui_status_for_expired_hold | `GET /waitlist/confirm/40000000-0000-0000-0000-000000000003` | HTTP `200`; body `uiStatus="EXPIRED"`; `hold.holdID` matches; `waitlist.status` expected `EXPIRED` |
| E04 | should_return_processing_when_no_terminal_mapping_matches | `GET /waitlist/confirm/40000000-0000-0000-0000-000000000004` | HTTP `200`; with OutSystems disabled, expected `uiStatus="PROCESSING"` (hold is CONFIRMED, payment not `SUCCEEDED`, waitlist not WAITING/HOLD_OFFERED) |

---

### Group F: Branch-forcing Cases for Full `uiStatus` Mapping Coverage

These are controlled-state cases to cover remaining branches in `GET /waitlist/confirm/{hold_id}`.

#### F0: Setup SQL (run in Supabase first)

```sql
-- Use released hold as branch fixture target
-- hold: 4b100000-0000-0000-0000-000000000002

-- Ensure waitlist row points to this hold
update public.waitlist_entries
set hold_id = '4b100000-0000-0000-0000-000000000002',
    status = 'HOLD_OFFERED',
    updated_at = now()
where waitlist_id = '60000000-0000-0000-0000-000000000002';

-- Ensure hold not expired and no eticket integration dependency for deterministic output
update public.seat_holds
set status = 'RELEASED',
    updated_at = now()
where hold_id = '4b100000-0000-0000-0000-000000000002';

-- Ensure a payment record exists with non-succeeded status first
insert into public.transactions (
  transaction_id, hold_id, event_id, user_id, amount, currency, status, refund_amount,
  correlation_id, provider_response, metadata, created_at, updated_at
)
select
  '9a000000-0000-0000-0000-000000000002',
  h.hold_id,
  h.event_id,
  h.user_id,
  h.amount,
  h.currency,
  'PENDING',
  0,
  gen_random_uuid(),
  '{}'::jsonb,
  '{}'::jsonb,
  now(),
  now()
from public.seat_holds h
where h.hold_id = '4b100000-0000-0000-0000-000000000002'
on conflict (transaction_id) do nothing;
```

| ID | Test name | Swagger input | Expected output |
|---|---|---|---|
| F01 | should_return_waitlist_offered_when_waitlist_status_hold_offered | `GET /waitlist/confirm/4b100000-0000-0000-0000-000000000002` after F0 | HTTP `200`; `uiStatus="WAITLIST_OFFERED"` |
| F02 | should_return_waitlist_pending_when_waitlist_status_waiting | Update same waitlist row to `status='WAITING'`; call same endpoint | HTTP `200`; `uiStatus="WAITLIST_PENDING"` |
| F03 | should_return_paid_processing_when_payment_status_succeeded_but_no_ticket | Update transaction for hold to `status='SUCCEEDED'`; call same endpoint | HTTP `200`; `uiStatus="PAID_PROCESSING"` |
| F04 | should_return_confirmed_when_eticket_exists | Requires valid OutSystems integration and existing ticket for hold; call same endpoint | HTTP `200`; `uiStatus="CONFIRMED"`; non-null `eticket` object |

---

## 6. Optional DB verification queries

```sql
select hold_id, user_id, status, hold_expires_at, amount, currency
from public.seat_holds
where hold_id = '<HOLD_ID>';

select waitlist_id, user_id, hold_id, status
from public.waitlist_entries
where hold_id = '<HOLD_ID>' or waitlist_id = '<WAITLIST_ID>';

select transaction_id, hold_id, status, amount, currency
from public.transactions
where hold_id = '<HOLD_ID>'
order by created_at desc;
```

## 7. Execution Order Recommendation

1. Group A (docs/health)
2. Group B (reserve validation/auth)
3. Group C (reserve business branches)
4. Group D (reserve confirm)
5. Group E (waitlist confirm deterministic)
6. Group F (branch-forcing advanced coverage)

## 8. Coverage Map

- `GET /health`: A01
- `GET /openapi.json`: A02
- `GET /docs`: A03
- `POST /reserve`: B01-B12, C01-C03
- `POST /reserve/confirm`: D01-D08
- `GET /waitlist/confirm/{hold_id}`: E01-E04, F01-F04

## 9. Known Practical Constraints

- `WAITLIST_OFFERED`, `WAITLIST_PENDING`, and `PAID_PROCESSING` usually require asynchronous scenario state or controlled DB setup; therefore Group F includes SQL setup to keep manual tests reproducible.
- `CONFIRMED` in waitlist-confirm requires e-ticket presence or reachable OutSystems state, so F04 is optional if OutSystems is intentionally disabled for deterministic local testing.

## 10. Gateway Parity Checks (Kong, non-Swagger)

These verify stricter auth posture that Setup expects for user-facing traffic.

- `POST http://localhost:8000/reserve` without `x-customer-api-key` -> expect `401`/`403` from Kong key-auth plugin.
- Same request with valid `x-customer-api-key` and valid `X-User-ID` -> should route and behave like C01/C02.
