# Booking Status Service Manual Swagger Test Suite

## 1) Test Design Summary

### 1.1 Unit/integration under test
- Primary surface: `GET /booking-status/{hold_id}`
- Supporting surfaces: `GET /health`, `GET /openapi.json`, `GET /docs`
- Scope: Manual integration testing via Swagger UI and Kong parity checks

### 1.2 Expected behavior from Scenario 1
From the Scenario 1A/1C/1D flow in project docs:
- `PROCESSING`: asynchronous flow not yet terminal (no transaction yet, payment pending, or ticket not yet available)
- `FAILED_PAYMENT`: latest payment failed and hold is non-terminal
- `EXPIRED`: hold terminal due to `EXPIRED`, or `RELEASED` with timeout semantics
- `CONFIRMED`: payment succeeded, hold confirmed, e-ticket exists

### 1.3 Inputs/outputs and dependencies
- Input: path parameter `hold_id` (UUID, required)
- Output: composite status payload with UI-oriented fields (`uiStatus`, `paymentStatus`, `ticketID`, dependency status)
- Dependencies: inventory-service, payment-service, OutSystems e-ticket service

### 1.4 Key risks this suite targets
- Incorrect state mapping between inventory/payment/e-ticket states
- Unsanitized dependency failure details leaking internals
- Route drift between direct service and Kong gateway
- Environment drift (stale images returning scaffold payloads)

## 2) Sources Used

Project context:
- `docs/Setup.md`
- `docs/Scenarios.md`

Context7 references (latest fetched during this update):
- Swagger UI docs: `/swagger-api/swagger-ui`
  - `supportedSubmitMethods` controls Try it out execution behavior
- OpenAPI spec docs: `/websites/spec_openapis_oas_v3_0_3`
  - Path parameters in `in: path` are required
  - Responses are validated by explicit status code objects and optional `default`

Supabase context source:
- Project ID: `cpxcpvcfbohvpiubbujg`
- Project URL: `https://cpxcpvcfbohvpiubbujg.supabase.co`
- Snapshot date: 2026-04-04

## 3) Environment and Preconditions

1. Build and start services with fresh images:
   - `docker compose up -d --build`
2. Confirm containers healthy:
   - `booking-status-service`, `inventory-service`, `payment-service`, `kong`
3. Confirm Booking Status docs endpoints:
   - `http://localhost:6002/docs`
   - `http://localhost:6002/openapi.json`
4. Confirm runtime dependency contract before status mapping tests:
   - Inventory endpoint `GET /inventory/hold/{hold_id}` must return hold fields like `holdStatus`, `holdExpiry` (not scaffold payload)
   - Payment endpoint `GET /payment/hold/{hold_id}` must return payment fields like `paymentStatus`, `transactionID`

If precondition #4 fails, rebuild/restart impacted atomic services before executing Group B onward.

## 4) Supabase Data Snapshot (Current)

Observed distribution:
- `seat_holds.status`: `HELD=2`, `CONFIRMED=12`, `EXPIRED=6`, `RELEASED=9`
- `transactions.status`: `SUCCEEDED=4`, `FAILED=3`, `REFUND_PENDING=2`, `REFUND_SUCCEEDED=2`, `REFUND_FAILED=3`

Deterministic seeded hold fixtures for manual testing:

| Case label | hold_id | Inventory state | Payment state | Expected uiStatus |
|---|---|---|---|---|
| HOLD_PROCESSING_NO_PAYMENT | `8b200000-0000-0000-0000-000000000001` | `HELD` | none | `PROCESSING` |
| HOLD_FAILED_PAYMENT | `8b200000-0000-0000-0000-000000000002` | `HELD` | `FAILED` | `FAILED_PAYMENT` |
| HOLD_EXPIRED | `8b200000-0000-0000-0000-000000000003` | `EXPIRED` | none | `EXPIRED` |
| HOLD_RELEASED_TIMEOUT | `8b200000-0000-0000-0000-000000000004` | `RELEASED` + `release_reason=PAYMENT_TIMEOUT` | none | `EXPIRED` |
| HOLD_CONFIRMED_SUCCEEDED_NO_TICKET | `8b200000-0000-0000-0000-000000000005` | `CONFIRMED` | `SUCCEEDED` | `PROCESSING` or `CONFIRMED` (if e-ticket exists) |

