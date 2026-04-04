# Expiry Scheduler Manual Swagger Test Suite

## 0. Test Design Reasoning

### 0.1 What is being tested

- Expiry behavior for stale `HELD` seat holds.
- Contract correctness of `POST /inventory/maintenance/expire-holds`, which is the endpoint called by Expiry Scheduler Service.
- Runtime behavior of Expiry Scheduler worker loop (success interval, failure retry, jitter, and shutdown).
- State and event side effects required by Scenario Step 1D (timeout flow).

### 0.2 Inputs, outputs, dependencies, and failure risks

- Inputs: Swagger request body to expire-holds endpoint, hold creation payloads, scheduler environment variables, and controlled SQL preconditions.
- Outputs: HTTP status/body, hold and seat state transitions, publish-failure signals, and scheduler logs.
- Dependencies: Inventory Service API, Supabase RPC function `inventory_expire_holds`, RabbitMQ publication path, and Docker Compose worker runtime.
- Main risks covered: missed expiries, wrong seat target status after expiry, silent event publication failures, duplicate expiry processing, and scheduler retry drift.

### 0.3 Test type and coverage intent

- Primary type: manual integration tests through Swagger for Inventory Service.
- Secondary type: manual worker-runtime checks through Docker Compose logs for Expiry Scheduler Service.
- Coverage intent: deterministic happy paths first, then edge/no-op behavior, then failure/retry and operational controls.

## 1. Scope

This suite focuses on the expiry scheduler workflow used in Scenario 1 Step 1D.

In scope:

- Swagger contract and behavior of `POST /inventory/maintenance/expire-holds`.
- Deterministic hold expiry outcomes for both public and waitlist-origin holds.
- Side-effect validation in Supabase (`seat_holds`, `seats`) and publish-failure signaling for RabbitMQ path.
- Scheduler runtime behavior via logs and environment overrides.

Out of scope:

- End-to-end UI assertions for Booking Status and emails (covered by scenario-level tests).
- Waitlist service API correctness itself (only observed as downstream dependency).

## 2. Environment and Entry Points

- Inventory Swagger UI (direct): `http://localhost:5003/inventory/docs/`
- Inventory OpenAPI JSON: `http://localhost:5003/inventory/openapi.json`
- Expire endpoint under test: `POST /inventory/maintenance/expire-holds`
- Scheduler container logs: `docker compose logs expiry-scheduler-service --tail 200`
- Scheduler container restart: `docker compose restart expiry-scheduler-service`

Important:

- Run mutation/maintenance tests on direct Inventory Swagger (`5003`) rather than Kong (`8000`), because Kong route for `/inventory` remains read-only in this project setup.
- Expiry Scheduler has no Swagger surface; it is validated by observing calls/results against the Inventory maintenance endpoint and worker logs.

## 3. Source Context Used To Craft Inputs

### 3.1 Setup and Scenario constraints

- Setup requires schedulers to run as separate worker processes (no in-service scheduler threads).
- Scenario Step 1D requires Expiry Scheduler to call Inventory maintenance endpoint and preserve Inventory datastore ownership.
- Timeout flow requires `seat.released` publication with `reason: PAYMENT_TIMEOUT`.

### 3.2 Supabase project context (project `cpxcpvcfbohvpiubbujg`)

- Migrations observed:
  - `20260401100519 init_ticketblitz_core_schema`
  - `20260401101813 seed_ticketblitz_scenarios_1_3`
  - `20260402045843 add_missing_inventory_rpc_functions_20260402`
  - `20260402082425 noop_check`
  - `20260402082441 noop_revert`
  - `20260402095203 fan_signup_autoconfirm_v2`
- Table cardinalities observed:
  - `events=2`, `seats=11`, `seat_holds=24`, `waitlist_entries=7`, `integration_events_2026_04=32`.
- Schema constraints used in assertions:
  - `seat_holds.status`: `HELD | CONFIRMED | EXPIRED | RELEASED`
  - `seat_holds.release_reason`: `PAYMENT_TIMEOUT | CANCELLATION | MANUAL_RELEASE | SYSTEM_CLEANUP`
  - `waitlist_entries.status`: `WAITING | HOLD_OFFERED | CONFIRMED | EXPIRED | CANCELLED`
- Security advisor snapshot:
  - `RLS Enabled No Policy` lints are present on multiple public tables.
  - Auth warning observed: leaked password protection disabled.
  - Remediation references:
    - https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy
    - https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection

### 3.3 Context7 references applied

- Flasgger (`/flasgger/flasgger`): Swagger/OpenAPI route behavior and UI contract verification patterns.
- Requests (`/psf/requests`): retry adapter and timeout best practices used by scheduler runtime assertions.
- Flask (`/pallets/flask`): explicit error-handler behavior and status-code verification patterns.

## 4. Global Reusable Test Data

### 4.1 IDs

- `EVENT_ID_MAIN = 10000000-0000-0000-0000-000000000301` (EVT-301)
- `USER_ID_BRANDON = 00000000-0000-0000-0000-000000000001`
- `USER_ID_BOONE = 00000000-0000-0000-0000-000000000002`
- `CATEGORY_PEN = PEN`
- `CATEGORY_CAT1 = CAT1`
- `SEAT_ID_PEN_P01 = 30000000-0000-0000-0000-000000000031`
- `SEAT_ID_CAT1_D13 = 30000000-0000-0000-0000-000000000013`
- `INVALID_UUID = not-a-uuid`

### 4.2 Reusable Swagger payloads

`CREATE_HOLD_PUBLIC_PEN`

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "00000000-0000-0000-0000-000000000001",
  "seatCategory": "PEN",
  "qty": 1,
  "fromWaitlist": false,
  "idempotencyKey": "exp-swagger-public-001"
}
```

`CREATE_HOLD_WAITLIST_CAT1`

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "00000000-0000-0000-0000-000000000002",
  "seatCategory": "CAT1",
  "qty": 1,
  "fromWaitlist": true,
  "idempotencyKey": "exp-swagger-waitlist-001"
}
```

### 4.3 Runtime variables captured during execution

- `HOLD_PUBLIC_A`
- `HOLD_WAITLIST_A`
- `HOLD_PUBLIC_B`
- `HOLD_WAITLIST_B`

## 5. Preflight Cases

### TC-EXP-001 should_load_inventory_swagger_ui

- Endpoint: `GET /inventory/docs/`
- Input: none
- Expected HTTP status: `200`
- Expected output: Swagger UI page renders successfully.

### TC-EXP-002 should_expose_expire_holds_operation_in_openapi

- Endpoint: `GET /inventory/openapi.json`
- Input: none
- Expected HTTP status: `200`
- Expected output:
  - `paths` contains `/inventory/maintenance/expire-holds`
  - `post` response schema includes `count`, `expiredHolds`, `publishFailures`, `publishFailureHoldIDs`

### TC-EXP-003 should_report_inventory_health_before_expiry_tests

- Endpoint: `GET /health`
- Input: none
- Expected HTTP status: `200`
- Expected output includes:
  - `status = "ok"`
  - `service = "inventory-service"`
  - `supabaseConfigured = true`

### TC-EXP-004 should_have_inventory_expire_holds_rpc_available

- Type: DB preflight (outside Swagger)
- SQL input:

```sql
select proname
from pg_proc
where proname = 'inventory_expire_holds';
```

- Expected output: exactly one row with `proname = inventory_expire_holds`.

### TC-EXP-005 should_confirm_scheduler_container_running

- Type: runtime preflight
- Command input:

```bash
docker compose ps expiry-scheduler-service
```

- Expected output: service state is `Up`.

## 6. Deterministic Data Preparation Cases

### TC-EXP-010 should_reset_public_pen_seat_for_hold_creation

- Type: DB setup (outside Swagger)
- SQL input:

```sql
update public.seat_holds
set status = 'RELEASED',
    release_reason = 'MANUAL_RELEASE',
    released_at = now()
where seat_id = '30000000-0000-0000-0000-000000000031'
  and status = 'HELD';

update public.seats
set status = 'AVAILABLE', sold_at = null
where seat_id = '30000000-0000-0000-0000-000000000031';
```

- Expected output: setup SQL succeeds with no errors.

### TC-EXP-011 should_reset_cat1_waitlist_seat_for_waitlist_hold_creation

- Type: DB setup (outside Swagger)
- SQL input:

```sql
update public.seat_holds
set status = 'RELEASED',
    release_reason = 'MANUAL_RELEASE',
    released_at = now()
where seat_id = '30000000-0000-0000-0000-000000000013'
  and status = 'HELD';

update public.seats
set status = 'PENDING_WAITLIST', sold_at = null
where seat_id = '30000000-0000-0000-0000-000000000013';
```

