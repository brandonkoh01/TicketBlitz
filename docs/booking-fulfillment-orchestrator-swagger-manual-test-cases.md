# Booking Fulfillment Orchestrator Manual Swagger Test Cases

## 1) Scope and Objective

This suite defines manual, end-to-end test cases for the Booking Fulfillment Orchestrator (BFO).

Important architecture note:

- BFO is a RabbitMQ worker and has no direct Swagger endpoint.
- Swagger is used to trigger upstream/downstream APIs that drive BFO behavior.
- Validation is done through API responses, Supabase state checks, and worker logs.

Primary BFO responsibilities under test:

1. Consume booking.confirmed.
2. Confirm hold in Inventory.
3. Generate e-ticket through Kong route (/eticket/generate).
4. Confirm waitlist entry when waitlistID is present/resolvable.
5. Publish BOOKING_CONFIRMED notification.
6. On terminal failures, ACK message and publish BOOKING_FULFILLMENT_INCIDENT.

Supabase context used:

- Project ID: cpxcpvcfbohvpiubbujg
- Key seeded entities used in this suite are from live project data and fixture conventions already used by existing docs.

## 2) Setup and Scenario Traceability

This document is aligned with:

- docs/Setup.md (worker deployment, Kong routing, RabbitMQ exchange wiring)
- docs/Scenarios.md (Scenario 1A/1C/1D fulfillment semantics)

Context7 references used while designing this suite:

- OpenAPI specification guidance on paths/operations/responses.
- Swagger UI execution model (Try it out request/response workflow).

## 3) Test Surfaces (Swagger)

Use these Swagger UIs for manual triggering:

- Payment Service: http://localhost:5004/docs
- Inventory Service: http://localhost:5003/inventory/docs/
- Waitlist Service: http://localhost:5005/docs
- Event Service: http://localhost:5001/docs

Worker under test (no Swagger UI):

- booking-fulfillment-orchestrator container logs

## 4) Global Components (Reusable)

Use these in all cases to avoid duplication.

### 4.1 Common Headers

- GC-HDR-JSON
  - Content-Type: application/json
- GC-HDR-INTERNAL
  - X-Internal-Token: value of INTERNAL_SERVICE_TOKEN

### 4.2 Core IDs (Supabase-backed)

- Event
  - EVT-301: 10000000-0000-0000-0000-000000000301

- Users
  - U1 Brandon: 00000000-0000-0000-0000-000000000001
  - U2 Boone: 00000000-0000-0000-0000-000000000002
  - U3 Ian: 00000000-0000-0000-0000-000000000003

- Category IDs for EVT-301
  - CAT1: 20000000-0000-0000-0000-000000000101
  - CAT2: 20000000-0000-0000-0000-000000000102
  - PEN: 20000000-0000-0000-0000-000000000103

- Stable hold IDs often used in fixtures
  - H-CONFIRMED-PUBLIC: 40000000-0000-0000-0000-000000000001
  - H-CONFIRMED-WAITLIST: 40000000-0000-0000-0000-000000000002
  - H-EXPIRED-WAITLIST: 40000000-0000-0000-0000-000000000003
  - H-FIX-VALID-HELD: 4b100000-0000-0000-0000-000000000001

- Stable waitlist IDs
  - WL-CONFIRMED: 60000000-0000-0000-0000-000000000002
  - WL-EXPIRED: 60000000-0000-0000-0000-000000000003
  - WL-WAITING-A: 60000000-0000-0000-0000-000000000001
  - WL-WAITING-B: 60000000-0000-0000-0000-000000000004

### 4.3 Reusable SQL Verification Snippets

Q-HOLD-STATE

```sql
select h.hold_id,
       h.status as hold_status,
       h.from_waitlist,
       h.user_id,
       h.event_id,
       sc.category_code,
       s.seat_number,
       s.status as seat_status,
       h.hold_expires_at,
       h.confirmed_at,
       h.released_at,
       h.expired_at,
       h.correlation_id,
       h.updated_at
from public.seat_holds h
join public.seat_categories sc on h.category_id = sc.category_id
join public.seats s on h.seat_id = s.seat_id
where h.hold_id = '<HOLD_ID>';
```

