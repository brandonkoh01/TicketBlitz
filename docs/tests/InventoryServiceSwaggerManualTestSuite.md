# Inventory Service Manual Swagger Test Suite

## 0. Test Design Reasoning

### 0.1 What is being tested

- Integration behavior of the inventory microservice API surface through Swagger.
- Contract correctness for request validation, state transitions, and error responses.
- Critical inventory business logic: availability, hold lifecycle, flash-sale toggling, seat status transitions, and hold expiration maintenance.

### 0.2 Inputs, outputs, dependencies, and failure risks

- Inputs: path params, JSON request bodies, idempotency keys, and concurrent request timing.
- Outputs: HTTP status codes, response body fields, and RabbitMQ side effects.
- Dependencies: Supabase (state and constraints), RabbitMQ (event publication), Kong routing behavior, and Flasgger-generated Swagger UI/OpenAPI docs.
- Main risks covered: race conditions on last seats, stale or invalid state transitions, idempotency drift, schema/rpc drift, and public route misconfiguration.

### 0.3 Test type selection and coverage intent

- Primary type: manual integration tests using Swagger (real HTTP + real DB state).
- Secondary checks: DB preflight/setup SQL for determinism and side-effect verification for message publishing.
- Coverage priority: critical business logic first, then edge/error paths, then gateway and observability checks.

## 1. Scope

This document defines manual, Swagger-first integration test cases for the inventory microservice.

Coverage includes:

- API contract and documentation endpoints
- Read behavior
- State mutation behavior
- Validation and error handling
- Idempotency
- Concurrency
- Event side effects
- Kong public-route regression checks

## 2. Environment and Entry Points

- Inventory Swagger UI (direct service): `http://localhost:5003/inventory/docs/`
- Inventory OpenAPI JSON: `http://localhost:5003/inventory/openapi.json`
- Inventory service via Kong (read-only route): `http://localhost:8000/inventory/...`

Important:

- Run mutation tests on direct service Swagger (`5003`) because Kong is configured as read-only for `/inventory` methods (`GET`, `OPTIONS`).

### 2.1 Source Context Used To Craft Inputs

- Supabase project: `cpxcpvcfbohvpiubbujg`
- Live event snapshot used: EVT-301 (`10000000-0000-0000-0000-000000000301`) and EVT-401-MANUAL (`10000000-0000-0000-0000-000000000401`).
- Live seat distribution for EVT-301 used to shape availability and sold-out cases.
- Context7 documentation source used: Flasgger (`/flasgger/flasgger`) with emphasis on `specs_route`, generated OpenAPI spec route behavior, and Swagger UI initialization patterns.
- Current DB preflight finding at authoring time: inventory RPC functions may be missing in runtime DB, so mutation tests include explicit RPC readiness checks.

### 2.2 Setup and Scenario Constraints Driving This Suite

- Setup contract: UI traffic enters through Kong, while internal service-to-service calls bypass Kong. This suite therefore runs mutation tests against direct inventory Swagger (`5003`) and keeps Kong checks focused on public read-only behavior.
- Setup build sequence: `/health`, then GET, POST, PUT, then error responses. Test section ordering mirrors this to keep execution and debugging predictable.
- Setup ownership model: Inventory Service owns `seats` and `seat_holds`. Cross-service behavior is validated through Inventory API outputs and events, not by direct writes from other services.
- Scenarios contract: Step 1A/1B/1C/1D and Step 2A/2B/2C explicitly depend on inventory availability, hold lifecycle, expire-holds maintenance, flash-sale toggling, and sold-out event publication. These are traced in Section 17.

## 3. Global Components (Reusable Test Data)

Use these shared constants across test cases.

### 3.1 IDs from Supabase (project `cpxcpvcfbohvpiubbujg`)

- `EVENT_ID_MAIN`: `10000000-0000-0000-0000-000000000301` (EVT-301)
- `EVENT_ID_ALT`: `10000000-0000-0000-0000-000000000401` (EVT-401-MANUAL)
- `USER_ID_BRANDON`: `00000000-0000-0000-0000-000000000001`
- `USER_ID_BOONE`: `00000000-0000-0000-0000-000000000002`
- `USER_ID_IAN`: `00000000-0000-0000-0000-000000000003`
- `CATEGORY_CAT1`: `CAT1`
- `CATEGORY_CAT2`: `CAT2`
- `CATEGORY_PEN`: `PEN`
- `SEAT_ID_AVAILABLE_SAMPLE`: `30000000-0000-0000-0000-000000000042`
- `SEAT_ID_SOLD_SAMPLE`: `30000000-0000-0000-0000-000000000020`
- `KNOWN_EXPIRED_HOLD_ID`: `40000000-0000-0000-0000-000000000003`
- `INVALID_UUID`: `not-a-uuid`

### 3.2 Current seat snapshot (EVT-301 at time of authoring)