- Expected output: setup SQL succeeds with no errors.

## 7. Expire-Holds API Cases (Swagger-First)

### TC-EXP-020 should_return_zero_when_no_held_rows_are_expired

- Endpoint: `POST /inventory/maintenance/expire-holds`
- Input body:

```json
{}
```

- Expected HTTP status: `200`
- Expected output:
  - `count = 0`
  - `expiredHolds = []`
  - `publishFailures = 0`

### TC-EXP-021 should_create_public_hold_for_expiry_candidate

- Endpoint: `POST /inventory/hold`
- Input body: `CREATE_HOLD_PUBLIC_PEN` (new unique `idempotencyKey`)
- Expected HTTP status: `201`
- Expected output:
  - `holdStatus = HELD`
  - `seatID = 30000000-0000-0000-0000-000000000031`
  - capture `holdID` into `HOLD_PUBLIC_A`

### TC-EXP-022 should_force_public_hold_to_past_deadline

- Type: DB setup (outside Swagger)
- SQL input:

```sql
update public.seat_holds
set hold_expires_at = now() - interval '2 minutes'
where hold_id = '{{HOLD_PUBLIC_A}}'
  and status = 'HELD';
```

- Expected output: one row updated.

### TC-EXP-023 should_expire_public_hold_and_release_seat_to_available

- Endpoint: `POST /inventory/maintenance/expire-holds`
- Input body:

```json
{}
```

- Expected HTTP status: `200`
- Expected output:
  - `count >= 1`
  - `publishFailures = 0`
  - `expiredHolds` contains object with `holdID = {{HOLD_PUBLIC_A}}`
  - `expiredHolds` item has `seatCategory = PEN`

- State verification SQL:

```sql
select status, release_reason, expired_at
from public.seat_holds
where hold_id = '{{HOLD_PUBLIC_A}}';

select status
from public.seats
where seat_id = '30000000-0000-0000-0000-000000000031';
```

- Expected SQL result:
  - hold row: `status = EXPIRED`, `release_reason = PAYMENT_TIMEOUT`, `expired_at is not null`
  - seat row: `status = AVAILABLE`

### TC-EXP-024 should_create_waitlist_hold_for_expiry_candidate

- Endpoint: `POST /inventory/hold`
- Input body: `CREATE_HOLD_WAITLIST_CAT1` (new unique `idempotencyKey`)
- Expected HTTP status: `201`
- Expected output:
  - `holdStatus = HELD`
  - `seatID = 30000000-0000-0000-0000-000000000013`
  - `fromWaitlist = true`
  - capture `holdID` into `HOLD_WAITLIST_A`

### TC-EXP-025 should_force_waitlist_hold_to_past_deadline

- Type: DB setup (outside Swagger)
- SQL input:

```sql
update public.seat_holds
set hold_expires_at = now() - interval '2 minutes'
where hold_id = '{{HOLD_WAITLIST_A}}'
  and status = 'HELD';
```

- Expected output: one row updated.

### TC-EXP-026 should_expire_waitlist_hold_and_keep_seat_pending_waitlist

- Endpoint: `POST /inventory/maintenance/expire-holds`
- Input body:

```json
{}
```

- Expected HTTP status: `200`
- Expected output:
  - `count >= 1`
  - `publishFailures = 0`
  - `expiredHolds` contains `holdID = {{HOLD_WAITLIST_A}}`
  - `expiredHolds` item has `seatCategory = CAT1`

- State verification SQL:

```sql
select status, release_reason, expired_at
from public.seat_holds
where hold_id = '{{HOLD_WAITLIST_A}}';

select status
from public.seats
where seat_id = '30000000-0000-0000-0000-000000000013';
```

- Expected SQL result:
  - hold row: `EXPIRED`, `PAYMENT_TIMEOUT`, `expired_at is not null`
  - seat row: `PENDING_WAITLIST`

### TC-EXP-027 should_handle_batch_with_multiple_expired_holds_in_single_run

- Precondition:
  - Create two new HELD rows: one public PEN hold and one waitlist CAT1 hold.
  - Force both `hold_expires_at` into the past.

- Endpoint: `POST /inventory/maintenance/expire-holds`
- Input body:

```json
{}
```