Q-WAITLIST-BY-ID

```sql
select waitlist_id,
       hold_id,
       status,
       event_id,
       user_id,
       joined_at,
       offered_at,
       confirmed_at,
       expired_at,
       updated_at
from public.waitlist_entries
where waitlist_id = '<WAITLIST_ID>';
```

Q-WAITLIST-BY-HOLD

```sql
select waitlist_id,
       hold_id,
       status,
       event_id,
       user_id,
       joined_at,
       offered_at,
       confirmed_at,
       expired_at,
       updated_at
from public.waitlist_entries
where hold_id = '<HOLD_ID>'
order by updated_at desc nulls last;
```

Q-TX-BY-HOLD

```sql
select transaction_id,
       hold_id,
       user_id,
       event_id,
       status,
       amount,
       currency,
       stripe_payment_intent_id,
       correlation_id,
       created_at,
       updated_at
from public.transactions
where hold_id = '<HOLD_ID>'
order by updated_at desc nulls last, created_at desc;
```

Q-WEBHOOK-EVENT

```sql
select webhook_event_id,
       payment_intent_id,
       hold_id,
       event_type,
       processing_status,
       error_message,
       received_at,
       processed_at
from public.payment_webhook_events
where webhook_event_id = '<EVENT_ID>';
```

### 4.4 Reusable Swagger Payload Templates

P-PAYMENT-INITIATE

```json
{
  "holdID": "4b100000-0000-0000-0000-000000000001",
  "userID": "00000000-0000-0000-0000-000000000001",
  "amount": 388.0
}
```

