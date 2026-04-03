# TicketBlitz OutSystems E-Ticket Service Implementation Guide

## 1. Scope and Outcome

This guide gives an unabridged, step-by-step implementation path for the TicketBlitz E-Ticket service in OutSystems, based on:

1. Your current project setup and scenario documents.
2. Live Supabase context from project `cpxcpvcfbohvpiubbujg`.
3. Latest OutSystems documentation retrieved through Context7.

By following this guide, you will produce an externally hosted OutSystems E-Ticket service (outside Docker) that supports:

- `POST /eticket/generate`
- `GET /eticket/hold/{holdID}`
- `GET /eticket/validate` (REST replacement for Scenario 3 gRPC validation)
- `PUT /tickets/status/{ticketID}`
- `POST /etickets/update` (ticket transfer / cancellation updates)

and is ready to integrate with Booking Fulfillment, Booking Status, and Cancellation flows.

---

## 2. Deep Analysis of Your Current Setup and Scenarios

## 2.1 What your setup currently says

From your setup and scenario docs:

1. OutSystems E-Ticket service is external and not in Docker (`docs/Setup.md`).
2. Root `.env` already expects:
   - `OUTSYSTEMS_BASE_URL`
   - `OUTSYSTEMS_API_KEY`
3. Scenario 1 models E-Ticket as **OutSystems REST**.
4. Scenario 1 API table expects:
   - `POST /eticket/generate`
   - `GET /eticket/hold/{holdID}`

## 2.2 Gaps and inconsistencies discovered

1. **No backend implementation currently calls OutSystems**.
   - Search across `backend/**` found no OutSystems endpoint usage.
2. **Scenario protocol mismatch**:
   - Scenario 1 says E-Ticket is REST.
   - Scenario 3 still references `gRPC ValidateTicket`.
3. **Ticket storage mismatch across docs**:
   - Scenario docs describe an `etickets` table, but live Supabase has no ticket table.
   - `database/ticketblitz_schema_v2.sql` explicitly says it excludes E-Ticket service.
4. **ID type mismatch in scenario tables**:
   - Some scenario tables still use INT-like examples.
   - Live Supabase is UUID-based across core entities.

## 2.3 Live Supabase context that affects E-Ticket design

Pulled from Supabase project `cpxcpvcfbohvpiubbujg`:

1. Core entities are UUID keyed:
   - `users.user_id`
   - `events.event_id`
   - `seat_holds.hold_id`
   - `transactions.transaction_id`
2. Hold and payment states are mature:
   - `seat_holds.status` enum: `HELD`, `CONFIRMED`, `EXPIRED`, `RELEASED`
   - `transactions.status` enum: `PENDING`, `SUCCEEDED`, `FAILED`, `REFUND_PENDING`, `REFUND_SUCCEEDED`, `REFUND_FAILED`
3. Waitlist and cancellation states are also mature.
4. There is no `etickets` table in Supabase currently.

Implication:
- OutSystems should be the primary ticket datastore as intended by your architecture.
- Ticket APIs must use UUID string fields end-to-end to match upstream services.

## 2.4 Architecture decision to lock before implementation

Standardize all E-Ticket interactions on REST now.

- Keep Scenario 1 as-is (REST).
- Refactor Scenario 3 references from gRPC to REST `GET /eticket/validate`.

This is aligned with your Scenario 1 rationale and OutSystems API model.

---

## 3. OutSystems Documentation Baseline (Context7)

The implementation below is grounded on these current OutSystems docs (retrieved via Context7):

1. Expose REST APIs (O11 and ODC):
   - `integration-with-systems/rest/expose-rest-apis/*`
   - `docs-odc .../integration-with-systems/exposing_rest/*`
2. Custom authentication on exposed REST:
   - `OnAuthentication` callback flow.
3. REST method flow:
   - `OnRequest -> OnAuthentication -> deserialize/validate -> method -> serialize -> OnResponse`.
4. Custom URL paths for exposed methods.
5. Custom HTTP status codes:
   - ODC `Response_SetStatusCode` from HTTP library.
   - O11 equivalent via HTTPRequestHandler.
