# Cancellation Orchestrator Swagger Manual Test Suite

## 1. Scope

This suite validates the composite Cancellation Orchestrator endpoints:

1. `POST /orchestrator/cancellation`
2. `POST /bookings/cancel/{booking_id}`
3. `POST /orchestrator/cancellation/reallocation/confirm`
4. `GET /health`

It covers validation, policy gates, refund states, waitlist reallocation, and OutSystems transfer behavior.

---

## 2. Environment Preconditions

1. Docker stack is up and healthy.
2. Kong routes are active.
3. OutSystems E-Ticket API is reachable.
4. Internal token values match between caller and services.
5. Supabase seed data is present.

Recommended checks:

1. `GET http://localhost:8000/health`
2. `GET http://localhost:8000/orchestrator/cancellation/health`
3. Payment verify endpoint for target booking returns 200.
4. OutSystems `GET /eticket/hold/{holdID}` works for the old and new hold IDs.

---

## 3. Auth and Headers

### 3.1 Public fan flow endpoints

Use standard JSON headers:

1. `Content-Type: application/json`
2. `Accept: application/json`

### 3.2 Internal confirm endpoint

`POST /orchestrator/cancellation/reallocation/confirm` requires:

1. `X-Internal-Token: <INTERNAL_SERVICE_TOKEN>`
2. `Content-Type: application/json`
3. `Accept: application/json`

---

## 4. Core Fixture IDs (Current Working Set)

Use these values unless your DB has changed:

1. `bookingID`: `70000000-0000-0000-0000-000000000001`
2. `oldHoldID`: `40000000-0000-0000-0000-000000000001`
3. `oldTicketID`: `ETK-SMOKE-0001`
4. `waitlistID`: `6d3a5c49-7600-49d1-9632-a852475cd694`
5. `newHoldID`: `88bd7bde-c5cc-43d8-ab0b-f4a5f3fb3563`
6. `newUserID`: `00000000-0000-0000-0000-000000000001`
7. `newSeatID`: `30000000-0000-0000-0000-000000000031`
8. `newSeatNumber`: `P01`
9. `newTransactionID`: `0dacea70-03cf-4a1b-a490-d50d5c55c66e`

---

## 5. SQL Utility Snippets

### 5.1 Discover a candidate waitlist row

```sql
select waitlist_id, user_id, event_id, status, hold_id, joined_at
from public.waitlist_entries
where event_id = '10000000-0000-0000-0000-000000000301'
order by joined_at desc;
```

### 5.2 Prepare waitlist row for reallocation tests

```sql
update public.waitlist_entries
set status='HOLD_OFFERED',
    hold_id='88bd7bde-c5cc-43d8-ab0b-f4a5f3fb3563',
    offered_at=now(),
    expired_at=now()+interval '10 minutes',
    updated_at=now()
where waitlist_id='6d3a5c49-7600-49d1-9632-a852475cd694';
```

### 5.3 Cleanup waitlist row after tests

```sql
update public.waitlist_entries
set status='WAITING',
    hold_id=null,
    offered_at=null,
    expired_at=null,
    updated_at=now()
where waitlist_id='6d3a5c49-7600-49d1-9632-a852475cd694';
```

---

## 6. Case Format

Each case contains:

1. Purpose
2. Request
3. Expected HTTP status
4. Expected response assertions
5. Notes/cleanup

---

## 7. Manual Test Cases

## Group A: Health, Auth, Validation

### CO-001 Health endpoint

1. Request: `GET /orchestrator/cancellation/health`
2. Expect: `200`
3. Assert: `status = ok`, service name present, dependency flags present.

### CO-002 Internal auth required on confirm endpoint

1. Request: `POST /orchestrator/cancellation/reallocation/confirm` without `X-Internal-Token`
2. Expect: `401`
3. Assert: error payload contains unauthorized message.

### CO-003 Internal auth rejects invalid token

1. Request: same endpoint with wrong `X-Internal-Token`
2. Expect: `401`
3. Assert: unauthorized.

### CO-004 Cancellation rejects missing bookingID

1. Request body omits `bookingID`
2. Expect: `400`
3. Assert: validation error for bookingID.

### CO-005 Cancellation rejects invalid bookingID UUID

1. Request body uses `bookingID = abc`
2. Expect: `400`
3. Assert: bookingID must be UUID.

### CO-006 Cancellation rejects missing userID

1. Request body omits `userID`
2. Expect: `400`
3. Assert: validation error for userID.