P-WAITLIST-JOIN-PEN

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "userID": "00000000-0000-0000-0000-000000000002",
  "seatCategory": "PEN",
  "qty": 1
}
```

P-WAITLIST-OFFER

```json
{
  "holdID": "4b100000-0000-0000-0000-000000000001"
}
```

## 5) Preconditions

1. Docker stack is running and healthy, including booking-fulfillment-orchestrator.
2. RabbitMQ topic exchange ticketblitz exists.
3. Kong route /eticket/generate is configured and reachable.
4. For deterministic runs, re-apply docs/payment-service-swagger-fixtures.sql.
5. Stripe webhook forwarding is active for signed success/failure webhook scenarios.

## 6) Manual Test Cases

Naming style follows should_expected_when_condition.

### Group A - Preflight and Readiness

| ID  | Test name                                                | Swagger input                         | Expected output                                                                     |
| --- | -------------------------------------------------------- | ------------------------------------- | ----------------------------------------------------------------------------------- |
| A01 | should_return_payment_health_when_dependencies_ready     | GET /health on Payment Swagger        | HTTP 200, service=payment-service, supabaseConfigured=true, rabbitmqConfigured=true |
| A02 | should_return_inventory_health_when_dependencies_ready   | GET /health on Inventory Swagger      | HTTP 200, service=inventory-service, supabaseConfigured=true                        |
| A03 | should_return_waitlist_health_when_dependencies_ready    | GET /health on Waitlist Swagger       | HTTP 200, service=waitlist-service, supabaseConfigured=true                         |
| A04 | should_show_bfo_queue_consumer_running_when_worker_is_up | No Swagger call; verify container log | Logs include listener startup for routing key booking.confirmed                     |

### Group B - BFO Success Path (No Waitlist Branch)

| ID  | Test name                                                          | Swagger input                                                                                                      | Expected output                                                                                         |
| --- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| B01 | should_create_pending_payment_intent_when_hold_is_valid_held       | POST /payment/initiate with P-PAYMENT-INITIATE                                                                     | HTTP 201 (or 200 idempotent replay), response has holdID, paymentIntentID, clientSecret, status=PENDING |
| B02 | should_accept_signed_success_webhook_when_payment_intent_succeeds  | Trigger Stripe succeeded event for the paymentIntent created in B01 (via Stripe test flow with webhook forwarding) | HTTP 200 from /payment/webhook, status=accepted, idempotent=false                                       |
| B03 | should_confirm_inventory_hold_when_bfo_processes_booking_confirmed | GET /inventory/hold/{hold_id} for B01 holdID                                                                       | HTTP 200, holdStatus=CONFIRMED, seatStatus=SOLD, confirmedAt not null                                   |
| B04 | should_leave_waitlist_unset_when_no_waitlist_entry_for_hold        | GET /waitlist/by-hold/{hold_id} for B01 holdID                                                                     | HTTP 404 Waitlist entry not found for holdID                                                            |

### Group C - BFO Success Path (Waitlist Confirm Branch)

| ID  | Test name                                                                                      | Swagger input                                                                | Expected output                                                                      |
| --- | ---------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| C01 | should_create_waiting_waitlist_entry_when_join_is_valid                                        | POST /waitlist/join with P-WAITLIST-JOIN-PEN                                 | HTTP 201, response includes waitlistID and status=WAITING                            |
| C02 | should_mark_waitlist_offered_with_hold_before_payment                                          | PUT /waitlist/{waitlistID}/offer with P-WAITLIST-OFFER (using B01 holdID)    | HTTP 200, status=HOLD_OFFERED, holdID matches                                        |
| C03 | should_include_waitlist_id_in_booking_confirmed_publisher_payload_when_hold_has_waitlist_entry | Complete payment success flow for B01 hold again with a fresh payment intent | /payment/webhook returns HTTP 200 accepted; BFO consumes event with waitlist context |
| C04 | should_transition_waitlist_to_confirmed_after_bfo_success                                      | GET /waitlist/{waitlistID} from C01                                          | HTTP 200, status=CONFIRMED, holdID set to B01 holdID                                 |

### Group D - Idempotency and Replay Safety

| ID  | Test name                                                                   | Swagger input                                                                                               | Expected output                                                                                |
| --- | --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| D01 | should_return_idempotent_true_when_same_processed_webhook_event_is_replayed | Replay a previously processed webhook event ID (example evt_seed_001) through signed webhook replay tooling | HTTP 200 from /payment/webhook, status=accepted, idempotent=true                               |
| D02 | should_keep_hold_confirmed_when_equivalent_success_is_reprocessed           | Replay succeeded signal for an already confirmed hold (new event ID, same payment intent)                   | HTTP 200 accepted; GET /inventory/hold/{hold_id} still holdStatus=CONFIRMED with no regression |

### Group E - Failure and Incident Paths

| ID  | Test name                                                                          | Swagger input                                                                                                                                                                          | Expected output                                                                                                                                                                           |
| --- | ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| E01 | should_publish_incident_when_inventory_confirm_returns_conflict                    | 1) POST /payment/initiate (fresh HELD hold). 2) PUT /inventory/hold/{hold_id}/release with reason=PAYMENT_TIMEOUT before payment success. 3) Complete payment success to fire webhook. | /payment/webhook returns HTTP 200 accepted; hold remains not HELD; BFO logs terminal inventory_confirm failure and incident publish attempt                                               |
| E02 | should_publish_incident_when_eticket_returns_non_retryable_4xx                     | Fault-injection precondition: set BFO ETICKET_GENERATE_URL to a path returning 404 and restart worker. Then run B01/B02 flow.                                                          | /payment/webhook HTTP 200 accepted; GET /inventory/hold/{hold_id} shows CONFIRMED; waitlist remains HOLD_OFFERED/unchanged; BFO logs terminal eticket_generate HTTP_404 and incident path |
| E03 | should_retry_then_publish_incident_when_eticket_request_is_transiently_unreachable | Fault-injection precondition: set BFO ETICKET_GENERATE_URL to unreachable host and BFO_MAX_RETRIES=3, restart worker, then run success trigger flow                                    | /payment/webhook HTTP 200 accepted; BFO logs retry attempts up to max, then terminal failure and incident publish                                                                         |
| E04 | should_skip_incident_email_when_incident_recipient_not_configured                  | Precondition: BOOKING_INCIDENT_EMAIL empty in BFO env; trigger E02 or E03 failure                                                                                                      | BFO logs include "BOOKING_INCIDENT_EMAIL is not configured, skipping incident notification"                                                                                               |

### Group F - Upstream Guardrails That Protect BFO

| ID  | Test name                                            | Swagger input                                                 | Expected output                                                                                 |
| --- | ---------------------------------------------------- | ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| F01 | should_reject_webhook_when_signature_missing         | POST /payment/webhook without Stripe-Signature                | HTTP 400, error=Missing Stripe-Signature header, no BFO processing                              |
| F02 | should_reject_webhook_when_signature_invalid         | POST /payment/webhook with invalid Stripe-Signature           | HTTP 400, error=Invalid signature, no BFO processing                                            |
| F03 | should_mark_webhook_ignored_for_unhandled_event_type | Send signed non-payment_intent event type to /payment/webhook | HTTP 200 accepted idempotent=false; webhook record processing_status=IGNORED; no BFO processing |

## 7) Detailed Steps for Key Flows

### 7.1 BFO Happy Path Execution Sheet

1. POST /payment/initiate with P-PAYMENT-INITIATE.
2. Capture paymentIntentID and clientSecret.
3. Complete Stripe test payment for that intent.
4. Wait for /payment/webhook success callback.
5. Verify:
   - Q-TX-BY-HOLD for hold has status SUCCEEDED.
   - Q-HOLD-STATE for hold has hold_status CONFIRMED and seat_status SOLD.
   - Waitlist by-hold for that hold is either 404 (no waitlist path) or CONFIRMED (waitlist path).

### 7.2 BFO Waitlist Branch Execution Sheet

1. POST /waitlist/join using P-WAITLIST-JOIN-PEN and capture waitlistID.
2. PUT /waitlist/{waitlistID}/offer with holdID equal to target payment hold.
3. Execute payment success flow (Section 7.1).
4. Verify Q-WAITLIST-BY-ID returns status CONFIRMED and hold_id matching payment hold.

### 7.3 BFO Incident Flow Execution Sheet

1. Prepare a failure condition (inventory conflict or eticket fault injection).
2. Trigger payment success webhook.
3. Verify worker logs:
   - terminal fulfillment failure line contains stage and error code.
   - incident publish attempted, or skipped when incident email is unset.
4. Verify state consistency:
   - inventory hold state reflects successful confirm only if failure happened after confirm.
   - waitlist remains unconfirmed if failure happened before waitlist confirm.

## 8) Coverage Map to BFO Code Paths

| BFO behavior                                           | Covered by                              |
| ------------------------------------------------------ | --------------------------------------- |
| Payload normalized from booking.confirmed              | B02, C03, F01-F03 (upstream guardrails) |
| Inventory confirm success                              | B03, C04                                |
| Inventory confirm conflict/not-found terminal handling | E01                                     |
| E-ticket success path                                  | B03, C04                                |
| E-ticket non-retryable failure handling                | E02                                     |
| E-ticket transient retry handling                      | E03                                     |
| Waitlist confirm branch                                | C04                                     |
| Notification publish for BOOKING_CONFIRMED             | B03, C04 (via downstream observability) |
| Incident publish or skip policy                        | E02, E03, E04                           |
| Webhook idempotency protection                         | D01                                     |

## 9) Known Limitations

1. BFO itself has no Swagger endpoint, so verification requires state and logs.
2. Signed success webhooks require Stripe tooling and cannot be fully emulated by unsigned Swagger requests.
3. Duplicate-success replay semantics depend on upstream Stripe replay behavior; this suite validates no state regression, not strict deduplication of notifications.

## 10) Recommended Execution Order

1. Group A
2. Group B
3. Group C
4. Group D
5. Group E
6. Group F

For deterministic reruns, re-apply docs/payment-service-swagger-fixtures.sql before Group B.