- CAT1: AVAILABLE=2, PENDING_WAITLIST=1, SOLD=3
- CAT2: SOLD=2
- PEN: AVAILABLE=2, SOLD=1

### 3.3 Reusable payload templates

`CREATE_HOLD_PUBLIC_TEMPLATE`

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "00000000-0000-0000-0000-000000000001",
  "seatCategory": "PEN",
  "qty": 1,
  "fromWaitlist": false,
  "idempotencyKey": "swagger-manual-public-001"
}
```

`CREATE_HOLD_WAITLIST_TEMPLATE`

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "00000000-0000-0000-0000-000000000002",
  "seatCategory": "CAT1",
  "qty": 1,
  "fromWaitlist": true,
  "idempotencyKey": "swagger-manual-waitlist-001"
}
```

`FLASH_SALE_ENABLE_TEMPLATE`

```json
{
  "active": true,
  "flashSaleID": "70000000-0000-0000-0000-000000000001"
}
```

`FLASH_SALE_DISABLE_TEMPLATE`

```json
{
  "active": false
}
```

`STANDARD_ERROR_BODY`

```json
{
  "error": "<message>"
}
```

### 3.4 Captured variables during execution

Capture and reuse these:

- `HOLD_PUBLIC_A`
- `HOLD_WAITLIST_A`
- `HOLD_RELEASE_A`
- `HOLD_TIMEOUT_A`

## 4. Preflight Cases

### TC-INV-001 should_load_swagger_ui_when_docs_route_requested

- Endpoint: `GET /inventory/docs/`
- Input: none
- Expected HTTP status: `200`
- Expected output: Swagger UI HTML page renders and includes Inventory API title.

### TC-INV-002 should_return_openapi_json_when_spec_route_requested

- Endpoint: `GET /inventory/openapi.json`
- Input: none
- Expected HTTP status: `200`
- Expected output:
  - JSON object with top-level `swagger: "2.0"`
  - `paths` include at least:
    - `/inventory/{event_id}/{seat_category}`
    - `/inventory/hold`
    - `/inventory/hold/{hold_id}`
    - `/inventory/hold/{hold_id}/confirm`
    - `/inventory/hold/{hold_id}/release`
    - `/inventory/seat/{seat_id}/status`
    - `/inventory/maintenance/expire-holds`

### TC-INV-003 should_return_health_status_when_service_is_up

- Endpoint: `GET /health`
- Input: none
- Expected HTTP status: `200`
- Expected output:

```json
{
  "status": "ok",
  "service": "inventory-service",
  "supabaseConfigured": true,
  "rabbitmqConfigured": true
}
```

### TC-INV-004 should_have_required_inventory_rpc_functions_before_mutation_tests

- Type: DB preflight (outside Swagger)
- SQL input:

```sql
select proname
from pg_proc
where proname in (
  'inventory_create_hold',
  'inventory_confirm_hold',
  'inventory_release_hold',
  'inventory_expire_holds'
)
order by proname;
```

- Expected output: 4 rows, one per function.
- If this fails: apply schema updates before running mutation API tests.

### TC-INV-005 should_verify_seed_event_and_categories_exist

- Type: DB preflight (outside Swagger)
- SQL input:

```sql
select event_id, event_code from public.events where event_id = '10000000-0000-0000-0000-000000000301';
select category_code from public.seat_categories where event_id = '10000000-0000-0000-0000-000000000301' order by category_code;
```

- Expected output:
  - event row exists for EVT-301
  - categories include CAT1, CAT2, PEN

### TC-INV-006 should_return_not_found_for_unknown_route

- Endpoint: `GET /inventory/this-route-does-not-exist`
- Input: none
- Expected HTTP status: `404`
- Expected output:

```json
{
  "error": "Not found"
}
```

## 5. Inventory Availability Cases

### TC-INV-010 should_return_available_status_for_pen_when_available_seats_exist

- Endpoint: `GET /inventory/{event_id}/{seat_category}`
- Path input: `event_id=10000000-0000-0000-0000-000000000301`, `seat_category=PEN`
- Expected HTTP status: `200`
- Expected output:

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "seatCategory": "PEN",
  "available": 1,
  "status": "AVAILABLE"
}
```

- Assertion rule: `available >= 1` and `status == "AVAILABLE"`.

### TC-INV-011 should_return_sold_out_status_when_no_available_seats_in_category

- Endpoint: `GET /inventory/{event_id}/{seat_category}`
- Path input: `event_id=10000000-0000-0000-0000-000000000301`, `seat_category=CAT2`
- Expected HTTP status: `200`
- Expected output:

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "seatCategory": "CAT2",
  "available": 0,
  "status": "SOLD_OUT"
}
```

### TC-INV-012 should_normalize_category_case_when_lowercase_category_is_provided