### CO-007 Cancellation rejects invalid userID UUID

1. Request body uses `userID = abc`
2. Expect: `400`
3. Assert: userID must be UUID.

### CO-008 Reallocation confirm rejects missing waitlistID

1. Request body omits `waitlistID`
2. Expect: `400`
3. Assert: validation error for waitlistID.

### CO-009 Reallocation confirm rejects invalid waitlistID UUID

1. Request body uses non-UUID `waitlistID`
2. Expect: `400`
3. Assert: UUID validation error.

### CO-010 Reallocation confirm rejects invalid newHoldID UUID

1. Request body uses non-UUID `newHoldID`
2. Expect: `400`
3. Assert: UUID validation error.

---

## Group B: Cancellation Flow Behavior

### CO-011 Booking not found

1. Request: valid UUID bookingID not present in payment records.
2. Expect: `404`
3. Assert: booking/payment not found message.

### CO-012 Booking ownership mismatch

1. Request: existing bookingID but different userID.
2. Expect: `409`
3. Assert: ownership mismatch message.

### CO-013 Outside policy denied

1. Request: booking outside refund policy window.
2. Expect: `409`
3. Assert: status indicates denied and reason references policy.

### CO-014 Already refunded short-circuit

1. Request: booking with payment status already refunded/succeeded.
2. Expect: `200`
3. Assert: status indicates already refunded.

### CO-015 Refund pending conflict

1. Request: booking with `REFUND_PENDING`.
2. Expect: `409`
3. Assert: conflict message indicates refund in progress.

### CO-016 Prior refund failed conflict

1. Request: booking with `REFUND_FAILED`.
2. Expect: `409`
3. Assert: manual follow-up style conflict message.

### CO-017 Refund success with no waitlist

1. Request: cancellable booking and no active waitlist entry.
2. Expect: `200`
3. Assert: response indicates refund completed and public inventory path.

### CO-018 Refund success with waitlist reallocation pending

1. Request: cancellable booking and active waitlist.
2. Expect: `202`
3. Assert: response includes `waitlistID`, `newHoldID`, and payment init details.

### CO-019 Refund provider failure compensation

1. Force payment refund call to fail.
2. Expect: `502`
3. Assert: status indicates cancellation in progress/manual follow-up.

### CO-020 Old e-ticket by hold not found

1. Ensure OutSystems returns not found for old hold.
2. Expect: `404`
3. Assert: e-ticket hold not found message.

### CO-021 E-ticket ownership validation conflict

1. Force OutSystems validation to return owner mismatch/non-cancellable status.
2. Expect: `409`
3. Assert: conflict mapped from validation.

### CO-022 Dependency outage mapping

1. Stop payment or inventory dependency for this endpoint path.
2. Expect: `503`
3. Assert: dependency failure details returned.

---

## Group C: Reallocation Confirmation Behavior

### CO-023 Waitlist entry not found

1. Use non-existent waitlistID.
2. Expect: `404`
3. Assert: waitlist entry not found.

### CO-024 Waitlist hold mismatch

1. waitlist entry holdID differs from request `newHoldID`.
2. Expect: `409`
3. Assert: mismatch message.

### CO-025 Waitlist status not eligible

1. Set waitlist status not `HOLD_OFFERED`.
2. Expect: `409`
3. Assert: not eligible for confirmation.

### CO-026 Provided newUserID mismatch

1. Pass `newUserID` different from waitlist owner.
2. Expect: `409`
3. Assert: newUserID mismatch.

### CO-027 New hold payment not succeeded

1. Ensure payment record for new hold is not SUCCEEDED.
2. Expect: `409`
3. Assert: waitlist payment not completed.

### CO-028 Hold confirm dependency failure

1. Force inventory hold confirm failure.
2. Expect: `503`
3. Assert: dependency error mapping.

### CO-029 Original booking old ticket lookup failure

1. Break old hold -> eticket lookup path.
2. Expect: `404` or `503` (depends on failure mode).
3. Assert: mapped dependency/not-found response.

### CO-030 Transfer failure reconciliation required

1. Force OutSystems `POST /etickets/update` to fail.
2. Expect: `502`
3. Assert: `status = REALLOCATION_RECONCILIATION_REQUIRED`.

### CO-031 Transfer success confirms waitlist

1. Transfer succeeds and waitlist confirm call succeeds.
2. Expect: `200`
3. Assert: `status = REALLOCATION_CONFIRMED`, includes `ticketID`.

