# Waitlist Promotion Orchestrator Manual Swagger Test Suite

## 0) Test Design Reasoning

### 0.1 What is being tested
- Integration behavior of the Waitlist Promotion Orchestrator worker, triggered by seat release events.
- Contract correctness of dependent Swagger APIs that the worker calls:
  - Inventory Service
  - Waitlist Service
  - User Service
- Observable side effects in Supabase state and integration event outbox records.

### 0.2 Expected behavior (from project setup and scenarios)
- On seat release, the worker selects the next waiting user for the same event and category.
- It creates a waitlist hold, marks waitlist entry as HOLD_OFFERED, and emits a SEAT_AVAILABLE notification event.
- On PAYMENT_TIMEOUT release with expiredHoldID, it expires the previous offered waitlist entry, emits HOLD_EXPIRED, then promotes next waiting user if available.
- If no waiting user exists, it returns the seat to AVAILABLE.

### 0.3 Inputs, outputs, dependencies
- Inputs:
  - Swagger requests to Inventory and Waitlist endpoints
  - SQL setup commands in Supabase
- Outputs:
  - HTTP status codes and response bodies
  - Waitlist status transitions
  - Seat and hold state changes
  - Outbox rows in integration_events_2026_04
- Dependencies:
  - RabbitMQ routing and worker container up
  - Supabase project cpxcpvcfbohvpiubbujg
  - Internal auth headers for protected Waitlist and User routes

### 0.4 What could go wrong
- Missing internal auth header causing 401 on protected waitlist endpoints.
- Hold/seat state mismatch causing hold creation conflicts.
- Existing active waitlist rows causing unique constraint conflicts.
- Asynchronous delay causing false negatives if assertions are made too early.

## 1) Sources Used

### 1.1 Project docs reviewed
- docs/Setup.md
- docs/Scenarios.md (Step 1C and 1D behavior and ownership rules)

### 1.2 Supabase live context used
- Project URL: https://cpxcpvcfbohvpiubbujg.supabase.co
- Event fixtures present:
  - EVT-301: 10000000-0000-0000-0000-000000000301
  - EVT-401-MANUAL: 10000000-0000-0000-0000-000000000401
- Category fixtures present for EVT-301:
  - CAT1: 20000000-0000-0000-0000-000000000101
  - CAT2: 20000000-0000-0000-0000-000000000102
  - PEN: 20000000-0000-0000-0000-000000000103
- Enum values confirmed:
  - seat_status_t: AVAILABLE, PENDING_WAITLIST, HELD, SOLD
  - waitlist_status_t: WAITING, HOLD_OFFERED, CONFIRMED, EXPIRED, CANCELLED
  - hold_status_t: HELD, CONFIRMED, EXPIRED, RELEASED
  - hold_release_reason_t: PAYMENT_TIMEOUT, CANCELLATION, MANUAL_RELEASE, SYSTEM_CLEANUP

### 1.3 Context7 references used
- OpenAPI 3.0.3 spec reference:
  - Path parameters in path must be required.
  - Responses object must explicitly define status-code response contracts.
- Supabase docs reference:
  - SQL editor and upsert guidance for deterministic setup.

## 2) Test Surfaces and Access

### 2.1 Swagger URLs
- Inventory Swagger UI: http://localhost:5003/inventory/docs/
- Waitlist OpenAPI JSON: http://localhost:5005/openapi.json
- Waitlist Swagger UI: http://localhost:5005/docs
- User service health: http://localhost:5002/health

### 2.2 Required internal auth header
Use this header for protected Waitlist and User endpoints:

- Header name: X-Internal-Token
- Header value: ticketblitz-internal-token

### 2.3 Worker observability
Use logs while executing test cases:

```bash
docker compose logs -f waitlist-promotion-orchestrator --tail 200
```

## 3) Mock Data Inserted Into Supabase

The following fixture rows were inserted on 2026-04-04 and are idempotent for reruns.