6. Error handling in exposed REST APIs.
7. Runtime configuration and secret handling via Site Properties.
8. Timer/background job behavior (for optional cleanup and reconciliation jobs).

Note:
- This guide is written with ODC-first terminology (latest platform direction), and includes O11 equivalents where needed.

---

## 4. Target E-Ticket Contract for TicketBlitz

Use this as the canonical contract.

## 4.1 Endpoint summary

1. `POST /eticket/generate`
   - Purpose: idempotently issue ticket when hold is confirmed and payment succeeded.
2. `GET /eticket/hold/{holdID}`
   - Purpose: fetch ticket by hold for booking-status polling.
3. `GET /eticket/validate?ticketID={ticketID}&userID={userID}`
   - Purpose: replace gRPC validation in cancellation flow.
4. `PUT /tickets/status/{ticketID}`
   - Purpose: mark ticket `USED`, `CANCELLED`, or `CANCELLATION_IN_PROGRESS`.
5. `POST /etickets/update`
   - Purpose: handle transfer/update semantics in Scenario 3 (old ticket canceled, new ticket issued or relinked).

## 4.2 Status values

Standardize ticket status values as text constants:

- `VALID`
- `USED`
- `CANCELLED`
- `CANCELLATION_IN_PROGRESS`

## 4.3 Idempotency rule

`POST /eticket/generate` must be idempotent on `holdID`:

- If ticket already exists for hold, return existing ticket (200) or explicit idempotent response.
- Do not create duplicate tickets for the same hold.

---

## 5. Step-by-Step Implementation in OutSystems

## 5.1 Create the OutSystems app/module

1. In ODC Studio (or Service Studio for O11), create a new application:
   - Name: `TicketBlitz_ETicket`.
2. Create one backend-focused module (or app component) for API exposure:
   - Name: `ETicket_API`.
3. Ensure module is server-side logic focused (no UI required).
4. Publish once to initialize runtime artifacts.

## 5.2 Create configuration Site Properties (secrets/config)

Create these Site Properties in `ETicket_API`:

1. `InternalApiKey` (Text, Secret = Yes)
   - used by internal TicketBlitz callers.
2. `AllowedIssuer` (Text)
   - for JWT mode later.
3. `AllowedAudience` (Text)
   - for JWT mode later.
4. `EnableRequestLogging` (Boolean, default `True` in non-prod).
5. `ApiVersion` (Text, default `v1`).

After publish:

1. Set effective values in runtime portal.
2. Never hardcode secrets in actions.

## 5.3 Model E-Ticket data entities

Create these entities in OutSystems local DB.

### Entity 1: `ETicket`

Attributes:

1. `Id` (default identifier, auto).
2. `TicketId` (Text, mandatory, unique) - external ticket ID (UUID string).
3. `HoldId` (Text, mandatory, unique).
4. `TransactionId` (Text, nullable).
5. `UserId` (Text, mandatory).
6. `EventId` (Text, mandatory).
7. `SeatId` (Text, mandatory).
8. `SeatNumber` (Text, mandatory, length <= 20).
9. `Status` (Text, mandatory, length <= 40).
10. `IssuedAt` (DateTime, mandatory).
11. `UsedAt` (DateTime, nullable).
12. `CancelledAt` (DateTime, nullable).
13. `SourceCorrelationId` (Text, nullable).
14. `PayloadHash` (Text, nullable).
15. `MetadataJson` (Long Text, nullable).
16. `CreatedAt` (DateTime, mandatory).
17. `UpdatedAt` (DateTime, mandatory).

### Entity 2: `ETicketEventLog` (optional but strongly recommended)

Attributes:

1. `Id`.
2. `EventName` (Text).
3. `TicketId` (Text).
4. `HoldId` (Text).
5. `CorrelationId` (Text).
6. `RequestBody` (Long Text).
7. `ResponseBody` (Long Text).
8. `Outcome` (Text).
9. `CreatedAt` (DateTime).

Use this for traceability and replay diagnosis.

## 5.4 Create indexes and constraints