- Endpoint: `GET /inventory/{event_id}/{seat_category}`
- Path input: `event_id=10000000-0000-0000-0000-000000000301`, `seat_category=pen`
- Expected HTTP status: `200`
- Expected output includes `"seatCategory": "PEN"`.

### TC-INV-013 should_return_400_when_event_id_is_invalid_uuid

- Endpoint: `GET /inventory/{event_id}/{seat_category}`
- Path input: `event_id=not-a-uuid`, `seat_category=CAT1`
- Expected HTTP status: `400`
- Expected output:

```json
{
  "error": "Invalid eventID"
}
```

### TC-INV-014 should_return_404_when_category_not_found_for_event

- Endpoint: `GET /inventory/{event_id}/{seat_category}`
- Path input: `event_id=10000000-0000-0000-0000-000000000301`, `seat_category=VIP_DOES_NOT_EXIST`
- Expected HTTP status: `404`
- Expected output:

```json
{
  "error": "Category not found for event"
}
```

## 6. Flash Sale State Cases

### TC-INV-020 should_activate_flash_sale_when_valid_payload_is_sent

- Precondition: `flashSaleID` must already exist in `public.flash_sales` for the target event. If missing, create it with the SQL fixture in Section 15.
- Endpoint: `PUT /inventory/{event_id}/flash-sale`
- Path input: `event_id=10000000-0000-0000-0000-000000000301`
- Body input:

```json
{
  "active": true,
  "flashSaleID": "70000000-0000-0000-0000-000000000001"
}
```

- Expected HTTP status: `200`
- Expected output:

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "flashSaleActive": true,
  "flashSaleID": "70000000-0000-0000-0000-000000000001"
}
```

### TC-INV-021 should_deactivate_flash_sale_when_active_is_false

- Endpoint: `PUT /inventory/{event_id}/flash-sale`
- Path input: `event_id=10000000-0000-0000-0000-000000000301`
- Body input:

```json
{
  "active": false
}
```

- Expected HTTP status: `200`
- Expected output has `flashSaleActive=false` and `flashSaleID=null`.

### TC-INV-022 should_return_400_when_active_true_without_flash_sale_id

- Endpoint: `PUT /inventory/{event_id}/flash-sale`
- Path input: `event_id=10000000-0000-0000-0000-000000000301`
- Body input:

```json
{
  "active": true
}
```

- Expected HTTP status: `400`
- Expected output:

```json
{
  "error": "flashSaleID is required when active is true"
}
```

### TC-INV-023 should_return_400_when_flash_sale_id_is_invalid

- Endpoint: `PUT /inventory/{event_id}/flash-sale`
- Path input: `event_id=10000000-0000-0000-0000-000000000301`
- Body input:

```json
{
  "active": true,
  "flashSaleID": "not-a-uuid"
}
```

- Expected HTTP status: `400`
- Expected output includes error `Invalid flashSaleID`.

### TC-INV-024 should_return_400_when_active_is_not_boolean

- Endpoint: `PUT /inventory/{event_id}/flash-sale`
- Path input: `event_id=10000000-0000-0000-0000-000000000301`
- Body input:

```json
{
  "active": "banana"
}
```

- Expected HTTP status: `400`
- Expected output includes error `active must be a boolean`.

### TC-INV-025 should_return_400_when_flash_sale_event_id_is_invalid_uuid

- Endpoint: `PUT /inventory/{event_id}/flash-sale`
- Path input: `event_id=not-a-uuid`
- Body input:

```json
{
  "active": false
}
```

- Expected HTTP status: `400`
- Expected output includes error `Invalid eventID`.

## 7. Create Hold Cases (`POST /inventory/hold`)

### TC-INV-030 should_create_public_hold_when_available_public_seat_exists

- Endpoint: `POST /inventory/hold`
- Body input:

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "00000000-0000-0000-0000-000000000001",
  "seatCategory": "PEN",
  "qty": 1,
  "fromWaitlist": false,
  "idempotencyKey": "swagger-manual-public-001"
}
```

- Expected HTTP status: `201`
- Expected output contains:
  - `holdID` as UUID
  - `eventID` = EVT-301
  - `seatCategory` = PEN
  - `holdStatus` = HELD
  - `fromWaitlist` = false
  - `currency` = SGD
- Capture: `HOLD_PUBLIC_A = holdID`.

### TC-INV-031 should_return_same_hold_when_idempotency_key_is_replayed_with_same_payload

- Endpoint: `POST /inventory/hold`
- Body input: exactly same as TC-INV-030
- Expected HTTP status: `200`
- Expected output:
  - `holdID == HOLD_PUBLIC_A`
  - `holdStatus` remains HELD or CONFIRMED depending on subsequent actions

### TC-INV-032 should_return_409_when_idempotency_key_reused_with_different_user_or_context