404 test fixture:
- `00000000-0000-0000-0000-000000009999`

## 5) Reusable Assertions

- `RA-BASE-200`
  - HTTP `200`
  - response includes `holdID`, `uiStatus`, `holdStatus`
- `RA-ERR`
  - error payload shape includes `error`
- `RA-503-SANITIZED`
  - HTTP `503`
  - `details` contains dependency identifier only (no internal URL, stack trace, raw upstream body)

## 6) Manual Swagger Test Cases

### Group A: Contract and Input Validation

| ID | Test name | Swagger input | Expected output |
|---|---|---|---|
| BS-001 | should_return_service_health_when_health_endpoint_called | `GET /health` | HTTP `200`; body includes `status="ok"`, `service="booking-status-service"`, and dependency booleans (`inventoryConfigured`, `paymentConfigured`, `outsystemsConfigured`). |
| BS-002 | should_return_openapi_document_when_openapi_endpoint_called | `GET /openapi.json` | HTTP `200`; `openapi="3.0.3"`; has path `/booking-status/{hold_id}`; path parameter is marked required. |
| BS-003 | should_load_swagger_ui_when_docs_endpoint_called | `GET /docs` | HTTP `200`; Swagger UI page renders and exposes Try it out for GET operation(s). |
| BS-004 | should_return_400_when_hold_id_is_not_uuid | `GET /booking-status/{hold_id}` with `hold_id=not-a-uuid` | HTTP `400`; body: `error` contains `holdID must be a valid UUID`. |
| BS-005 | should_return_404_when_hold_id_not_found | `GET /booking-status/{hold_id}` with `hold_id=00000000-0000-0000-0000-000000009999` | HTTP `404`; body has `error="Hold not found"`. |

### Group B: Core Status Mapping (Deterministic Seeded Data)

| ID | Test name | Swagger input | Expected output |
|---|---|---|---|
| BS-006 | should_return_processing_when_hold_exists_without_transaction | `GET /booking-status/{hold_id}` with `hold_id=8b200000-0000-0000-0000-000000000001` | HTTP `200`; `uiStatus="PROCESSING"`; `holdStatus="HELD"`; `paymentStatus=null`; `dependencyStatus.payment="not_found"`. |
| BS-007 | should_return_failed_payment_when_latest_payment_failed | `GET /booking-status/{hold_id}` with `hold_id=8b200000-0000-0000-0000-000000000002` | HTTP `200`; `uiStatus="FAILED_PAYMENT"`; `holdStatus="HELD"`; `paymentStatus="FAILED"`; `failureReason="card_declined"`; `transactionID` present. |
| BS-008 | should_return_expired_when_hold_status_is_expired | `GET /booking-status/{hold_id}` with `hold_id=8b200000-0000-0000-0000-000000000003` | HTTP `200`; `uiStatus="EXPIRED"`; `holdStatus="EXPIRED"`; `dependencyStatus.payment="skipped"`; `dependencyStatus.eticket="skipped"`. |
| BS-009 | should_return_expired_when_hold_released_for_payment_timeout | `GET /booking-status/{hold_id}` with `hold_id=8b200000-0000-0000-0000-000000000004` | HTTP `200`; `uiStatus="EXPIRED"`; `holdStatus="RELEASED"`; release reason timeout treated as terminal expiry. |
| BS-010 | should_return_processing_or_confirmed_when_hold_confirmed_and_payment_succeeded | `GET /booking-status/{hold_id}` with `hold_id=8b200000-0000-0000-0000-000000000005` | HTTP `200`; `holdStatus="CONFIRMED"`; `paymentStatus="SUCCEEDED"`; if no e-ticket then `uiStatus="PROCESSING"` and `dependencyStatus.eticket` is `not_found`, `unavailable`, or `disabled`; if e-ticket exists then `uiStatus="CONFIRMED"` with non-empty `ticketID`. |