In OutSystems entity index settings:

1. Unique index on `ETicket.TicketId`.
2. Unique index on `ETicket.HoldId`.
3. Non-unique index on `ETicket.UserId`.
4. Non-unique index on `ETicket.EventId`.
5. Non-unique composite index on `(EventId, Status)`.
6. Optional index on `SourceCorrelationId`.

Publish module after index creation.

## 5.5 Create reusable server actions and utilities

Create these server actions before exposing REST methods.

1. `NowUtc()`
   - Return current UTC datetime.
2. `GenerateTicketId()`
   - Return UUID string (or GUID-style unique string).
3. `NormalizeStatus(InputStatus)`
   - Uppercase + trim + validate against allowed values.
4. `ComputePayloadHash(InputText)`
   - Optional idempotency diagnostics.
5. `BuildErrorResponse(Code, Message, Details)`
   - Standard error payload structure.
6. `LogApiEvent(...)`
   - Insert into `ETicketEventLog` when logging enabled.

## 5.6 Expose the REST API service

1. Go to Logic -> Integrations -> REST.
2. Select `Expose REST API`.
3. Name it `v1` (versioned naming best practice).
4. Set Authentication to `Custom`.
5. Create callbacks:
   - `OnAuthentication`
   - `OnRequest` (optional, recommended)
   - `OnResponse` (recommended)

## 5.7 Implement custom authentication (`OnAuthentication`)

Implement API key validation first (fastest path), then optional JWT.

API key mode steps:

1. Read header `X-Internal-Token` or `X-API-Key` via request-header utility.
2. Compare against `InternalApiKey` Site Property.
3. If missing/invalid:
   - raise custom auth exception.
   - set status code 401.
4. If valid:
   - continue.

JWT mode later:

1. Read `Authorization` header.
2. Parse bearer token.
3. Validate signature and claims (`iss`, `aud`, `exp`).
4. Return 401 for invalid token, 403 for insufficient permission.

## 5.8 Implement `POST /eticket/generate`

### Method definition

1. HTTP Method: `POST`
2. Name: `GenerateETicket`
3. URL Path: `/eticket/generate`
4. Input structure (`GenerateETicketRequest`):
   - `holdID` (Text, mandatory)
   - `transactionID` (Text, optional)
   - `userID` (Text, mandatory)
   - `eventID` (Text, mandatory)
   - `seatID` (Text, mandatory)
   - `seatNumber` (Text, mandatory)
   - `correlationID` (Text, optional)
   - `metadata` (Text, optional JSON)
5. Output structure (`GenerateETicketResponse`):
   - `ticketID`
   - `holdID`
   - `status`
   - `issuedAt`
   - `seatNumber`

### Action flow steps

1. Validate mandatory fields.
2. Query `ETicket` by `HoldId`.
3. If exists:
   - return existing ticket payload.
   - set HTTP 200.
   - log as idempotent hit.
4. If not exists:
   - create new `ETicket` record:
     - `TicketId = GenerateTicketId()`
     - `Status = VALID`
     - timestamps from `NowUtc()`.
   - set HTTP 201 using `Response_SetStatusCode` (ODC) or equivalent.
5. Return full response payload.
6. Log request/response outcome.

### Error behavior

1. Bad payload -> 400.
2. Internal create failure -> 500.

## 5.9 Implement `GET /eticket/hold/{holdID}`

### Method definition

1. HTTP Method: `GET`
2. Name: `GetETicketByHold`
3. URL Path: `/eticket/hold/{holdID}`
4. Input: `holdID` from URL (mandatory).
5. Output:
   - `ticketID`
   - `holdID`
   - `userID`
   - `eventID`
   - `seatID`
   - `seatNumber`
   - `status`
   - `issuedAt`

### Action flow steps

1. Read holdID.
2. Query `ETicket` by `HoldId`.
3. If found:
   - return ticket payload (200).
4. If not found:
   - return error payload.
   - set 404.

## 5.10 Implement `GET /eticket/validate`

This replaces Scenario 3 gRPC `ValidateTicket`.

### Method definition