### 3.1 Inserted fixture IDs

- Users:
  - 9aa10000-0000-0000-0000-000000000001 (wpo.qa1@ticketblitz.com)
  - 9aa10000-0000-0000-0000-000000000002 (wpo.qa2@ticketblitz.com)
  - 9aa10000-0000-0000-0000-000000000003 (wpo.qa3@ticketblitz.com)
- Seats:
  - 3aa00000-0000-0000-0000-000000000101 (CAT1, WPO-CAT1-A, PENDING_WAITLIST)
  - 3aa00000-0000-0000-0000-000000000102 (CAT1, WPO-CAT1-B, PENDING_WAITLIST)
  - 3aa00000-0000-0000-0000-000000000103 (PEN, WPO-PEN-A, PENDING_WAITLIST)
  - 3aa00000-0000-0000-0000-000000000104 (CAT2, WPO-CAT2-A, PENDING_WAITLIST)
- Waitlist entries:
  - 9bb20000-0000-0000-0000-000000000001 (CAT1, QA User 1, WAITING)
  - 9bb20000-0000-0000-0000-000000000002 (CAT1, QA User 2, WAITING)
  - 9bb20000-0000-0000-0000-000000000003 (PEN, QA User 3, WAITING)

### 3.2 Re-runnable SQL seed script

```sql
insert into public.users (user_id, full_name, email, phone, metadata, deleted_at)
values
  ('9aa10000-0000-0000-0000-000000000001', 'WPO QA User 1', 'wpo.qa1@ticketblitz.com', null, '{"fixture":"wpo_manual_swagger"}'::jsonb, null),
  ('9aa10000-0000-0000-0000-000000000002', 'WPO QA User 2', 'wpo.qa2@ticketblitz.com', null, '{"fixture":"wpo_manual_swagger"}'::jsonb, null),
  ('9aa10000-0000-0000-0000-000000000003', 'WPO QA User 3', 'wpo.qa3@ticketblitz.com', null, '{"fixture":"wpo_manual_swagger"}'::jsonb, null)
on conflict (user_id) do update
set full_name = excluded.full_name,
    email = excluded.email,
    phone = excluded.phone,
    metadata = excluded.metadata,
    deleted_at = null,
    updated_at = now();

insert into public.seats (seat_id, event_id, category_id, seat_number, status, sold_at, metadata)
values
  ('3aa00000-0000-0000-0000-000000000101', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000101', 'WPO-CAT1-A', 'PENDING_WAITLIST', null, '{"fixture":"wpo_manual_swagger"}'::jsonb),
  ('3aa00000-0000-0000-0000-000000000102', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000101', 'WPO-CAT1-B', 'PENDING_WAITLIST', null, '{"fixture":"wpo_manual_swagger"}'::jsonb),
  ('3aa00000-0000-0000-0000-000000000103', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000103', 'WPO-PEN-A', 'PENDING_WAITLIST', null, '{"fixture":"wpo_manual_swagger"}'::jsonb),
  ('3aa00000-0000-0000-0000-000000000104', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000102', 'WPO-CAT2-A', 'PENDING_WAITLIST', null, '{"fixture":"wpo_manual_swagger"}'::jsonb)
on conflict (seat_id) do update
set event_id = excluded.event_id,
    category_id = excluded.category_id,
    seat_number = excluded.seat_number,
    status = excluded.status,
    sold_at = null,
    metadata = excluded.metadata,
    updated_at = now();

insert into public.waitlist_entries (
  waitlist_id,
  event_id,
  category_id,
  user_id,
  hold_id,
  status,
  joined_at,
  offered_at,
  confirmed_at,
  expired_at,
  priority_score,
  source,
  metadata
)
values
  ('9bb20000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000101', '9aa10000-0000-0000-0000-000000000001', null, 'WAITING', now() - interval '30 minutes', null, null, null, 10, 'MANUAL_WPO', '{"fixture":"wpo_manual_swagger","order":1}'::jsonb),
  ('9bb20000-0000-0000-0000-000000000002', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000101', '9aa10000-0000-0000-0000-000000000002', null, 'WAITING', now() - interval '20 minutes', null, null, null, 9, 'MANUAL_WPO', '{"fixture":"wpo_manual_swagger","order":2}'::jsonb),
  ('9bb20000-0000-0000-0000-000000000003', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000103', '9aa10000-0000-0000-0000-000000000003', null, 'WAITING', now() - interval '10 minutes', null, null, null, 8, 'MANUAL_WPO', '{"fixture":"wpo_manual_swagger","order":1}'::jsonb)
on conflict (waitlist_id) do update
set event_id = excluded.event_id,
    category_id = excluded.category_id,
    user_id = excluded.user_id,
    hold_id = null,
    status = 'WAITING',
    joined_at = excluded.joined_at,
    offered_at = null,
    confirmed_at = null,
    expired_at = null,
    priority_score = excluded.priority_score,
    source = excluded.source,
    metadata = excluded.metadata,
    updated_at = now();
```