### Group C: Dependency Failure and Sanitization

| ID | Test name | Swagger input | Expected output |
|---|---|---|---|
| BS-011 | should_return_503_when_inventory_dependency_unavailable | Stop inventory service, then call `GET /booking-status/{hold_id}` with `hold_id=8b200000-0000-0000-0000-000000000001` | HTTP `503`; `error` indicates inventory dependency issue; `details.dependency="inventory-service"`; no internal URLs/payload dump. |
| BS-012 | should_return_503_when_payment_dependency_unavailable_for_non_terminal_hold | Keep inventory up, stop payment service, then call `GET /booking-status/{hold_id}` with `hold_id=8b200000-0000-0000-0000-000000000001` | HTTP `503`; `error` indicates payment dependency issue; `details.dependency="payment-service"`; sanitized details only. |
| BS-013 | should_still_return_expired_when_payment_dependency_unavailable_for_terminal_hold | Stop payment service, then call `GET /booking-status/{hold_id}` with `hold_id=8b200000-0000-0000-0000-000000000003` | HTTP `200`; `uiStatus="EXPIRED"`; terminal inventory state should short-circuit payment lookup. |

### Group D: Kong Route Parity

| ID | Test name | Input | Expected output |
|---|---|---|---|
| BS-014 | should_match_service_and_kong_responses_for_failed_payment_case | Compare `http://localhost:6002/booking-status/8b200000-0000-0000-0000-000000000002` and `http://localhost:8000/booking-status/8b200000-0000-0000-0000-000000000002` | Same status code and same semantic values for `uiStatus`, `holdStatus`, `paymentStatus`, `failureReason`. |
| BS-015 | should_match_service_and_kong_responses_for_expired_case | Compare `http://localhost:6002/booking-status/8b200000-0000-0000-0000-000000000003` and `http://localhost:8000/booking-status/8b200000-0000-0000-0000-000000000003` | Same status code and same semantic values for `uiStatus`, `holdStatus`, `dependencyStatus`. |

## 7) SQL Helpers (Read-Only)

Use these queries in Supabase SQL editor to validate fixture drift before test execution.

```sql
select status, count(*)::int as count
from public.seat_holds
group by status
order by status;
```

```sql
select status, count(*)::int as count
from public.transactions
group by status
order by status;
```

```sql
select
  h.hold_id,
  h.status as hold_status,
  h.release_reason,
  h.hold_expires_at,
  h.confirmed_at,
  h.released_at,
  h.expired_at,
  h.amount,
  h.currency,
  s.seat_number,
  coalesce(t.status::text, 'NONE') as payment_status,
  t.failure_reason
from public.seat_holds h
left join lateral (
  select tx.status, tx.failure_reason, tx.created_at
  from public.transactions tx
  where tx.hold_id = h.hold_id
  order by tx.created_at desc
  limit 1
) t on true
left join public.seats s on s.seat_id = h.seat_id
where h.hold_id in (
  '8b200000-0000-0000-0000-000000000001',
  '8b200000-0000-0000-0000-000000000002',
  '8b200000-0000-0000-0000-000000000003',
  '8b200000-0000-0000-0000-000000000004',
  '8b200000-0000-0000-0000-000000000005'
)
order by h.hold_id;
```

## 8) Coverage Matrix

Covered in this suite:
- Public API contract and input validation
- All business UI statuses from Scenario 1 contract
- Deterministic data-backed mapping checks
- Dependency failure handling with sanitization checks
- Service route and Kong route parity

Not covered by this manual suite:
- Load/performance testing
- Automated concurrency/race tests
- OutSystems data authoring (requires external system setup)