1. HTTP Method: `GET`
2. Name: `ValidateTicketOwnership`
3. URL Path: `/eticket/validate`
4. Query inputs:
   - `ticketID` (mandatory)
   - `userID` (mandatory)
5. Output:
   - `valid` (Boolean)
   - `reason` (Text)
   - `status` (Text)

### Action flow steps

1. Query ticket by `TicketId`.
2. If not found:
   - return `valid=false`, `reason=TICKET_NOT_FOUND`, status 404.
3. If found but `Status <> VALID`:
   - return `valid=false`, reason from status, HTTP 409.
4. If found and owner mismatch:
   - return `valid=false`, `reason=OWNER_MISMATCH`, HTTP 403.
5. If found and owner matches and status valid:
   - return `valid=true`, `reason=OK`, HTTP 200.

## 5.11 Implement `PUT /tickets/status/{ticketID}`

### Method definition

1. HTTP Method: `PUT`
2. Name: `UpdateTicketStatus`
3. URL Path: `/tickets/status/{ticketID}`
4. Input structure:
   - `status` (mandatory)
   - `reason` (optional)
   - `correlationID` (optional)
5. Output:
   - `ticketID`
   - `oldStatus`
   - `newStatus`
   - `updatedAt`

### Action flow steps

1. Validate target status is one of allowed values.
2. Fetch ticket by `ticketID`.
3. If not found -> 404.
4. Validate transition rules, for example:
   - `VALID -> USED` allowed.
   - `VALID -> CANCELLED` allowed.
   - `CANCELLATION_IN_PROGRESS -> CANCELLED` allowed.
   - `USED -> VALID` not allowed.
5. Update status and timestamp fields.
6. Return updated response 200.

## 5.12 Implement `POST /etickets/update`

Use this for Scenario 3 transfer/cancellation orchestration compatibility.

### Method definition

1. HTTP Method: `POST`
2. Name: `UpdateETickets`
3. URL Path: `/etickets/update`
4. Input structure should support:
   - `oldTicketID` (mandatory)
   - `newOwnerUserID` (optional)
   - `newHoldID` (optional)
   - `newSeatID` (optional)
   - `newSeatNumber` (optional)
   - `operation` (`CANCEL_ONLY` or `TRANSFER_AND_REISSUE`)
   - `correlationID` (optional)
5. Output:
   - `operation`
   - `oldTicketStatus`
   - `newTicketID` (if reissued)

### Action flow steps

1. Validate operation type.
2. Load old ticket.
3. If old ticket missing -> 404.
4. Set old ticket status:
   - `CANCELLATION_IN_PROGRESS` then `CANCELLED` (or immediate cancel based on orchestration state).
5. If operation is transfer/reissue:
   - create new ticket with `VALID` status and new owner/hold/seat context.
6. Return result.

---

## 6. Request/Response Payload Templates

## 6.1 `POST /eticket/generate` request

```json
{
  "holdID": "4ff3d8d8-5d9a-4f85-a2f0-8c79bd6e4f8a",
  "transactionID": "c236e2a7-11e2-4908-a349-2123197c8a4f",
  "userID": "c0c1f64a-91de-4c3a-bfa9-9e8d1a5e2f84",
  "eventID": "0f7f57e2-62c1-4df9-a5d9-8d95464d9d34",
  "seatID": "a7ca1f5a-b2a4-4a03-95cb-b0bb5e72d61d",
  "seatNumber": "D12",
  "correlationID": "6cc78a27-a2f6-4b0b-bfa4-ae818450e0c4",
  "metadata": "{\"source\":\"booking-fulfillment-orchestrator\"}"
}
```

## 6.2 `POST /eticket/generate` response

```json
{
  "ticketID": "d38e6f41-e18f-4c6b-aa5a-6f4a1cb4b2b7",
  "holdID": "4ff3d8d8-5d9a-4f85-a2f0-8c79bd6e4f8a",
  "status": "VALID",
  "issuedAt": "2026-04-02T12:15:10Z",
  "seatNumber": "D12"
}
```