## 4) Test Execution Conventions

- Run cases in order, because several orchestrator flows are stateful and async.
- Polling timeout for async effects: up to 20 seconds, polling every 2 seconds.
- Capture dynamic variables from responses:
  - HOLD_A, HOLD_B, HOLD_C
  - OFFERED_HOLD_1, OFFERED_HOLD_2

## 5) Manual Test Cases

## 5.1 Preflight and Contract Cases

### WPO-001 should_load_required_service_docs_and_health_endpoints

#### Input
1. GET http://localhost:5003/health
2. GET http://localhost:5005/health
3. GET http://localhost:5002/health
4. GET http://localhost:5003/inventory/openapi.json
5. GET http://localhost:5005/openapi.json

#### Expected Output
- Each health endpoint returns HTTP 200 and status ok.
- Inventory and Waitlist OpenAPI endpoints return HTTP 200 JSON.
- Waitlist OpenAPI includes:
  - GET /waitlist/next
  - GET /waitlist/by-hold/{hold_id}
  - PUT /waitlist/{waitlist_id}/offer
  - PUT /waitlist/{waitlist_id}/expire

### WPO-002 should_require_internal_token_for_protected_waitlist_endpoints

#### Input
1. GET /waitlist/next?eventID=10000000-0000-0000-0000-000000000301&seatCategory=CAT1 without X-Internal-Token
2. Same request with header X-Internal-Token: ticketblitz-internal-token

#### Expected Output
- Step 1: HTTP 401 Unauthorized.
- Step 2: HTTP 200 and a waitlist entry object, or HTTP 404 if no active WAITING rows remain.

### WPO-003 should_confirm_fixture_baseline_before_orchestrator_cases

#### Input
Run SQL:

```sql
select waitlist_id, status, hold_id
from public.waitlist_entries
where waitlist_id in (
  '9bb20000-0000-0000-0000-000000000001',
  '9bb20000-0000-0000-0000-000000000002',
  '9bb20000-0000-0000-0000-000000000003'
)
order by waitlist_id;

select seat_id, status
from public.seats
where seat_id in (
  '3aa00000-0000-0000-0000-000000000101',
  '3aa00000-0000-0000-0000-000000000102',
  '3aa00000-0000-0000-0000-000000000103',
  '3aa00000-0000-0000-0000-000000000104'
)
order by seat_id;
```

#### Expected Output
- Waitlist entries are WAITING with hold_id null.
- All listed seats are PENDING_WAITLIST.

## 5.2 Core Orchestrator Flow Cases

### WPO-101 should_offer_first_waiting_user_when_cat1_seat_released

