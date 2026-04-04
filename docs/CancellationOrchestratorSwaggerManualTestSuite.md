# Cancellation Orchestrator Manual Swagger Test Suite

## 1) Test Design Summary

### 1.1 Unit/integration under test
- Primary API surfaces:
  - `POST /orchestrator/cancellation`
  - `POST /bookings/cancel/{booking_id}`
  - `POST /orchestrator/cancellation/reallocation/confirm`
- Supporting surfaces:
  - `GET /health`
  - `GET /openapi.json`
  - `GET /docs`
- Scope: manual integration validation through Swagger UI and Kong route parity checks.

### 1.2 Expected behavior
- Enforce booking ownership, cancellation policy, and refund-state gates.
- Trigger status transitions and orchestration outcomes:
  - `DENIED` for policy-ineligible cancellations.
  - `ALREADY_REFUNDED` for already-settled refunds.
  - `CANCELLATION_IN_PROGRESS` for refund failure compensation path.
  - `REALLOCATION_CONFIRMED` or `REALLOCATION_RECONCILIATION_REQUIRED` for reallocation confirmation flows.

### 1.3 Inputs/outputs and dependencies
- Inputs:
  - JSON payloads with UUIDs (`bookingID`, `userID`, `newHoldID`, `waitlistID`, optional `newUserID`, optional `reason`, optional `correlationID`).
  - Internal auth header for reallocation confirmation endpoint.
- Outputs:
  - Success payloads with status fields and identifiers.
  - Error payload shape `{"error": "...", "details"?: {...}}`.
- Dependencies:
  - payment-service, inventory-service, waitlist-service, user-service, event-service, OutSystems e-ticket service, RabbitMQ publish path.

### 1.4 Main failure risks covered
- Invalid UUID and required-field validation gaps.
- Booking ownership bypass attempts.
- Incorrect handling of payment states (`REFUND_PENDING`, `REFUND_FAILED`, `REFUND_SUCCEEDED`).
- Unauthorized use of reallocation-confirm endpoint.
- Waitlist owner mismatch and waitlist status mismatch.
- Upstream dependency and compensation behavior drift.

## 2) Sources Used

Project context reviewed in detail:
- `docs/Setup.md`
- `docs/Scenarios.md`
- Existing suite style references:
  - `docs/BookingStatusServiceSwaggerManualTestSuite.md`
  - `docs/payment-service-swagger-manual-test-cases.md`
  - `docs/ExpirySchedulerManualSwaggerTestSuite.md`

Implementation source of truth:
- `backend/composite/cancellation-orchestrator/cancellation_orchestrator.py`

Context7 references:
- OpenAPI 3.0.3 (`/websites/spec_openapis_oas_v3_0_3`)
  - Path params must declare `required: true`.
  - Operation `responses` object is required and should document success plus known error responses.
- Swagger UI (`/swagger-api/swagger-ui`)
  - `supportedSubmitMethods` controls Try it out execution support.
  - `deepLinking` enables operation/tag deep-link navigation in docs.

Supabase context source:
- Project ID: `cpxcpvcfbohvpiubbujg`
- Project URL: `https://cpxcpvcfbohvpiubbujg.supabase.co`
- Snapshot date: 2026-04-04

## 3) Environment and Preconditions

1. Bring stack up with fresh images:
   - `docker compose up -d --build`
2. Confirm service and docs availability:
   - Direct orchestrator docs: `http://localhost:6003/docs`
   - Direct OpenAPI: `http://localhost:6003/openapi.json`
   - Kong base: `http://localhost:8000`
3. Confirm `.env.local` has matching internal auth values used by orchestrator:
   - `INTERNAL_AUTH_HEADER` (default `X-Internal-Token`)
   - `INTERNAL_SERVICE_TOKEN`
4. For destructive mutation cases, execute them near the end or reseed fixtures after each run.

## 4) Supabase Snapshot (Current)

Observed status distributions:
- `transactions`: `PENDING=4`, `SUCCEEDED=7`, `FAILED=3`, `REFUND_PENDING=2`, `REFUND_SUCCEEDED=2`, `REFUND_FAILED=3`
- `waitlist_entries`: includes `WAITING`, `CONFIRMED`, `EXPIRED`, `CANCELLED`
- `cancellation_requests`: includes `REJECTED`, `PROCESSING_REFUND`, `CANCELLATION_IN_PROGRESS`, `COMPLETED`

