# Payment Service Manual Swagger Test Cases

## 1) Scope and Objective

This manual suite covers the full payment-service API surface for Swagger-based testing:

- Health and docs endpoints
- Payment initiation and alias creation
- Payment lookup and verification endpoints
- Stripe webhook ingestion and idempotency behavior
- Internal status mutation endpoints and aliases
- Refund orchestration endpoints and aliases

Target service and docs endpoint:

- Base URL: `http://localhost:5004`
- Swagger UI: `http://localhost:5004/docs`
- OpenAPI spec: `http://localhost:5004/openapi.json`

Database context source used for this suite:

- Supabase project: `cpxcpvcfbohvpiubbujg`
- URL: `https://cpxcpvcfbohvpiubbujg.supabase.co`

## 2) Important Execution Note

You requested HELD preconditions via Inventory flow. In the current workspace code, Inventory is scaffolded and does not expose hold creation endpoints yet (only `GET /inventory/{event_id}/{seat_category}`).

Working alternative used in this implementation:

- Create deterministic payment test preconditions with SQL fixtures in `docs/payment-service-swagger-fixtures.sql`.

## 3) Global Components (Reusable)

Use these in every test to reduce repetition.

### 3.1 Headers

- `GC-HDR-JSON`
  - `Content-Type: application/json`
- `GC-HDR-INTERNAL-VALID`
  - `X-Internal-Token: <value of PAYMENT_INTERNAL_TOKEN>`
- `GC-HDR-INTERNAL-INVALID`
  - `X-Internal-Token: wrong-token`
- `GC-HDR-STRIPE-INVALID`
  - `Stripe-Signature: t=1,v1=invalidsignature`

### 3.2 Common Response Assertions

- `GC-RES-ERR`
  - HTTP status code matches case
  - body shape: `{"error": "<message>"}`
- `GC-RES-PAYMENT`
  - fields present: `holdID`, `paymentIntentID`, `clientSecret`, `amount`, `currency`, `status`, `holdExpiry`
- `GC-RES-REFUND`
  - fields present: `status`, `transactionID`, `refundAmount`, `attempts`

### 3.3 Deterministic IDs

Live seeded IDs already in Supabase:

- `DS-TX-SUCCEEDED-001`: `70000000-0000-0000-0000-000000000001`
- `DS-TX-SUCCEEDED-002`: `70000000-0000-0000-0000-000000000002`
- `DS-TX-REFUND-SUCCEEDED-003`: `70000000-0000-0000-0000-000000000003`
- `DS-TX-REFUND-FAILED-004`: `70000000-0000-0000-0000-000000000004`
- `DS-HOLD-CONFIRMED-001`: `40000000-0000-0000-0000-000000000001`
- `DS-HOLD-EXPIRED-003`: `40000000-0000-0000-0000-000000000003`

Fixture IDs from `docs/payment-service-swagger-fixtures.sql`:

- `FX-HOLD-VALID-HELD`: `4b100000-0000-0000-0000-000000000001`
- `FX-HOLD-EXPIRED-HELD`: `4b100000-0000-0000-0000-000000000002`
- `FX-HOLD-HELD-WITH-SUCCEEDED-TX`: `4b100000-0000-0000-0000-000000000003`
- `FX-TX-HELD-SUCCEEDED`: `7b100000-0000-0000-0000-000000000001`
- `FX-TX-FAILED-STATUS`: `7b100000-0000-0000-0000-000000000002`
- `FX-TX-REFUND-PENDING-RECENT`: `7b100000-0000-0000-0000-000000000003`
- `FX-TX-REFUND-PENDING-STALE`: `7b100000-0000-0000-0000-000000000004`
- `FX-TX-MISSING-PI`: `7b100000-0000-0000-0000-000000000005`
- `FX-TX-POLICY-OUTSIDE`: `7b100000-0000-0000-0000-000000000006`

### 3.4 DB Verification Queries

Run in Supabase SQL editor after mutation cases.