#### Input
1. Swagger call: POST /inventory/hold

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "9aa10000-0000-0000-0000-000000000001",
  "seatCategory": "CAT1",
  "qty": 1,
  "fromWaitlist": true,
  "idempotencyKey": "wpo-tc-101-seed"
}
```

2. Capture holdID as HOLD_A.
3. Swagger call: PUT /inventory/hold/{HOLD_A}/release

```json
{
  "reason": "MANUAL_RELEASE"
}
```

4. Poll Swagger: GET /waitlist/9bb20000-0000-0000-0000-000000000001 (every 2s, max 20s).
5. Capture resulting holdID as OFFERED_HOLD_1.
6. Swagger call: GET /inventory/hold/{OFFERED_HOLD_1}

#### Expected Output
- Step 1 returns HTTP 201 with holdStatus HELD.
- Step 3 returns HTTP 200 with holdStatus RELEASED.
- Poll result for waitlist 9bb...001 eventually returns:
  - status HOLD_OFFERED
  - holdID not null
- GET /inventory/hold/{OFFERED_HOLD_1} returns:
  - HTTP 200
  - holdStatus HELD
  - fromWaitlist true

#### Side-effect verification SQL
```sql
select event_id, routing_key, payload
from public.integration_events_2026_04
where routing_key = 'notification.send'
  and payload->>'type' = 'SEAT_AVAILABLE'
  and payload->>'holdID' = '{{OFFERED_HOLD_1}}'
order by occurred_at desc
limit 1;
```

Expected:
- One row exists with payload email = wpo.qa1@ticketblitz.com.

### WPO-102 should_expire_old_offer_and_promote_second_waiting_user_on_timeout

#### Input
1. GET /waitlist/9bb20000-0000-0000-0000-000000000001 and capture holdID as OFFERED_HOLD_1.
2. SQL force expiry:

```sql
update public.seat_holds
set hold_expires_at = now() - interval '2 minutes'
where hold_id = '{{OFFERED_HOLD_1}}'
  and status = 'HELD';
```

3. Swagger call: POST /inventory/maintenance/expire-holds with body {}
4. Poll GET /waitlist/9bb20000-0000-0000-0000-000000000001
5. Poll GET /waitlist/9bb20000-0000-0000-0000-000000000002 and capture holdID as OFFERED_HOLD_2

#### Expected Output
- Step 3 returns HTTP 200 with:
  - count >= 1
  - expiredHolds includes OFFERED_HOLD_1
  - publishFailures = 0
- Waitlist 9bb...001 becomes EXPIRED and keeps holdID OFFERED_HOLD_1.
- Waitlist 9bb...002 becomes HOLD_OFFERED with non-null holdID.

#### Side-effect verification SQL
```sql
select routing_key, payload
from public.integration_events_2026_04
where routing_key = 'notification.send'
  and (
    (payload->>'type' = 'HOLD_EXPIRED' and payload->>'holdID' = '{{OFFERED_HOLD_1}}')
    or
    (payload->>'type' = 'SEAT_AVAILABLE' and payload->>'holdID' = '{{OFFERED_HOLD_2}}')
  )
order by occurred_at desc;
```

Expected:
- One HOLD_EXPIRED event for OFFERED_HOLD_1.
- One SEAT_AVAILABLE event for OFFERED_HOLD_2.

### WPO-103 should_set_cat2_seat_available_when_no_waiting_user_exists

#### Input
1. Swagger call: POST /inventory/hold

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "9aa10000-0000-0000-0000-000000000003",
  "seatCategory": "CAT2",
  "qty": 1,
  "fromWaitlist": true,
  "idempotencyKey": "wpo-tc-103-seed"
}
```

2. Capture holdID as HOLD_B.
3. Swagger call: PUT /inventory/hold/{HOLD_B}/release

```json
{
  "reason": "MANUAL_RELEASE"
}
```

4. Poll SQL every 2s (max 20s):

```sql
select status
from public.seats
where seat_id = '3aa00000-0000-0000-0000-000000000104';
```