Seeded/known booking fixtures for Scenario 3:

| Label | booking_id (transaction_id) | user_id | payment_status | within_policy | Note |
|---|---|---|---|---|---|
| BK_SUCCEEDED_WITHIN | `70000000-0000-0000-0000-000000000001` | `00000000-0000-0000-0000-000000000001` | `SUCCEEDED` | `true` | Candidate for refund attempt path |
| BK_REFUND_FAILED | `70000000-0000-0000-0000-000000000002` | `00000000-0000-0000-0000-000000000002` | `REFUND_FAILED` | `true` | Should be blocked by orchestrator gate |
| BK_ALREADY_REFUNDED | `70000000-0000-0000-0000-000000000003` | `00000000-0000-0000-0000-000000000005` | `REFUND_SUCCEEDED` | `true` | Should return `ALREADY_REFUNDED` |
| BK_REFUND_FAILED_ALT | `70000000-0000-0000-0000-000000000004` | `00000000-0000-0000-0000-000000000004` | `REFUND_FAILED` | `true` | Additional blocked state |
| BK_ALREADY_REFUNDED_ALT | `70000000-0000-0000-0000-000000000005` | `00000000-0000-0000-0000-000000000003` | `REFUND_SUCCEEDED` | `true` | Additional already-refunded case |
| BK_REFUND_PENDING | `7b100000-0000-0000-0000-000000000003` | `00000000-0000-0000-0000-000000000003` | `REFUND_PENDING` | `true` | Should be blocked as in-progress |
| BK_REFUND_FAILED_SEEDED | `7b100000-0000-0000-0000-000000000004` | `00000000-0000-0000-0000-000000000005` | `REFUND_FAILED` | `true` | Should be blocked as failed |
| BK_POLICY_DENIED | `7b100000-0000-0000-0000-000000000006` | `00000000-0000-0000-0000-000000000001` | `SUCCEEDED` | `false` | Event inside 48-hour lockout |

Known waitlist fixtures:

| Label | waitlist_id | user_id | status | hold_id | category |
|---|---|---|---|---|---|
| WL_CONFIRMED | `bcefea06-1048-45c9-bde2-04f4d80f3510` | `d1f9e7ed-f96f-4e47-bda8-2d4b985072f3` | `CONFIRMED` | `40000000-0000-0000-0000-000000000004` | `CAT2` |
| WL_CANCELLED | `1aa98295-4279-40b7-b29a-4c7dc7ad1dce` | `00000000-0000-0000-0000-000000000005` | `CANCELLED` | `40000000-0000-0000-0000-000000000004` | `CAT2` |
| WL_WAITING_EDITABLE | `6d3a5c49-7600-49d1-9632-a852475cd694` | `00000000-0000-0000-0000-000000000001` | `WAITING` | `null` | `CAT2` |

## 5) Reusable Assertions

- `RA-ERR`
  - Error responses include `error` string.
- `RA-UUID`
  - Returned IDs are valid UUID strings.
- `RA-JSON-OBJ`
  - JSON body is object-shaped and not array/string.

## 6) Manual Swagger Test Cases

### Group A: Contract and Input Validation