- `Q-TRANSACTION-BY-HOLD`
```sql
select transaction_id, hold_id, status, refund_status, refund_amount, failure_reason, stripe_payment_intent_id, created_at, updated_at
from public.transactions
where hold_id = '<HOLD_ID>'
order by created_at desc;
```

- `Q-TRANSACTION-BY-ID`
```sql
select transaction_id, hold_id, status, refund_status, refund_amount, failure_reason, stripe_payment_intent_id, created_at, updated_at
from public.transactions
where transaction_id = '<TRANSACTION_ID>';
```

- `Q-WEBHOOK-BY-EVENT`
```sql
select webhook_event_id, payment_intent_id, hold_id, event_type, processing_status, received_at, processed_at, error_message
from public.payment_webhook_events
where webhook_event_id = '<EVENT_ID>';
```

- `Q-CANCELLATION-BY-HOLD`
```sql
select cancellation_request_id, hold_id, transaction_id, status, refund_amount, attempt_count, last_attempt_at, resolved_at, reason
from public.cancellation_requests
where hold_id = '<HOLD_ID>'
order by requested_at desc;
```

- `Q-REFUND-ATTEMPTS-BY-CANCELLATION`
```sql
select refund_attempt_id, cancellation_request_id, transaction_id, attempt_no, status, error_code, error_message, attempted_at, completed_at
from public.refund_attempts
where cancellation_request_id = '<CANCELLATION_REQUEST_ID>'
order by attempt_no;
```

## 4) Environment Setup for Manual Run

1. Start stack and confirm payment service is healthy.
2. Open Swagger at `/docs`.
3. Apply `docs/payment-service-swagger-fixtures.sql` in Supabase SQL editor.
4. For auth-negative test cases, ensure `PAYMENT_INTERNAL_TOKEN` is set in runtime env.

## 5) Manual Test Cases

Naming format follows: `should_<expected>_when_<condition>`.

---

### Group A: Health and Docs

| ID | Test name | Swagger input | Expected output |
|---|---|---|---|
| A01 | should_return_service_health_when_health_is_called | `GET /health` no body | HTTP `200`; body contains `status="ok"`, `service="payment-service"`, and booleans `supabaseConfigured`, `rabbitmqConfigured`, `stripeConfigured` |
| A02 | should_return_openapi_document_when_openapi_is_called | `GET /openapi.json` no body | HTTP `200`; body has `openapi="3.0.3"`; `paths` includes `/payment/initiate`, `/payment/webhook`, `/payments/refund/{booking_id}` |
| A03 | should_render_swagger_ui_when_docs_is_opened | Browser open `GET /docs` | HTTP `200`; Swagger UI renders with payment operations visible |

---

### Group B: Payment Initiation and Creation