- Endpoint: `POST /inventory/hold`
- Body input:

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "00000000-0000-0000-0000-000000000002",
  "seatCategory": "PEN",
  "qty": 1,
  "fromWaitlist": false,
  "idempotencyKey": "swagger-manual-public-001"
}
```

- Expected HTTP status: `409`
- Expected output:

```json
{
  "error": "idempotencyKey was already used for a different user or event"
}
```

### TC-INV-033 should_create_waitlist_hold_when_pending_waitlist_seat_exists

- Endpoint: `POST /inventory/hold`
- Body input:

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "00000000-0000-0000-0000-000000000002",
  "seatCategory": "CAT1",
  "qty": 1,
  "fromWaitlist": true,
  "idempotencyKey": "swagger-manual-waitlist-001"
}
```

- Expected HTTP status: `201`
- Expected output contains:
  - `holdStatus` = HELD
  - `fromWaitlist` = true
  - `seatCategory` = CAT1
- Capture: `HOLD_WAITLIST_A = holdID`.

### TC-INV-034 should_return_400_when_qty_not_equal_to_1

- Endpoint: `POST /inventory/hold`
- Body input:

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "00000000-0000-0000-0000-000000000001",
  "seatCategory": "PEN",
  "qty": 2,
  "fromWaitlist": false
}
```

- Expected HTTP status: `400`
- Expected output includes error `Only qty=1 is supported`.

### TC-INV-035 should_return_400_when_required_seat_category_missing

- Endpoint: `POST /inventory/hold`
- Body input:

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "00000000-0000-0000-0000-000000000001",
  "qty": 1,
  "fromWaitlist": false
}
```

- Expected HTTP status: `400`
- Expected output includes error `seatCategory is required`.

### TC-INV-036 should_return_400_when_user_id_is_invalid

- Endpoint: `POST /inventory/hold`
- Body input:

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "not-a-uuid",
  "seatCategory": "PEN",
  "qty": 1,
  "fromWaitlist": false
}
```

- Expected HTTP status: `400`
- Expected output includes error `Invalid userID`.

### TC-INV-037 should_return_404_when_category_not_found

- Endpoint: `POST /inventory/hold`
- Body input:

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "00000000-0000-0000-0000-000000000001",
  "seatCategory": "VIP_DOES_NOT_EXIST",
  "qty": 1,
  "fromWaitlist": false
}
```

- Expected HTTP status: `404`
- Expected output includes error `Category not found for event`.

### TC-INV-038 should_return_409_when_no_public_seat_available

- Endpoint: `POST /inventory/hold`
- Body input:

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "00000000-0000-0000-0000-000000000003",
  "seatCategory": "CAT2",
  "qty": 1,
  "fromWaitlist": false,
  "idempotencyKey": "swagger-cat2-no-seat-001"
}
```

- Expected HTTP status: `409`
- Expected output includes error `No seat available for hold`.

### TC-INV-039 should_return_400_when_idempotency_key_not_string

- Endpoint: `POST /inventory/hold`
- Body input:

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "00000000-0000-0000-0000-000000000001",
  "seatCategory": "PEN",
  "qty": 1,
  "fromWaitlist": false,
  "idempotencyKey": 12345
}
```

- Expected HTTP status: `400`
- Expected output includes error `idempotencyKey must be a string`.

## 8. Get Hold Cases (`GET /inventory/hold/{hold_id}`)

### TC-INV-040 should_return_hold_details_for_existing_hold

- Endpoint: `GET /inventory/hold/{hold_id}`
- Path input: `hold_id=HOLD_PUBLIC_A`
- Expected HTTP status: `200`
- Expected output contains:
  - `holdID == HOLD_PUBLIC_A`
  - `eventID == EVENT_ID_MAIN`
  - `holdStatus` in {HELD, CONFIRMED, RELEASED, EXPIRED}

### TC-INV-041 should_return_400_for_invalid_hold_uuid

- Endpoint: `GET /inventory/hold/{hold_id}`
- Path input: `hold_id=not-a-uuid`
- Expected HTTP status: `400`
- Expected output includes error `Invalid holdID`.

### TC-INV-042 should_return_404_for_unknown_hold_id

- Endpoint: `GET /inventory/hold/{hold_id}`
- Path input: `hold_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`
- Expected HTTP status: `404`
- Expected output includes error `Hold not found`.

## 9. Confirm Hold Cases (`PUT /inventory/hold/{hold_id}/confirm`)

### TC-INV-050 should_confirm_held_hold_when_payment_success_correlation_id_provided

- Endpoint: `PUT /inventory/hold/{hold_id}/confirm`
- Path input: `hold_id=HOLD_PUBLIC_A`
- Body input:

```json
{
  "correlationID": "81000000-0000-0000-0000-000000000001"
}
```

- Expected HTTP status: `200`
- Expected output contains:
  - `holdID == HOLD_PUBLIC_A`
  - `holdStatus == "CONFIRMED"`
  - `seatStatus == "SOLD"`
  - `correlationID == "81000000-0000-0000-0000-000000000001"`