| ID | Test name | Arrange | Act (Swagger input) | Assert (expected output) |
|---|---|---|---|---|
| CO-001 | should_return_ok_when_health_called | Service running | `GET /health` | HTTP `200`; `status="ok"`; dependency flags present. |
| CO-002 | should_return_openapi_when_openapi_called | Service running | `GET /openapi.json` | HTTP `200`; includes paths for cancellation and reallocation endpoints; path param `booking_id` required. |
| CO-003 | should_render_docs_when_docs_called | Service running | `GET /docs` | HTTP `200`; Swagger UI renders. |
| CO-004 | should_return_400_when_json_body_is_not_object | None | `POST /orchestrator/cancellation` with raw JSON array `[]` | HTTP `400`; `error="JSON body must be an object"`. |
| CO-005 | should_return_400_when_booking_id_missing | None | `POST /orchestrator/cancellation` body `{"userID":"00000000-0000-0000-0000-000000000001"}` | HTTP `400`; `error="bookingID is required"`. |
| CO-006 | should_return_400_when_user_id_missing | None | `POST /orchestrator/cancellation` body `{"bookingID":"70000000-0000-0000-0000-000000000001"}` | HTTP `400`; `error="userID is required"`. |
| CO-007 | should_return_400_when_booking_id_invalid_uuid | None | `POST /orchestrator/cancellation` body `{"bookingID":"not-a-uuid","userID":"00000000-0000-0000-0000-000000000001"}` | HTTP `400`; `error` contains `bookingID must be a valid UUID`. |
| CO-008 | should_return_400_when_alias_path_booking_id_invalid | None | `POST /bookings/cancel/not-a-uuid` body `{"userID":"00000000-0000-0000-0000-000000000001"}` | HTTP `400`; `error` contains `bookingID must be a valid UUID`. |
| CO-009 | should_return_400_when_alias_user_id_missing | None | `POST /bookings/cancel/70000000-0000-0000-0000-000000000001` body `{}` | HTTP `400`; `error="userID is required"`. |
| CO-010 | should_return_404_when_booking_not_found | None | `POST /orchestrator/cancellation` body `{"bookingID":"00000000-0000-0000-0000-000000009999","userID":"00000000-0000-0000-0000-000000000001"}` | HTTP `404`; `error` indicates booking/payment record not found. |

### Group B: Cancellation Business Rules (Supabase-backed IDs)

| ID | Test name | Arrange | Act (Swagger input) | Assert (expected output) |
|---|---|---|---|---|
| CO-020 | should_return_409_when_booking_owned_by_different_user | Use `BK_SUCCEEDED_WITHIN` with non-owner user | `POST /orchestrator/cancellation` body `{"bookingID":"70000000-0000-0000-0000-000000000001","userID":"00000000-0000-0000-0000-000000000002"}` | HTTP `409`; `error="Booking does not belong to requesting user"`. |
| CO-021 | should_return_denied_when_outside_48h_policy | Use `BK_POLICY_DENIED` with owner | `POST /orchestrator/cancellation` body `{"bookingID":"7b100000-0000-0000-0000-000000000006","userID":"00000000-0000-0000-0000-000000000001"}` | HTTP `409`; body has `status="DENIED"`, `withinPolicy=false`, reason mentions 48-hour policy. |
| CO-022 | should_return_already_refunded_when_payment_status_refund_succeeded | Use `BK_ALREADY_REFUNDED` | `POST /orchestrator/cancellation` body `{"bookingID":"70000000-0000-0000-0000-000000000003","userID":"00000000-0000-0000-0000-000000000005"}` | HTTP `200`; `status="ALREADY_REFUNDED"`; includes `bookingID`, `holdID`. |
| CO-023 | should_return_409_when_refund_already_in_progress | Use `BK_REFUND_PENDING` | `POST /orchestrator/cancellation` body `{"bookingID":"7b100000-0000-0000-0000-000000000003","userID":"00000000-0000-0000-0000-000000000003"}` | HTTP `409`; `error="Refund is already in progress"`. |
| CO-024 | should_return_409_when_refund_previously_failed | Use `BK_REFUND_FAILED_SEEDED` | `POST /orchestrator/cancellation` body `{"bookingID":"7b100000-0000-0000-0000-000000000004","userID":"00000000-0000-0000-0000-000000000005"}` | HTTP `409`; `error="Refund previously failed and needs manual follow-up"`. |
| CO-025 | should_return_cancellation_in_progress_when_refund_request_fails | Use `BK_SUCCEEDED_WITHIN`; ensure this case runs late or on reset fixture | `POST /orchestrator/cancellation` body `{"bookingID":"70000000-0000-0000-0000-000000000001","userID":"00000000-0000-0000-0000-000000000001","reason":"Manual swagger failure-path validation"}` | HTTP `502`; body `status="CANCELLATION_IN_PROGRESS"`; `nextSteps` indicates manual follow-up. |
| CO-026 | should_return_409_after_previous_failure_sets_refund_failed | Run after CO-025 without reseed | Re-run CO-025 input | HTTP `409`; `error="Refund previously failed and needs manual follow-up"`. |