| ID | Test name | Swagger input | Expected output |
|---|---|---|---|
| B01 | should_create_payment_intent_when_hold_is_valid | `POST /payment/initiate`; headers `GC-HDR-JSON` + `GC-HDR-INTERNAL-VALID`; body `{"holdID":"4b100000-0000-0000-0000-000000000001","userID":"00000000-0000-0000-0000-000000000001","amount":388.00}` | HTTP `201`; body contains `holdID` same as input, `status="PENDING"`, non-empty `paymentIntentID`, non-empty `clientSecret`, `amount="388.00"`, `currency="SGD"`; DB: new transaction row for hold in `Q-TRANSACTION-BY-HOLD` |
| B02 | should_return_existing_pending_intent_when_same_request_is_replayed | Repeat B01 input | HTTP `200`; response keeps same `paymentIntentID` and `clientSecret` as B01; no new transaction row created |
| B03 | should_return_400_when_hold_id_is_not_uuid | `POST /payment/initiate`; valid headers; body `{"holdID":"not-a-uuid","userID":"00000000-0000-0000-0000-000000000001","amount":388.00}` | HTTP `400`; `GC-RES-ERR`; message contains `holdID must be a valid UUID` |
| B04 | should_return_400_when_user_id_is_not_uuid | body `{"holdID":"4b100000-0000-0000-0000-000000000001","userID":"bad-user","amount":388.00}` | HTTP `400`; message contains `userID must be a valid UUID` |
| B05 | should_return_400_when_amount_is_non_numeric | body `{"holdID":"4b100000-0000-0000-0000-000000000001","userID":"00000000-0000-0000-0000-000000000001","amount":"abc"}` | HTTP `400`; message contains `amount must be a numeric value` |
| B06 | should_return_400_when_amount_is_zero_or_negative | body `{"holdID":"4b100000-0000-0000-0000-000000000001","userID":"00000000-0000-0000-0000-000000000001","amount":0}` | HTTP `400`; message contains `amount must be greater than 0` |
| B07 | should_return_409_when_hold_does_not_belong_to_user | body `{"holdID":"4b100000-0000-0000-0000-000000000001","userID":"00000000-0000-0000-0000-000000000002","amount":388.00}` | HTTP `409`; message contains `holdID does not belong to userID` |
| B08 | should_return_409_when_hold_status_is_not_held | body using `DS-HOLD-CONFIRMED-001`: `{"holdID":"40000000-0000-0000-0000-000000000001","userID":"00000000-0000-0000-0000-000000000001","amount":160.00}` | HTTP `409`; message contains `Seat hold is not in HELD status` |
| B09 | should_return_409_when_hold_is_expired | body using `FX-HOLD-EXPIRED-HELD`: `{"holdID":"4b100000-0000-0000-0000-000000000002","userID":"00000000-0000-0000-0000-000000000001","amount":160.00}` | HTTP `409`; message contains `Seat hold has expired` |
| B10 | should_return_409_when_amount_does_not_match_hold | body `{"holdID":"4b100000-0000-0000-0000-000000000001","userID":"00000000-0000-0000-0000-000000000001","amount":387.99}` | HTTP `409`; message contains `amount does not match hold amount` |
| B11 | should_return_409_when_payment_already_completed_for_hold | body `{"holdID":"4b100000-0000-0000-0000-000000000003","userID":"00000000-0000-0000-0000-000000000002","amount":144.00}` | HTTP `409`; message contains `Payment already completed for this hold` |
| B12 | should_create_payment_when_alias_uses_ticket_id | `POST /payments/create`; headers `GC-HDR-JSON` + `GC-HDR-INTERNAL-VALID`; body `{"ticketID":"4b100000-0000-0000-0000-000000000001","userID":"00000000-0000-0000-0000-000000000001","amount":388.00}` | HTTP `200` or `201` depending prior run; response shape equals `GC-RES-PAYMENT` |
| B13 | should_return_400_when_alias_missing_hold_and_ticket | `POST /payments/create`; valid headers; body `{"userID":"00000000-0000-0000-0000-000000000001","amount":388.00}` | HTTP `400`; message contains `holdID (or ticketID) is required` |
| B14 | should_return_401_when_internal_token_missing_or_invalid | Any mutation endpoint from B-group; omit token or use `GC-HDR-INTERNAL-INVALID` | HTTP `401`; `GC-RES-ERR`; message `Unauthorized` |

Optional dependency-failure checks for B-group:

- Set `STRIPE_SECRET_KEY` empty and call B01 -> expected HTTP `503`, error `Stripe is not configured`.
- Set `SUPABASE_URL`/`SUPABASE_SERVICE_KEY` invalid and call B01 -> expected HTTP `503`, error `Supabase is not configured`.

---

### Group C: Hold Status and Verification Reads