### TC-INV-051 should_be_idempotent_when_confirm_called_again_on_confirmed_hold

- Endpoint: `PUT /inventory/hold/{hold_id}/confirm`
- Path input: `hold_id=HOLD_PUBLIC_A`
- Body input: `{}`
- Expected HTTP status: `200`
- Expected output contains `holdStatus == "CONFIRMED"`.

### TC-INV-052 should_return_404_when_confirming_unknown_hold

- Endpoint: `PUT /inventory/hold/{hold_id}/confirm`
- Path input: `hold_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`
- Body input: `{}`
- Expected HTTP status: `404`
- Expected output includes error `Hold not found`.

### TC-INV-053 should_return_400_when_confirm_correlation_id_invalid

- Endpoint: `PUT /inventory/hold/{hold_id}/confirm`
- Path input: `hold_id=HOLD_PUBLIC_A`
- Body input:

```json
{
  "correlationID": "bad-uuid"
}
```

- Expected HTTP status: `400`
- Expected output includes error `Invalid correlationID`.

### TC-INV-054 should_return_409_when_hold_not_in_held_state

- Endpoint: `PUT /inventory/hold/{hold_id}/confirm`
- Path input: `hold_id=40000000-0000-0000-0000-000000000003`
- Body input: `{}`
- Expected HTTP status: `409`
- Expected output:

```json
{
  "error": "Hold is not in HELD state"
}
```

## 10. Release Hold Cases (`PUT /inventory/hold/{hold_id}/release`)

### TC-INV-060 should_release_waitlist_hold_to_pending_waitlist_on_manual_release

- Endpoint: `PUT /inventory/hold/{hold_id}/release`
- Path input: `hold_id=HOLD_WAITLIST_A`
- Body input:

```json
{
  "reason": "MANUAL_RELEASE"
}
```

- Expected HTTP status: `200`
- Expected output contains:
  - `holdID == HOLD_WAITLIST_A`
  - `holdStatus == "RELEASED"`
  - `seatStatus == "PENDING_WAITLIST"`

### TC-INV-061 should_be_idempotent_when_releasing_already_released_hold

- Endpoint: `PUT /inventory/hold/{hold_id}/release`
- Path input: `hold_id=HOLD_WAITLIST_A`
- Body input:

```json
{
  "reason": "MANUAL_RELEASE"
}
```

- Expected HTTP status: `200`
- Expected output contains `holdStatus == "RELEASED"`.

### TC-INV-062 should_return_400_when_release_reason_invalid

- Endpoint: `PUT /inventory/hold/{hold_id}/release`
- Path input: `hold_id=HOLD_WAITLIST_A`
- Body input:

```json
{
  "reason": "INVALID_REASON"
}
```

- Expected HTTP status: `400`
- Expected output includes error `Invalid release reason`.

### TC-INV-063 should_return_404_when_releasing_unknown_hold

- Endpoint: `PUT /inventory/hold/{hold_id}/release`
- Path input: `hold_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`
- Body input:

```json
{
  "reason": "MANUAL_RELEASE"
}
```

- Expected HTTP status: `404`
- Expected output includes error `Hold not found`.

### TC-INV-064 should_return_409_when_releasing_non_held_hold

- Endpoint: `PUT /inventory/hold/{hold_id}/release`
- Path input: `hold_id=HOLD_PUBLIC_A` (already CONFIRMED from TC-INV-050)
- Body input:

```json
{
  "reason": "MANUAL_RELEASE"
}
```

- Expected HTTP status: `409`
- Expected output includes error `Hold is not in HELD state`.

### TC-INV-065 should_release_public_hold_to_pending_waitlist_on_payment_timeout

- Precondition: create fresh HELD hold and capture as `HOLD_TIMEOUT_A`.
- Endpoint: `PUT /inventory/hold/{hold_id}/release`
- Path input: `hold_id=HOLD_TIMEOUT_A`
- Body input:

```json
{
  "reason": "PAYMENT_TIMEOUT"
}
```

- Expected HTTP status: `200`
- Expected output contains:
  - `holdStatus == "RELEASED"`
  - `seatStatus == "PENDING_WAITLIST"`
  - `releaseAt` not null

### TC-INV-066 should_release_hold_with_cancellation_reason_for_scenario3_compensation_flow

- Precondition: create fresh HELD hold and capture as `HOLD_RELEASE_A`.
- Endpoint: `PUT /inventory/hold/{hold_id}/release`
- Path input: `hold_id=HOLD_RELEASE_A`
- Body input:

```json
{
  "reason": "CANCELLATION"
}
```

- Expected HTTP status: `200`
- Expected output contains:
  - `holdStatus == "RELEASED"`
  - `seatStatus == "PENDING_WAITLIST"`
- Expected side effect: release event verification is covered in TC-INV-092.

## 11. Seat Status Update Cases (`PUT /inventory/seat/{seat_id}/status`)