#### Expected Output
- Step 1 returns HTTP 201 with holdStatus HELD.
- Step 3 returns HTTP 200 with holdStatus RELEASED.
- Seat 3aa...0104 eventually becomes AVAILABLE, confirming orchestrator no-candidate branch.

### WPO-104 should_process_payment_timeout_event_when_hold_not_mapped_in_waitlist

This validates the branch where /waitlist/by-hold returns 404 and worker continues.

#### Input
1. Swagger call: POST /inventory/hold for CAT2 public hold

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "9aa10000-0000-0000-0000-000000000003",
  "seatCategory": "CAT2",
  "qty": 1,
  "fromWaitlist": false,
  "idempotencyKey": "wpo-tc-104-public"
}
```

2. Capture holdID as HOLD_C.
3. Swagger call: PUT /inventory/hold/{HOLD_C}/release

```json
{
  "reason": "PAYMENT_TIMEOUT"
}
```

4. Poll SQL:

```sql
select status
from public.seats
where seat_id = '3aa00000-0000-0000-0000-000000000104';
```

#### Expected Output
- Release returns HTTP 200 and release_reason PAYMENT_TIMEOUT.
- Worker does not fail even if waitlist/by-hold is not found for HOLD_C.
- Seat ends AVAILABLE (no waiting CAT2 user path).

## 5.3 Supporting Contract and Negative Cases

### WPO-201 should_reject_invalid_uuid_inputs_on_waitlist_routes

#### Input
1. GET /waitlist/next?eventID=not-a-uuid&seatCategory=CAT1 with internal token
2. GET /waitlist/by-hold/not-a-uuid with internal token
3. PUT /waitlist/9bb20000-0000-0000-0000-000000000001/offer with body {"holdID": "not-a-uuid"} and internal token

#### Expected Output
- All requests return HTTP 400 with validation error message.

### WPO-202 should_require_hold_id_for_offer_transition

#### Input
PUT /waitlist/9bb20000-0000-0000-0000-000000000003/offer with body {} and internal token

#### Expected Output
- HTTP 400 with message that holdID is required when offering a waitlist entry.

### WPO-203 should_return_same_hold_for_same_inventory_idempotency_key

#### Input
Call POST /inventory/hold twice with identical body:

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "9aa10000-0000-0000-0000-000000000001",
  "seatCategory": "CAT1",
  "qty": 1,
  "fromWaitlist": true,
  "idempotencyKey": "wpo-tc-203-idempotency"
}
```

#### Expected Output
- First response: HTTP 201, hold created.
- Second response: HTTP 200, same holdID returned.

## 6) Coverage Matrix (Orchestrator Logic)

- Promotion path (next waitlist user exists): covered by WPO-101.
- Timeout path (expire previous offer and promote next): covered by WPO-102.
- No-candidate path (set seat AVAILABLE): covered by WPO-103.
- Timeout event with missing waitlist mapping: covered by WPO-104.
- Protected dependency contracts and validation behavior: covered by WPO-002, WPO-201, WPO-202.
- Idempotency prerequisite relied on by orchestrator hold creation behavior: covered by WPO-203.

## 7) Optional Cleanup SQL

```sql
update public.waitlist_entries
set status = 'CANCELLED',
    hold_id = null,
    offered_at = null,
    confirmed_at = null,
    expired_at = null,
    updated_at = now()
where waitlist_id in (
  '9bb20000-0000-0000-0000-000000000001',
  '9bb20000-0000-0000-0000-000000000002',
  '9bb20000-0000-0000-0000-000000000003'
);

update public.seats
set status = 'PENDING_WAITLIST',
    sold_at = null,
    updated_at = now()
where seat_id in (
  '3aa00000-0000-0000-0000-000000000101',
  '3aa00000-0000-0000-0000-000000000102',
  '3aa00000-0000-0000-0000-000000000103',
  '3aa00000-0000-0000-0000-000000000104'
);
```