- Expected HTTP status: `200`
- Expected output:
  - `count >= 2`
  - `publishFailures = 0` (if RabbitMQ healthy)
  - both hold IDs present in `expiredHolds`

### TC-EXP-028 should_be_idempotent_when_run_again_immediately

- Endpoint: `POST /inventory/maintenance/expire-holds` (run immediately after TC-EXP-027)
- Input body:

```json
{}
```

- Expected HTTP status: `200`
- Expected output:
  - `count = 0`
  - `expiredHolds = []`
  - `publishFailures = 0`

### TC-EXP-029 should_ignore_arbitrary_request_body_and_still_execute

- Endpoint: `POST /inventory/maintenance/expire-holds`
- Input body:

```json
{
  "unexpected": "field",
  "limit": 10
}
```

- Expected HTTP status: `200`
- Expected output: normal expire-holds response shape (`count`, `expiredHolds`, `publishFailures`).

## 8. Side-Effect and Publish-Integrity Cases

### TC-EXP-040 should_report_successful_publish_path_when_broker_is_healthy

- Precondition: RabbitMQ is running and at least one overdue HELD row exists.
- Endpoint: `POST /inventory/maintenance/expire-holds`
- Input body:

```json
{}
```

- Expected HTTP status: `200`
- Expected output:
  - `count >= 1`
  - `publishFailures = 0`
  - `expiredHolds` contains the expired hold IDs for this run

- Evidence note:
  - In current implementation, inventory publishes directly to RabbitMQ and does not persist publish records in `integration_events` for this endpoint path.
  - Therefore, publish-path success is asserted through `publishFailures = 0` plus healthy broker state.

### TC-EXP-041 should_surface_publish_failures_in_response_when_broker_unavailable

- Precondition:
  - Stop RabbitMQ container.
  - Ensure at least one HELD row is overdue before invoking expire-holds.

- Commands:

```bash
docker compose stop rabbitmq
```

- Endpoint: `POST /inventory/maintenance/expire-holds`
- Input body:

```json
{}
```

- Expected HTTP status: `200`
- Expected output:
  - `count >= 1`
  - `publishFailures >= 1`
  - `publishFailureHoldIDs` exists and contains expired hold IDs for failed publishes

- Recovery command:

```bash
docker compose start rabbitmq
```

### TC-EXP-042 should_recover_publish_failures_after_broker_is_restored

- Precondition:
  - Execute TC-EXP-041 first to observe `publishFailures >= 1`.
  - Restart RabbitMQ.
  - Prepare at least one new overdue HELD row.

- Endpoint: `POST /inventory/maintenance/expire-holds`
- Input body:

```json
{}
```

- Expected HTTP status: `200`
- Expected output:
  - `count >= 1`
  - `publishFailures = 0`
  - response no longer includes failed publish IDs from this run

## 9. Scheduler Worker Runtime Cases

### TC-EXP-050 should_call_expire_endpoint_periodically_when_healthy

- Precondition:
  - Start scheduler with short interval for observability.

- Command input:

```bash
EXPIRY_INTERVAL_SECONDS=5 docker compose up -d expiry-scheduler-service
sleep 15
docker compose logs expiry-scheduler-service --tail 200
```

- Expected output in logs:
  - startup line with interval and maintenance URL
  - repeated success lines similar to `Expiry batch completed count=...`

### TC-EXP-051 should_treat_publish_failures_as_scheduler_failure_and_retry

- Precondition:
  - RabbitMQ stopped
  - at least one overdue HELD row exists

- Commands:

```bash
docker compose stop rabbitmq
sleep 8
docker compose logs expiry-scheduler-service --tail 200
```

- Expected output in logs:
  - warning line containing `publishFailures=` and `publishFailureHoldIDs=`
  - scheduler keeps running and retries based on `EXPIRY_ERROR_RETRY_DELAY_SECONDS` plus jitter

- Recovery:

```bash
docker compose start rabbitmq
```

### TC-EXP-052 should_retry_when_inventory_path_returns_non_200

- Precondition:
  - Restart scheduler with bad maintenance path.

- Command input:

```bash
INVENTORY_EXPIRE_HOLDS_PATH=/inventory/maintenance/does-not-exist docker compose up -d expiry-scheduler-service
sleep 8
docker compose logs expiry-scheduler-service --tail 200
```

- Expected output in logs:
  - warning containing `returned status=404`
  - repeated retries using error-retry delay path