### TC-INV-070 should_transition_available_to_pending_waitlist

- Endpoint: `PUT /inventory/seat/{seat_id}/status`
- Path input: `seat_id=30000000-0000-0000-0000-000000000042`
- Body input:

```json
{
  "status": "PENDING_WAITLIST"
}
```

- Expected HTTP status: `200`
- Expected output contains `status == "PENDING_WAITLIST"`.

### TC-INV-071 should_transition_pending_waitlist_to_held

- Endpoint: `PUT /inventory/seat/{seat_id}/status`
- Path input: `seat_id=30000000-0000-0000-0000-000000000042`
- Body input:

```json
{
  "status": "HELD"
}
```

- Expected HTTP status: `200`
- Expected output contains `status == "HELD"`.

### TC-INV-072 should_transition_held_to_available

- Endpoint: `PUT /inventory/seat/{seat_id}/status`
- Path input: `seat_id=30000000-0000-0000-0000-000000000042`
- Body input:

```json
{
  "status": "AVAILABLE"
}
```

- Expected HTTP status: `200`
- Expected output contains `status == "AVAILABLE"`.

### TC-INV-073 should_transition_held_to_sold

- Precondition: seat first moved to HELD.
- Endpoint: `PUT /inventory/seat/{seat_id}/status`
- Path input: `seat_id=30000000-0000-0000-0000-000000000042`
- Body input:

```json
{
  "status": "SOLD"
}
```

- Expected HTTP status: `200`
- Expected output contains `status == "SOLD"`.

### TC-INV-074 should_return_200_noop_when_setting_same_status

- Endpoint: `PUT /inventory/seat/{seat_id}/status`
- Path input: `seat_id=30000000-0000-0000-0000-000000000020` (already SOLD)
- Body input:

```json
{
  "status": "SOLD"
}
```

- Expected HTTP status: `200`
- Expected output contains same status `SOLD`.

### TC-INV-075 should_return_409_for_invalid_transition_from_sold_to_available

- Endpoint: `PUT /inventory/seat/{seat_id}/status`
- Path input: `seat_id=30000000-0000-0000-0000-000000000020`
- Body input:

```json
{
  "status": "AVAILABLE"
}
```

- Expected HTTP status: `409`
- Expected output contains error message about invalid transition from SOLD to AVAILABLE.

### TC-INV-076 should_return_400_for_invalid_status_literal

- Endpoint: `PUT /inventory/seat/{seat_id}/status`
- Path input: `seat_id=30000000-0000-0000-0000-000000000042`
- Body input:

```json
{
  "status": "RESERVED"
}
```

- Expected HTTP status: `400`
- Expected output includes error `Invalid seat status`.

### TC-INV-077 should_return_400_when_status_missing

- Endpoint: `PUT /inventory/seat/{seat_id}/status`
- Path input: `seat_id=30000000-0000-0000-0000-000000000042`
- Body input:

```json
{}
```

- Expected HTTP status: `400`
- Expected output includes error `status is required`.

### TC-INV-078 should_return_404_when_seat_not_found

- Endpoint: `PUT /inventory/seat/{seat_id}/status`
- Path input: `seat_id=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa`
- Body input:

```json
{
  "status": "AVAILABLE"
}
```

- Expected HTTP status: `404`
- Expected output includes error `Seat not found`.

### TC-INV-079 should_transition_pending_waitlist_to_available_when_no_waitlist_user_exists

- Precondition: seat currently in `PENDING_WAITLIST` (set via TC-INV-070 if needed).
- Endpoint: `PUT /inventory/seat/{seat_id}/status`
- Path input: `seat_id=30000000-0000-0000-0000-000000000042`
- Body input:

```json
{
  "status": "AVAILABLE"
}
```

- Expected HTTP status: `200`
- Expected output contains `status == "AVAILABLE"`.

## 12. Expire Holds Cases (`POST /inventory/maintenance/expire-holds`)

### TC-INV-080 should_return_zero_when_no_expired_held_holds_exist

- Endpoint: `POST /inventory/maintenance/expire-holds`
- Input: no body
- Expected HTTP status: `200`
- Expected output:

```json
{
  "expiredHolds": [],
  "count": 0
}
```

- Note: run this after ensuring no HELD hold has `hold_expires_at <= now()`.

### TC-INV-081 should_expire_overdue_held_hold_and_return_expired_record

- Precondition: create a HELD hold and use the SQL setup in Section 15 to set both `created_at` and `hold_expires_at` to past values (this avoids violating `seat_holds_hold_expiry_chk`, which requires `hold_expires_at > created_at`).
- Endpoint: `POST /inventory/maintenance/expire-holds`
- Input: no body
- Expected HTTP status: `200`
- Expected output:
  - `count >= 1`
  - each item has `holdID`, `seatID`, `eventID`, `seatCategory`, `userID`
  - expired hold appears in list