## 6.3 `GET /eticket/validate` response (invalid owner)

```json
{
  "valid": false,
  "reason": "OWNER_MISMATCH",
  "status": "VALID"
}
```

---

## 7. Integrate TicketBlitz Backend with OutSystems

Because your backend currently has no OutSystems call sites, wire these next.

## 7.1 Environment variable contract (backend)

Use existing root `.env` keys:

1. `OUTSYSTEMS_BASE_URL=https://<your-outsystems-host>`
2. `OUTSYSTEMS_API_KEY=<secret>`

## 7.2 Booking Fulfillment integration point

In Booking Fulfillment flow (when payment confirmed and hold confirmed):

1. Call `POST {OUTSYSTEMS_BASE_URL}/<rest-base>/eticket/generate`.
2. Pass `X-Internal-Token` or configured auth header.
3. Include correlation ID from message context.
4. Treat 200 and 201 as success.
5. Persist returned `ticketID` in fulfillment state/payload for downstream notification.

## 7.3 Booking Status integration point

For `GET /booking-status/{holdID}` composite read:

1. Call `GET .../eticket/hold/{holdID}`.
2. If 200 and status is `VALID` (or `USED` as needed), include `ticketID` in response.
3. If 404, treat as still processing unless other failure signals exist.

## 7.4 Cancellation integration point

Replace gRPC validation with:

1. `GET /eticket/validate?ticketID={ticketID}&userID={userID}`.
2. Use `PUT /tickets/status/{ticketID}` for cancellation state transitions.
3. Use `POST /etickets/update` for transfer/reissue flow if needed.

---

## 8. Kong Exposure Strategy

Choose one of these models:

1. Internal service-to-service direct call (recommended first):
   - Orchestrators call OutSystems URL directly.
   - No public Kong route required.
2. Kong-proxied route (if you need centralized policy):
   - Add Kong service for OutSystems host.
   - Add internal route prefix like `/internal/eticket/*`.
   - Apply key-auth/ACL and rate limit policies.

Given your setup, direct internal call is simpler for first implementation.

---

## 9. Validation Using Live Supabase Data

Use Supabase to fetch realistic test inputs.

## 9.1 Get a confirmed hold with seat context

```sql
select
  h.hold_id,
  h.user_id,
  h.event_id,
  h.seat_id,
  s.seat_number,
  t.transaction_id
from seat_holds h
join seats s on s.seat_id = h.seat_id
left join transactions t on t.hold_id = h.hold_id
where h.status = 'CONFIRMED'
order by h.updated_at desc
limit 1;
```

## 9.2 Generate ticket test

1. Build `POST /eticket/generate` payload using row above.
2. Call endpoint once -> expect 201 (new).
3. Call same payload again -> expect 200 idempotent response with same `ticketID`.

## 9.3 Booking status test

1. Call `GET /eticket/hold/{holdID}`.
2. Expect 200 and consistent ticket payload.

## 9.4 Validation test

1. Call validate with matching user -> expect `valid=true`.
2. Call validate with different user -> expect 403 and `OWNER_MISMATCH`.

## 9.5 Cancellation test

1. Call `PUT /tickets/status/{ticketID}` to `CANCELLATION_IN_PROGRESS`.
2. Then `CANCELLED`.
3. Verify final status via `GET /eticket/hold/{holdID}`.

---

## 10. Recommended Error Model

Use consistent error payloads:

```json
{
  "error": {
    "code": "TICKET_NOT_FOUND",
    "message": "No ticket exists for holdID",
    "details": "holdID=<value>",
    "correlationID": "<value>"
  }
}
```

Map common error codes:

1. 400: `INVALID_REQUEST`
2. 401: `UNAUTHORIZED`
3. 403: `FORBIDDEN`
4. 404: `TICKET_NOT_FOUND`
5. 409: `INVALID_STATUS_TRANSITION`
6. 500: `INTERNAL_ERROR`

---

## 11. Optional Async and Ops Enhancements (OutSystems Timers)

After base API is stable, add timers for maintenance:

1. `ReconciliationTimer`
   - Finds tickets in `CANCELLATION_IN_PROGRESS` too long.
   - Emits alert/log event.
2. `RetentionTimer`
   - Archives old `ETicketEventLog` rows.
3. `HealthSnapshotTimer`
   - Writes periodic operational heartbeat records.

Timer best practices from ODC docs:

1. Keep timer runs short.
2. Use checkpoint/restart pattern for long work.
3. Avoid long-running monolithic jobs.

---

## 12. Versioning and Backward Compatibility Plan

Start with API `v1` now.

When changing contract-breaking parts, create `v2` instead of mutating `v1`, especially for:

1. Endpoint path changes.
2. Authentication model changes.
3. Mandatory field changes.
4. Data type changes.

This aligns with OutSystems microservice versioning recommendations.

---

## 13. Step-by-Step Rollout Plan for Your Team

## Phase A - OutSystems build

1. Build entities and indexes.
2. Build server actions/utilities.
3. Expose REST with custom auth.
4. Implement all 5 endpoints.
5. Publish and verify Swagger docs.

## Phase B - Integration wiring

1. Set `OUTSYSTEMS_BASE_URL` and API key in `.env`.
2. Implement calls in Booking Fulfillment/Booking Status/Cancellation services.
3. Add retry policy and timeout on HTTP calls.
4. Add structured logs with correlation IDs.

## Phase C - End-to-end test

1. Scenario 1A: confirmed booking -> ticket generated.
2. Scenario 1C: waitlist offer payment -> ticket generated.
3. Scenario 1D: timeout path -> no ticket generated.
4. Scenario 3: cancellation validation and status transitions.

## Phase D - Documentation update

1. Update `docs/Scenarios.md` to remove remaining gRPC references.
2. Update API tables to UUID fields (not INT).
3. Add final OutSystems endpoint base path and auth header standard.

---

## 14. Exact Fixes Needed in Scenario Documentation

Apply these content corrections immediately:

1. Replace all Scenario 3 `gRPC ValidateTicket` mentions with REST validation endpoint.
2. Standardize E-Ticket API table to:
   - `POST /eticket/generate`
   - `GET /eticket/hold/{holdID}`
   - `GET /eticket/validate`
   - `PUT /tickets/status/{ticketID}`
   - `POST /etickets/update`
3. Replace INT-style IDs with UUID strings.
4. Mark OutSystems DB as source of truth for ticket records.

---

## 15. Appendix A - Supabase Context Snapshot Used for Design

Project: `cpxcpvcfbohvpiubbujg`

Confirmed relevant facts:

1. No `eticket`/`ticket` table currently exists in public schema.
2. UUID-based identities throughout core entities.
3. Hold/payment/waitlist/cancellation enums already implemented and populated.
4. Existing indexes already optimize critical upstream workflows.
5. Therefore E-Ticket service must be an external bounded context, not an extra table bolted onto current Supabase core.

---

## 16. Appendix B - Context7 References Used

Primary references pulled via Context7:

1. `/outsystems/docs-product`
   - Expose REST API
   - Customize REST URLs
   - Add custom authentication
   - Change HTTP status code
   - Throw custom error
   - Token-based auth pattern
   - Site properties and secret handling
   - Index/entity modeling
2. `/outsystems/docs-odc`
   - Exposing REST APIs (ODC)
   - Method execution flow
   - Custom auth and token pattern
   - Response status customization (`Response_SetStatusCode`)
   - Timer/background job behavior

---

## 17. Definition of Done Checklist

Use this checklist to confirm completion.

1. OutSystems app published with `v1` REST API.
2. All required endpoints available and documented in generated Swagger.
3. Custom auth enforced (no public unauthenticated access).
4. Idempotent generation verified (same `holdID` does not duplicate tickets).
5. Booking status can fetch by `holdID`.
6. Cancellation flow can validate and update ticket status via REST.
7. Scenario docs aligned to REST-only E-Ticket protocol.
8. End-to-end tests pass for Scenario 1 and Scenario 3 ticket states.

If all 8 are complete, your E-Ticket service is implementation-ready for presentation and integration.