### TC-EXP-053 should_fail_fast_on_invalid_inventory_url_configuration

- Command input:

```bash
INVENTORY_SERVICE_URL=not-a-url docker compose up expiry-scheduler-service
```

- Expected output:
  - process exits non-zero quickly
  - log contains `Invalid scheduler configuration`

### TC-EXP-054 should_shutdown_gracefully_on_service_stop

- Command input:

```bash
docker compose stop expiry-scheduler-service
docker compose logs expiry-scheduler-service --tail 80
```

- Expected output in logs:
  - signal/shutdown request line
  - final stopped line for service name

## 10. Concurrency and Race-Proofing Cases

### TC-EXP-060 should_not_double_expire_same_hold_under_parallel_maintenance_calls

- Precondition: create one overdue HELD row.
- Action: execute two `POST /inventory/maintenance/expire-holds` requests in parallel (two Swagger tabs or one Swagger call + one curl).
- Expected output:
  - only one call returns that hold in `expiredHolds`
  - the other call returns `count=0` for that hold
  - final hold state remains `EXPIRED` exactly once

### TC-EXP-061 should_not_reprocess_already_expired_or_released_holds

- Precondition:
  - choose hold already in `EXPIRED` or `RELEASED` state.
- Endpoint: `POST /inventory/maintenance/expire-holds`
- Expected output:
  - selected hold ID does not appear in response `expiredHolds`
  - no additional transition is applied to that hold

## 11. Negative and Validation Cases Around Inputs To Supporting APIs

### TC-EXP-070 should_reject_invalid_qty_when_preparing_hold_candidate

- Endpoint: `POST /inventory/hold`
- Input body:

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "00000000-0000-0000-0000-000000000001",
  "seatCategory": "PEN",
  "qty": 2,
  "fromWaitlist": false,
  "idempotencyKey": "exp-invalid-qty-001"
}
```

- Expected HTTP status: `400`
- Expected output:

```json
{
  "error": "Only qty=1 is supported"
}
```

### TC-EXP-071 should_reject_non_boolean_fromWaitlist_when_preparing_hold_candidate

- Endpoint: `POST /inventory/hold`
- Input body:

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "00000000-0000-0000-0000-000000000001",
  "seatCategory": "PEN",
  "qty": 1,
  "fromWaitlist": "not-bool",
  "idempotencyKey": "exp-invalid-bool-001"
}
```

- Expected HTTP status: `400`
- Expected output contains error for `fromWaitlist must be a boolean`.

## 12. Traceability Matrix to Scenario Step 1D

| Scenario Step 1D Requirement | Covered Test Cases |
| :-- | :-- |
| Scheduler calls Inventory maintenance endpoint periodically | TC-EXP-050 |
| Inventory owns expiry state transitions | TC-EXP-023, TC-EXP-026, TC-EXP-061 |
| Hold expires to `EXPIRED` with `PAYMENT_TIMEOUT` | TC-EXP-023, TC-EXP-026 |
| Seat target status depends on hold origin (`AVAILABLE` vs `PENDING_WAITLIST`) | TC-EXP-023, TC-EXP-026 |
| `seat.released` publication path reported through publish-failure contract | TC-EXP-040, TC-EXP-041, TC-EXP-042 |
| Publication failures surfaced and retried by scheduler | TC-EXP-041, TC-EXP-051 |
| No duplicate processing under repeated/parallel runs | TC-EXP-028, TC-EXP-060 |

## 13. Cleanup Checklist

After test execution:

1. Restore RabbitMQ if stopped.
2. Restore scheduler env overrides to defaults.
3. Ensure no leftover HELD test rows on seats used in this suite.
4. Keep evidence artifacts:
   - Swagger screenshots for key responses
   - scheduler log excerpts
   - SQL result snippets for hold/seat/event verification

Suggested cleanup SQL:

```sql
update public.seat_holds
set status = 'RELEASED',
    release_reason = 'MANUAL_RELEASE',
    released_at = now()
where status = 'HELD'
  and idempotency_key like 'exp-%';

update public.seats
set status = 'AVAILABLE', sold_at = null
where seat_id = '30000000-0000-0000-0000-000000000031';

update public.seats
set status = 'PENDING_WAITLIST', sold_at = null
where seat_id = '30000000-0000-0000-0000-000000000013';
```