### TC-INV-082 should_be_idempotent_for_already_expired_holds_on_second_run

- Endpoint: `POST /inventory/maintenance/expire-holds`
- Input: no body
- Expected HTTP status: `200`
- Expected output:
  - previously expired hold from TC-INV-081 no longer returned
  - count decreases to 0 if no other expired HELD holds exist

### TC-INV-083 should_expire_waitlist_origin_hold_and_keep_queue_protected

- Precondition: overdue HELD hold exists with `from_waitlist=true`.
- Endpoint: `POST /inventory/maintenance/expire-holds`
- Input: no body
- Expected HTTP status: `200`
- Expected output includes expired hold item.
- Follow-up expected state:
  - `GET /inventory/hold/{holdID}` returns `holdStatus=EXPIRED`
  - corresponding seat status returns to `PENDING_WAITLIST`

## 13. Concurrency, Side Effects, and Gateway Regression

### TC-INV-090 should_return_one_created_and_one_rejected_when_two_parallel_holds_compete_for_single_remaining_seat

- Type: concurrent manual test (two Swagger tabs)
- Preconditions:
  - Only one seat AVAILABLE in a chosen category.
  - Use different idempotency keys in both requests.
- Inputs:
  - Two simultaneous `POST /inventory/hold` requests.
- Expected output:
  - one response `201` with hold payload
  - one response `409` with `No seat available for hold`

### TC-INV-091 should_return_created_and_idempotent_on_parallel_replay_with_same_idempotency_key

- Type: concurrent manual test (two Swagger tabs)
- Preconditions: same payload and same idempotencyKey in both requests.
- Expected output:
  - one response `201`
  - one response `200`
  - both responses have same `holdID`

### TC-INV-092 should_publish_seat_released_event_when_release_endpoint_succeeds

- Trigger: successful `PUT /inventory/hold/{hold_id}/release`
- Input: any HELD hold, reason MANUAL_RELEASE, PAYMENT_TIMEOUT, or CANCELLATION
- Expected HTTP output: `200`
- Expected side effect (RabbitMQ): message with routing key `seat.released` containing:

```json
{
  "eventID": "<uuid>",
  "seatCategory": "<code>",
  "seatID": "<uuid>",
  "qty": 1,
  "reason": "MANUAL_RELEASE|PAYMENT_TIMEOUT|CANCELLATION"
}
```

### TC-INV-093 should_publish_seat_released_event_for_each_expired_hold_in_maintenance_job

- Trigger: `POST /inventory/maintenance/expire-holds`
- Input: no body
- Expected HTTP output: `200` with `count = N`
- Expected side effect: `N` `seat.released` messages with `reason=PAYMENT_TIMEOUT` and `expiredHoldID` set.

### TC-INV-094 should_publish_category_sold_out_when_flash_sale_active_and_category_fully_sold_on_confirm

- Preconditions:
  - flash sale active for event
  - confirming hold causes last non-sold seat in category to become SOLD
- Trigger: `PUT /inventory/hold/{hold_id}/confirm`
- Expected HTTP output: `200`
- Expected side effect: one `category.sold_out` message with:

```json
{
  "eventID": "<uuid>",
  "category": "<code>",
  "flashSaleID": "<uuid>",
  "soldAt": "<iso-timestamp>"
}
```

### TC-INV-095 should_allow_read_requests_via_kong_but_block_public_write_requests

- Steps:
  - Send `GET /inventory/{eventID}/{seatCategory}` via `http://localhost:8000`
  - Send `POST /inventory/hold` via `http://localhost:8000`
  - Send `PUT /inventory/hold/{holdID}/confirm` via `http://localhost:8000`
- Expected output:
  - GET returns normal `200`
  - POST and PUT do not succeed as public route methods (expected non-2xx, typically 404/405 depending gateway handling)

## 14. Execution Notes for Maintainability

- Run tests in order from low-mutation to high-mutation:
  1. Preflight + read tests
  2. Flash-sale tests
  3. Hold create/get/confirm/release
  4. Seat status transitions
  5. Expire-holds + side effects
  6. Concurrency + Kong regression
- Use fresh idempotency keys per run to keep tests repeatable.
- Record captured hold IDs to avoid cross-test ambiguity.
- For tests requiring precise seat states, include explicit setup/reset actions before execution.

## 15. Optional Setup and Cleanup SQL Snippets

Use only when needed to make manual runs deterministic.

Create one overdue HELD hold for maintenance tests:

```sql
update public.seat_holds
set created_at = now() - interval '10 minutes',
    hold_expires_at = now() - interval '5 minutes',
    status = 'HELD',
    expired_at = null,
    released_at = null,
    confirmed_at = null,
    release_reason = null
where hold_id = '<TARGET_HOLD_ID>';
```

Verify setup before calling expire endpoint:

```sql
select hold_id, status, created_at, hold_expires_at
from public.seat_holds
where hold_id = '<TARGET_HOLD_ID>';
```