| ID | Test name | Swagger input | Expected output |
|---|---|---|---|
| C01 | should_return_latest_hold_transaction_when_hold_exists | `GET /payment/hold/{hold_id}` with `hold_id=40000000-0000-0000-0000-000000000001` | HTTP `200`; body includes `holdID`, `transactionID=70000000-0000-0000-0000-000000000001`, `paymentStatus="SUCCEEDED"`, `amount="160.00"`, `currency="SGD"` |
| C02 | should_return_400_when_hold_lookup_id_invalid | `GET /payment/hold/{hold_id}` with `hold_id=invalid-id` | HTTP `400`; message contains `holdID must be a valid UUID` |
| C03 | should_return_404_when_no_transaction_for_hold | `GET /payment/hold/{hold_id}` with `hold_id=40000000-0000-0000-0000-000000000003` | HTTP `404`; message contains `No transaction found for hold` |
| C04 | should_verify_booking_by_transaction_id | `GET /payments/verify/{booking_id}` with `booking_id=70000000-0000-0000-0000-000000000001` | HTTP `200`; `resolvedBy="transaction_id"`; `transactionID` matches input; includes `withinPolicy`, `eligibleRefundAmount`, `feePercentage` |
| C05 | should_verify_booking_by_hold_id | `GET /payments/verify/{booking_id}` with `booking_id=40000000-0000-0000-0000-000000000001` | HTTP `200`; `resolvedBy="hold_id"`; `transactionID=70000000-0000-0000-0000-000000000001` |
| C06 | should_return_400_when_verify_id_invalid | `GET /payments/verify/{booking_id}` with `booking_id=not-a-uuid` | HTTP `400`; message contains `bookingID must be a valid UUID` |
| C07 | should_return_404_when_verify_booking_not_found | `GET /payments/verify/{booking_id}` with random UUID not in DB | HTTP `404`; message contains `Booking transaction not found` |
| C08 | should_verify_policy_when_booking_exists | `GET /payments/verify-policy/{booking_id}` with `booking_id=70000000-0000-0000-0000-000000000001` | HTTP `200`; fields include `eligible`, `withinPolicy`, `reason`, `policyCutoffAt`, `eventDate`, `purchaseDate` |
| C09 | should_return_404_when_verify_policy_not_found | `GET /payments/verify-policy/{booking_id}` with random UUID | HTTP `404`; message contains `Booking transaction not found` |

---

### Group D: Webhook Processing

| ID | Test name | Swagger input | Expected output |
|---|---|---|---|
| D01 | should_return_400_when_stripe_signature_header_missing | `POST /payment/webhook`; body `{}`; no `Stripe-Signature` | HTTP `400`; message `Missing Stripe-Signature header` |
| D02 | should_return_400_when_signature_invalid | `POST /payment/webhook`; headers `GC-HDR-STRIPE-INVALID`; body `{}` | HTTP `400`; message `Invalid signature` |
| D03 | should_return_400_when_payload_invalid | `POST /payment/webhook`; signature present but body malformed for Stripe parser | HTTP `400`; message `Invalid payload` |
| D04 | should_return_400_when_event_id_missing | `POST /payment/webhook`; validly parsed event object with no `id` | HTTP `400`; message `Webhook event ID is missing` |
| D05 | should_short_circuit_when_duplicate_processed_event_received | `POST /payment/webhook` with event id `evt_seed_001` and same payload identity | HTTP `200`; body has `status="accepted"`, `idempotent=true`; DB row in `Q-WEBHOOK-BY-EVENT` remains `PROCESSED` |
| D06 | should_short_circuit_when_duplicate_recent_received_event_arrives | Precondition: insert webhook row with same id and `processing_status='RECEIVED'`, `received_at=now()`; then post same event | HTTP `200`; `idempotent=true`; handler side effects are skipped |
| D07 | should_mark_ignored_when_event_type_not_handled | Post valid signed event type like `charge.succeeded` | HTTP `200`; `idempotent=false`; `Q-WEBHOOK-BY-EVENT` shows `processing_status='IGNORED'` |
| D08 | should_return_503_when_webhook_secret_missing | Clear `STRIPE_WEBHOOK_SECRET`, then post webhook | HTTP `503`; message `STRIPE_WEBHOOK_SECRET is not configured` |
| D09 | should_return_503_when_supabase_unconfigured_for_webhook | Break Supabase env and call webhook | HTTP `503`; message `Supabase is not configured` |
| D10 | should_process_succeeded_or_failed_intent_when_valid_signed_event_received | Use Stripe CLI to forward valid signed webhook to `/payment/webhook` | HTTP `200`; `idempotent=false`; for succeeded intent DB transaction status becomes `SUCCEEDED`; for failed intent status becomes `FAILED` with `failure_reason` |

Note for D10:

- Swagger alone cannot generate cryptographically valid Stripe signatures.
- Use Stripe CLI `stripe listen` and `stripe trigger` for the signed-event path.

---

### Group E: Status Update Endpoints and Aliases

| ID | Test name | Swagger input | Expected output |
|---|---|---|---|
| E01 | should_set_refund_pending_when_status_processing_refund | `PUT /payments/status/{booking_id}` with `booking_id=70000000-0000-0000-0000-000000000002`; body `{"status":"PROCESSING_REFUND"}`; valid internal token | HTTP `200`; response `updated=true`, `status="REFUND_PENDING"`, `refundStatus="PENDING"`; `Q-TRANSACTION-BY-ID` confirms |
| E02 | should_set_refund_succeeded_when_status_refund_succeeded | same endpoint; body `{"status":"REFUND_SUCCEEDED","refundAmount":144.00}` | HTTP `200`; response `status="REFUND_SUCCEEDED"`; `refundStatus="SUCCEEDED"`; DB reflects `refund_amount=144.00` |
| E03 | should_set_refund_failed_when_status_refund_failed | body `{"status":"REFUND_FAILED","reason":"Manual fail test"}` | HTTP `200`; response `status="REFUND_FAILED"`; DB `failure_reason` contains `Manual fail test` |
| E04 | should_set_succeeded_when_status_succeeded | body `{"status":"SUCCEEDED"}` | HTTP `200`; response `status="SUCCEEDED"`; DB matches |
| E05 | should_set_failed_when_status_failed | body `{"status":"FAILED","reason":"forced"}` | HTTP `200`; response `status="FAILED"`; DB `failure_reason="forced"` |
| E06 | should_update_cancellation_only_when_status_eligible | body `{"status":"ELIGIBLE"}` | HTTP `200`; transaction status remains current transaction value; latest cancellation row status is `ELIGIBLE` |
| E07 | should_return_400_when_status_value_unsupported | body `{"status":"NOT_A_REAL_STATUS"}` | HTTP `400`; message `Unsupported status value` |
| E08 | should_return_400_when_status_missing | body `{}` | HTTP `400`; message `status is required` |
| E09 | should_return_400_when_refund_amount_invalid | body `{"status":"REFUND_SUCCEEDED","refundAmount":-1}` | HTTP `400`; message contains `refundAmount must be greater than 0` |
| E10 | should_return_404_when_booking_not_found | `booking_id=<random uuid>` with valid body | HTTP `404`; message `Booking transaction not found` |
| E11 | should_behave_same_for_update_alias | `PUT /payments/update/{booking_id}` with same payload as E01 | HTTP `200`; same semantics as `/payments/status/{booking_id}` |
| E12 | should_mark_processing_for_processing_alias | `PUT /payments/processing/{booking_id}` with valid token | HTTP `200`; response `status="REFUND_PENDING"` |
| E13 | should_mark_success_for_success_alias | `PUT /payments/success/{booking_id}`; body optional `{"refundAmount":151.20}` | HTTP `200`; response `status="REFUND_SUCCEEDED"` |
| E14 | should_mark_failed_for_fail_alias_when_transaction_id_supplied | `PUT /payments/status/fail`; body `{"transactionID":"70000000-0000-0000-0000-000000000002","reason":"refund failed"}` | HTTP `200`; response `status="REFUND_FAILED"`; DB reflects failure reason |
| E15 | should_return_400_for_fail_alias_when_identifier_missing | `PUT /payments/status/fail`; body `{"reason":"missing id"}` | HTTP `400`; message contains `bookingID or transactionID is required` |
| E16 | should_return_401_for_status_mutations_when_token_missing_or_invalid | any E-group mutation endpoint without valid internal token | HTTP `401`; `Unauthorized` |

---

### Group F: Refund Endpoint and Alias