Notes for CO-025:
- In many local setups, this path is deterministic because seeded Stripe payment intent IDs are not live in Stripe test account, causing refund failure and compensation.

### Group C: Reallocation Confirm Endpoint

| ID | Test name | Arrange | Act (Swagger input) | Assert (expected output) |
|---|---|---|---|---|
| CO-030 | should_return_401_when_internal_token_missing | None | `POST /orchestrator/cancellation/reallocation/confirm` body `{"bookingID":"70000000-0000-0000-0000-000000000001","newHoldID":"40000000-0000-0000-0000-000000000004","waitlistID":"bcefea06-1048-45c9-bde2-04f4d80f3510"}` without internal header | HTTP `401`; `error="Unauthorized"`. |
| CO-031 | should_return_400_when_reallocation_payload_uuid_invalid | Set valid internal header | Same endpoint body with `newHoldID:"not-a-uuid"` | HTTP `400`; `error` mentions `newHoldID must be a valid UUID`. |
| CO-032 | should_return_409_when_waitlist_hold_does_not_match_new_hold | Internal header set; use `WL_CONFIRMED` | body `{"bookingID":"70000000-0000-0000-0000-000000000001","newHoldID":"40000000-0000-0000-0000-000000000005","waitlistID":"bcefea06-1048-45c9-bde2-04f4d80f3510"}` | HTTP `409`; `error="waitlist entry is not associated with newHoldID"`. |
| CO-033 | should_return_409_when_waitlist_entry_already_confirmed | Internal header set; use `WL_CONFIRMED` with matching hold | body `{"bookingID":"70000000-0000-0000-0000-000000000001","newHoldID":"40000000-0000-0000-0000-000000000004","waitlistID":"bcefea06-1048-45c9-bde2-04f4d80f3510"}` | HTTP `409`; `error="Waitlist entry is already confirmed"`. |
| CO-034 | should_return_409_when_waitlist_entry_not_eligible | Internal header set; use `WL_CANCELLED` | body `{"bookingID":"70000000-0000-0000-0000-000000000001","newHoldID":"40000000-0000-0000-0000-000000000004","waitlistID":"1aa98295-4279-40b7-b29a-4c7dc7ad1dce"}` | HTTP `409`; `error="Waitlist entry is not eligible for confirmation"`. |
| CO-035 | should_return_409_when_new_user_does_not_match_waitlist_owner | Prepare fixture SQL `FX-RC-01` below and set internal header | body `{"bookingID":"70000000-0000-0000-0000-000000000001","newHoldID":"5c300000-0000-0000-0000-000000000001","waitlistID":"6d3a5c49-7600-49d1-9632-a852475cd694","newUserID":"00000000-0000-0000-0000-000000000002"}` | HTTP `409`; `error="newUserID does not match the waitlist entry owner"`. |
| CO-036 | should_return_409_when_waitlist_payment_not_completed | Prepare fixture SQL `FX-RC-02` below and set internal header | body `{"bookingID":"70000000-0000-0000-0000-000000000001","newHoldID":"c6743671-e1c3-4a5e-9db8-df1be6f58ba5","waitlistID":"6d3a5c49-7600-49d1-9632-a852475cd694"}` | HTTP `409`; `error="Waitlist payment is not completed"`. |
| CO-037 | should_return_200_when_reallocation_confirmation_completes_successfully | Requires full dependency readiness: valid hold offered + payment `SUCCEEDED` + reachable OutSystems with transfer success | body uses valid live hold/waitlist pair + internal header | HTTP `200`; `status="REALLOCATION_CONFIRMED"`; includes `ticketID`, `seatNumber`, `newUserID`. |
| CO-038 | should_return_502_when_transfer_step_fails_after_hold_confirmed | Requires controlled setup where OutSystems `/etickets/update` fails but earlier dependency steps succeed | same endpoint with valid live pair + internal header | HTTP `502`; `status="REALLOCATION_RECONCILIATION_REQUIRED"`; includes `bookingID`, `waitlistID`, `newHoldID`, `nextSteps`. |

### Group D: Route Parity (Direct vs Kong)