Expected verification:

- `status = 'HELD'`
- `created_at < hold_expires_at`
- `hold_expires_at <= now()`

Ensure flash-sale fixture exists for TC-INV-020:

```sql
insert into public.flash_sales (
  flash_sale_id,
  event_id,
  discount_percentage,
  escalation_percentage,
  starts_at,
  ends_at,
  status,
  launched_by_user_id,
  config,
  ended_at
)
values (
  '70000000-0000-0000-0000-000000000001'::uuid,
  '10000000-0000-0000-0000-000000000301'::uuid,
  50.00,
  20.00,
  now() - interval '2 hours',
  now() - interval '1 hours',
  'ENDED'::flash_sale_status_t,
  '00000000-0000-0000-0000-000000000004'::uuid,
  '{"source":"tc-inv-020-fixture"}'::jsonb,
  now() - interval '1 hours'
)
on conflict (flash_sale_id) do nothing;

select flash_sale_id, event_id, status
from public.flash_sales
where flash_sale_id = '70000000-0000-0000-0000-000000000001';
```

Reset a seat to AVAILABLE for transition tests:

```sql
update public.seats
set status = 'AVAILABLE', sold_at = null
where seat_id = '30000000-0000-0000-0000-000000000042';
```

## 16. Coverage Summary

This suite covers:

- All inventory microservice endpoints exposed in Swagger
- Happy path and negative validation path for each endpoint
- Idempotency behavior for hold creation and repeated state changes
- Concurrency behavior for seat contention
- Event side effects (`seat.released`, `category.sold_out`)
- Kong route regression for public read-only exposure

## 17. Setup and Scenario Traceability Matrix

### 17.1 Setup.md contract mapping

| Setup contract                                                                    | Inventory-suite interpretation                                                                                         | Covered by                         |
| :-------------------------------------------------------------------------------- | :--------------------------------------------------------------------------------------------------------------------- | :--------------------------------- |
| UI traffic goes through Kong; internal service-to-service bypasses Kong           | Mutation tests run on direct service Swagger (`5003`), while Kong tests verify public read-only behavior               | TC-INV-001, TC-INV-002, TC-INV-095 |
| Service build order is `/health` then GET then POST then PUT then error responses | Test sections follow the same progression for predictable execution and triage                                         | Sections 4-13                      |
| Atomic services own their own datastores                                          | Inventory state is validated via Inventory API calls and side effects; SQL is limited to deterministic preflight/setup | TC-INV-004, TC-INV-005, Section 15 |
| Composite services depend on healthy atomics                                      | Health and OpenAPI contract checks are prerequisites before mutating flows                                             | TC-INV-001, TC-INV-002, TC-INV-003 |

### 17.2 Scenarios.md step-to-test mapping

| Scenario step contract                              | Inventory behavior to verify                                                              | Mapped test IDs                                            |
| :-------------------------------------------------- | :---------------------------------------------------------------------------------------- | :--------------------------------------------------------- |
| Step 1A reservation pre-check                       | Availability returns `AVAILABLE`/`SOLD_OUT` with category normalization and validation    | TC-INV-010, TC-INV-011, TC-INV-012, TC-INV-013, TC-INV-014 |
| Step 1A reserve hold path                           | Public hold creation supports idempotency and conflict protections                        | TC-INV-030 through TC-INV-039                              |
| Step 1A payment success path                        | Confirm transitions `HELD -> CONFIRMED` and `seat -> SOLD`; confirm remains idempotent    | TC-INV-050 through TC-INV-054                              |
| Step 1B sold-out branch to waitlist join            | Inventory explicitly reports sold-out state and no-seat conflicts                         | TC-INV-011, TC-INV-038                                     |
| Step 1C seat release and protected waitlist handoff | Waitlist-origin hold and release behaviors preserve queue protection (`PENDING_WAITLIST`) | TC-INV-033, TC-INV-060, TC-INV-065                         |
| Step 1D scheduler expiry flow                       | Expire-holds operation expires overdue holds and emits timeout release events             | TC-INV-080 through TC-INV-083, TC-INV-093                  |
| Step 1D no-waitlist branch                          | Seat can move from `PENDING_WAITLIST -> AVAILABLE` when no candidate exists               | TC-INV-079                                                 |
| Step 2A flash sale launch                           | Flash-sale flag can be activated with payload validation                                  | TC-INV-020 through TC-INV-025                              |
| Step 2B sold-out escalation trigger                 | Final seat confirmation during flash sale emits `category.sold_out`                       | TC-INV-094                                                 |
| Step 2C flash sale end                              | Flash-sale flag can be deactivated cleanly                                                | TC-INV-021                                                 |
| Scenario 3 cancellation compensation                | Cancellation release reason is accepted and triggers release semantics                    | TC-INV-066, TC-INV-092                                     |