| ID | Test name | Swagger input | Expected output |
|---|---|---|---|
| F01 | should_return_already_refunded_when_transaction_already_refund_succeeded | `POST /payments/refund/{booking_id}` with `booking_id=70000000-0000-0000-0000-000000000003`; token valid | HTTP `200`; body `status="already_refunded"`, `attempts=0`, `refundAmount="151.20"` |
| F02 | should_return_already_refunded_when_booking_id_is_hold_with_refund_succeeded | `POST /payments/refund/{booking_id}` with `booking_id=40000000-0000-0000-0000-000000000004` | HTTP `200`; body `status="already_refunded"` |
| F03 | should_return_400_for_refund_alias_when_booking_identifier_missing | `POST /payments/refund`; body `{}` | HTTP `400`; message `bookingID or transactionID is required` |
| F04 | should_return_400_when_refund_booking_id_invalid_uuid | `POST /payments/refund/{booking_id}` with `booking_id=invalid` | HTTP `400`; message contains `bookingID must be a valid UUID` |
| F05 | should_return_404_when_refund_booking_not_found | `POST /payments/refund/{booking_id}` with random UUID | HTTP `404`; message `Booking transaction not found` |
| F06 | should_return_400_when_refund_amount_exceeds_transaction_amount | `POST /payments/refund/{booking_id}` for `70000000-0000-0000-0000-000000000001`; body `{"refundAmount":9999}` | HTTP `400`; message `refundAmount cannot exceed transaction amount` |
| F07 | should_return_409_when_transaction_status_is_not_refundable | `POST /payments/refund/{booking_id}` with `booking_id=7b100000-0000-0000-0000-000000000002` (`FAILED`) | HTTP `409`; message `Only successful payments can be refunded` |
| F08 | should_return_409_when_refund_is_already_in_progress_with_recent_pending_attempt | `POST /payments/refund/{booking_id}` with `booking_id=7b100000-0000-0000-0000-000000000003` | HTTP `409`; message `Refund is already in progress`; `Q-REFUND-ATTEMPTS-BY-CANCELLATION` keeps pending attempt uncompleted |
| F09 | should_recover_stale_pending_attempt_before_retrying_refund | `POST /payments/refund/{booking_id}` with `booking_id=7b100000-0000-0000-0000-000000000004` | Expected API: typically HTTP `502` in seed/test-key environment; expected DB: stale attempt marked `FAILED` with `error_code='STALE_PENDING'`, then new attempts inserted with incremented `attempt_no` |
| F10 | should_reject_refund_when_outside_policy_window | `POST /payments/refund/{booking_id}` with `booking_id=7b100000-0000-0000-0000-000000000006` | HTTP `409`; message `Booking is not eligible for refund under policy`; latest cancellation record has `status='REJECTED'` |
| F11 | should_return_400_when_transaction_missing_payment_intent | `POST /payments/refund/{booking_id}` with `booking_id=7b100000-0000-0000-0000-000000000005` | HTTP `400`; message `Transaction does not contain a Stripe payment intent ID` |
| F12 | should_return_502_after_max_refund_attempts_fail | `POST /payments/refund/{booking_id}` with `booking_id=70000000-0000-0000-0000-000000000004` (`REFUND_FAILED` seed) | HTTP `502`; message `Refund failed after maximum retry attempts`; DB transaction ends `REFUND_FAILED`; cancellation remains `CANCELLATION_IN_PROGRESS`; attempts continue with incrementing attempt numbers |
| F13 | should_accept_alias_refund_when_booking_id_in_body | `POST /payments/refund`; body `{"bookingID":"70000000-0000-0000-0000-000000000003"}` | HTTP `200`; body as F01 |
| F14 | should_return_401_for_refund_when_internal_token_missing_or_invalid | Any F-group mutation without valid token | HTTP `401`; `Unauthorized` |
| F15 | should_execute_successful_refund_for_real_paid_intent | `POST /payments/refund/{booking_id}` on a transaction created from a real successful Stripe PaymentIntent | HTTP `200`; body `status="success"`; DB transaction `REFUND_SUCCEEDED`, `refund_status='SUCCEEDED'`, and new refund attempt row `SUCCEEDED` |

Optional dependency checks for F-group:

- Empty `STRIPE_SECRET_KEY` and call refund -> HTTP `503`, `Stripe is not configured`.
- Invalid Supabase config and call refund -> HTTP `503`, `Supabase is not configured`.