| ID | Test name | Arrange | Act | Assert (expected output) |
|---|---|---|---|---|
| CO-040 | should_match_alias_denied_response_between_service_and_kong | Use policy-denied case CO-021 | Compare direct `http://localhost:6003/bookings/cancel/7b100000-0000-0000-0000-000000000006` vs Kong `http://localhost:8000/bookings/cancel/7b100000-0000-0000-0000-000000000006` with same body | Same status code (`409`) and same semantic payload (`status=DENIED`, reason). |
| CO-041 | should_match_validation_error_between_service_and_kong | Use invalid UUID path | Compare direct and Kong for `POST /bookings/cancel/not-a-uuid` | Same status code (`400`) and same validation error semantics. |

## 7) SQL Helpers

### 7.1 Read-only verification queries

Candidate booking context:

```sql
select
  t.transaction_id as booking_id,
  t.user_id,
  t.status as payment_status,
  t.hold_id,
  h.status as hold_status,
  sc.category_code as seat_category,
  e.event_date,
  (now() <= (e.event_date - interval '48 hours')) as within_policy
from public.transactions t
join public.seat_holds h on h.hold_id = t.hold_id
join public.seat_categories sc on sc.category_id = h.category_id
join public.events e on e.event_id = t.event_id
where t.transaction_id in (
  '70000000-0000-0000-0000-000000000001',
  '70000000-0000-0000-0000-000000000002',
  '70000000-0000-0000-0000-000000000003',
  '70000000-0000-0000-0000-000000000004',
  '70000000-0000-0000-0000-000000000005',
  '7b100000-0000-0000-0000-000000000003',
  '7b100000-0000-0000-0000-000000000004',
  '7b100000-0000-0000-0000-000000000006'
)
order by booking_id;
```

Waitlist snapshot:

```sql
select
  w.waitlist_id,
  w.user_id,
  w.status,
  w.hold_id,
  sc.category_code,
  w.event_id,
  w.joined_at
from public.waitlist_entries w
join public.seat_categories sc on sc.category_id = w.category_id
order by w.joined_at asc;
```

Post-cancellation mutation checks:

```sql
select transaction_id, hold_id, status, refund_status, refund_amount, failure_reason, updated_at
from public.transactions
where transaction_id = '70000000-0000-0000-0000-000000000001';
```

```sql
select cancellation_request_id, hold_id, transaction_id, status, attempt_count, reason, requested_at, resolved_at
from public.cancellation_requests
where transaction_id = '70000000-0000-0000-0000-000000000001'
order by requested_at desc;
```

### 7.2 Fixture helpers for Group C

`FX-RC-01` (for CO-035, user mismatch)

```sql
update public.waitlist_entries
set status = 'HOLD_OFFERED',
    hold_id = '5c300000-0000-0000-0000-000000000001'
where waitlist_id = '6d3a5c49-7600-49d1-9632-a852475cd694';
```

`FX-RC-02` (for CO-036, payment-not-completed using existing pending transaction hold)

```sql
update public.waitlist_entries
set status = 'HOLD_OFFERED',
    hold_id = 'c6743671-e1c3-4a5e-9db8-df1be6f58ba5'
where waitlist_id = '6d3a5c49-7600-49d1-9632-a852475cd694';
```

Cleanup after Group C fixture tests:

```sql
update public.waitlist_entries
set status = 'WAITING',
    hold_id = null
where waitlist_id = '6d3a5c49-7600-49d1-9632-a852475cd694';
```

## 8) Recommended Execution Order

1. Group A (contract and validation)
2. Group B non-destructive cases (CO-020 to CO-024)
3. Group C (CO-030 to CO-036), with fixture cleanup
4. Group D parity checks
5. Destructive path CO-025 and CO-026 (last), or run after a reseed reset

## 9) Coverage Matrix

Covered:
- All public cancellation orchestrator endpoints and supporting docs/health endpoints
- Input validation and UUID/path/body contract errors
- Policy/ownership/refund-state business gates
- Reallocation auth and state-gate behaviors
- Dependency-sensitive compensation/reconciliation status contracts
- Kong parity for fan-facing route

Not covered directly by this manual suite:
- Performance/load behavior under high cancellation concurrency
- Automated race-condition replay tests
- Full end-to-end email content validation beyond API response contracts