### CO-032 Transfer idempotent replay success

1. newHold already has exactly matching ticket assignment.
2. OutSystems should return `200` with existing `newTicketID`.
3. Expect orchestrator: `200`
4. Assert: `REALLOCATION_CONFIRMED` and stable `ticketID`.

### CO-033 Transfer mismatch conflict path

1. newHold already has ticket but fields mismatch.
2. OutSystems returns `409`.
3. Expect orchestrator: `502`
4. Assert: reconciliation required.

### CO-034 Notification publish failure on confirm

1. Simulate MQ publish failure after transfer success.
2. Expect: `503`
3. Assert: dependency/publish failure message.

### CO-035 Header contract regression

1. Call confirm with wrong internal auth header name.
2. Expect: `401`
3. Assert: unauthorized.

---

## Group D: Endpoint Parity and Golden Scenarios

### CO-036 Alias endpoint parity

1. Compare result of:
   - `POST /orchestrator/cancellation`
   - `POST /bookings/cancel/{booking_id}`
2. Expect: same status and equivalent payload semantics.

### CO-037 Golden path: REALLOCATION_CONFIRMED

Purpose: prove end-to-end successful reallocation confirmation.

Pre-setup:

1. Set waitlist row to `HOLD_OFFERED` using Section 5.2.
2. Verify new hold payment is `SUCCEEDED`.
3. Verify old hold ticket exists in OutSystems.

Request:

```json
POST /orchestrator/cancellation/reallocation/confirm
{
  "bookingID": "70000000-0000-0000-0000-000000000001",
  "waitlistID": "6d3a5c49-7600-49d1-9632-a852475cd694",
  "newHoldID": "88bd7bde-c5cc-43d8-ab0b-f4a5f3fb3563",
  "newUserID": "00000000-0000-0000-0000-000000000001",
  "correlationID": "<uuid>"
}
```

Headers:

1. `X-Internal-Token: ticketblitz-internal-token`

Expected:

1. HTTP `200`
2. `status = REALLOCATION_CONFIRMED`
3. `ticketID` present and non-empty
4. `waitlistID/newHoldID/newUserID` match request context

Post-checks:

1. Waitlist entry becomes `CONFIRMED` with matching holdID.
2. OutSystems has valid ticket bound to `newHoldID`.

Cleanup:

1. Run Section 5.3 when needed.

### CO-038 Reconciliation required scenario

1. Keep same fixture as CO-037 but force OutSystems update to fail.
2. Expect: `502`
3. Assert: `REALLOCATION_RECONCILIATION_REQUIRED` and actionable reason.

### CO-039 Correlation ID behavior

1. Provide valid `correlationID` UUID and inspect downstream logs/events.
2. Expect: value propagates through transfer and notification paths.

### CO-040 OutSystems status route parity

1. Verify orchestrator uses `PUT /etickets/status/{ticketID}` for status transitions.
2. Expect: no calls to legacy path formats.

### CO-041 OutSystems update contract compliance

1. For idempotent replay, OutSystems returns `200` + `newTicketID`.
2. For genuine mismatch, OutSystems returns `409` with non-empty error body.
3. Expect orchestrator behavior:
   - `200` for idempotent replay
   - `502` reconciliation for mismatch/failure

---

## 8. Recommended Execution Order

Run in this order:

1. CO-001 to CO-010 (sanity/validation)
2. CO-011 to CO-022 (cancellation logic)
3. CO-023 to CO-035 (confirm path branches)
4. CO-036 to CO-041 (parity and golden scenarios)

If CO-037 fails, run CO-041 immediately to isolate OutSystems response contract issues.

---

## 9. Failure Triage Checklist (CO-037 Focus)

When CO-037 returns `502`:

1. Check direct OutSystems `POST /etickets/update` with the exact same payload.
2. If direct returns `409`:
   - verify newHold existing ticket field equality (user/event/seat/seatNumber/transaction)
   - ensure idempotent replay branch returns `200` instead of conflict
3. Ensure `409` responses include body details (code/message/details) for diagnosis.
4. Re-run CO-037 after publish and confirm route points to latest OutSystems version.

---

## 10. Evidence Capture Template

For each case, capture:

1. Case ID
2. Request URL + body
3. Response status + body
4. DB pre-state and post-state queries
5. Pass/fail
6. If fail: root cause and next action

Example row:

```text
CO-037 | POST /orchestrator/cancellation/reallocation/confirm | 200 | REALLOCATION_CONFIRMED | PASS
```