## 6) Coverage Map (Endpoint-to-Cases)

- `GET /health`: A01
- `GET /openapi.json`: A02
- `GET /docs`: A03
- `POST /payment/initiate`: B01-B11, B14
- `POST /payments/create`: B12-B14
- `GET /payment/hold/{hold_id}`: C01-C03
- `GET /payments/verify/{booking_id}`: C04-C07
- `GET /payments/verify-policy/{booking_id}`: C08-C09
- `POST /payment/webhook`: D01-D10
- `PUT /payments/status/{booking_id}`: E01-E10, E16
- `PUT /payments/update/{booking_id}`: E11
- `PUT /payments/processing/{booking_id}`: E12
- `PUT /payments/success/{booking_id}`: E13
- `PUT /payments/status/fail`: E14-E15
- `POST /payments/refund/{booking_id}`: F01-F12, F14-F15
- `POST /payments/refund`: F03, F13

## 7) Execution Order Recommendation

Run in this order to minimize flaky state interactions:

1. A-group
2. C-group (read-only)
3. B-group
4. D-group negatives
5. E-group
6. F-group

Re-apply `docs/payment-service-swagger-fixtures.sql` before B-group or F-group if previous runs mutated fixture rows.

## 8) One-Pass Run Sheet (Supabase-Validated)

The IDs in this run sheet were validated against Supabase and mapped to the current fixture strategy.

### 8.1 Preflight Before Running

1. Re-apply `docs/payment-service-swagger-fixtures.sql`.
2. Confirm the key preconditions:

```sql
select hold_id, user_id, status, amount, hold_expires_at
from public.seat_holds
where hold_id in (
  '4b100000-0000-0000-0000-000000000001',
  '4b100000-0000-0000-0000-000000000002',
  '4b100000-0000-0000-0000-000000000003'
)
order by hold_id;

select transaction_id, hold_id, status, refund_status
from public.transactions
where transaction_id in (
  '7b100000-0000-0000-0000-000000000001',
  '7b100000-0000-0000-0000-000000000002',
  '7b100000-0000-0000-0000-000000000003',
  '7b100000-0000-0000-0000-000000000004',
  '7b100000-0000-0000-0000-000000000005',
  '7b100000-0000-0000-0000-000000000006'
)
order by transaction_id;
```

Expected essentials:

- `4b100000-...0001`: `HELD`, amount `388.00`
- `4b100000-...0002`: `HELD` and expired
- `4b100000-...0003`: `HELD` with existing SUCCEEDED transaction `7b100000-...0001`

### 8.2 Recommended Execution Order

Run in this exact order to reduce state interference:

1. A01, A02, A03
2. C01, C02, C03, C04, C05, C06, C07, C08, C09
3. B03, B04, B05, B06, B07, B08, B09, B10, B11, B13, B14
4. B01, then B02 immediately, then B12
5. D01, D02, D03, D04, D05, D06, D07
6. E07, E08, E09, E10, E15, E16
7. E01, E02, E03, E04, E05, E06, E11, E12, E13, E14
8. F03, F04, F05, F06, F07, F11, F14
9. F01, F02, F13
10. F08, F09, F10, F12
11. F15 (real Stripe flow only)

### 8.3 High-Reuse Payloads

- B01/B02 baseline:

```json
{"holdID":"4b100000-0000-0000-0000-000000000001","userID":"00000000-0000-0000-0000-000000000001","amount":388.00}
```

- B11 baseline:

```json
{"holdID":"4b100000-0000-0000-0000-000000000003","userID":"00000000-0000-0000-0000-000000000002","amount":144.00}
```

- B12 alias baseline:

```json
{"ticketID":"4b100000-0000-0000-0000-000000000001","userID":"00000000-0000-0000-0000-000000000001","amount":388.00}
```

### 8.4 Mid-Run Reseed Trigger

If any of these fail due to previous state mutation, re-apply `docs/payment-service-swagger-fixtures.sql` and resume from the start of the affected group:

- `B01` returns `200` unexpectedly before first run
- `F08` does not report in-progress refund
- `F09` does not detect stale pending attempt
