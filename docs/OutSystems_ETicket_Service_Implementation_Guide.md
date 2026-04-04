# TicketBlitz OutSystems E-Ticket Service Implementation Guide

## 0. What This Guide Is

This is a full, beginner-safe implementation guide for the TicketBlitz E-Ticket service in OutSystems 11.55.65.

Follow the steps in order. Do not skip ahead. Publish after each major checkpoint.

This guide restores the canonical flow that supports these endpoints:

1. `POST /eticket/generate`
2. `GET /eticket/hold/{holdID}`
3. `GET /eticket/validate`
4. `PUT /etickets/status/{ticketID}`
5. `POST /etickets/update`

---

## 1. Confirm the Contract Before Building

The E-Ticket service must be REST-based and external to Docker.

Use UUID-style text IDs end to end. Do not introduce INT IDs into the E-Ticket flow.

The service must support:

1. Ticket generation after booking confirmation.
2. Hold lookup for booking-status polling.
3. Ownership validation for cancellation and transfer flows.
4. Ticket status updates.
5. Ticket transfer and reissue updates.

The source of truth for ticket records is the OutSystems service itself.

---

## 2. Build the Contracts Module First

Create or use a shared contracts module named `TB_Fnd_Contracts`.

Create these structures exactly.

### 2.1 GenerateETicketRequest

1. `holdID` (Text, Required)
2. `transactionID` (Text, Optional)
3. `userID` (Text, Required)
4. `eventID` (Text, Required)
5. `seatID` (Text, Required)
6. `seatNumber` (Text, Required)
7. `correlationID` (Text, Optional)
8. `metadata` (Text, Optional)

### 2.2 GenerateETicketResponse

1. `ticketID` (Text, Required)
2. `holdID` (Text, Required)
3. `status` (Text, Required)
4. `issuedAt` (DateTime, Required)
5. `seatNumber` (Text, Required)

### 2.3 GetETicketByHoldResponse

1. `ticketID` (Text, Required)
2. `holdID` (Text, Required)
3. `userID` (Text, Required)
4. `eventID` (Text, Required)
5. `seatID` (Text, Required)
6. `seatNumber` (Text, Required)
7. `status` (Text, Required)
8. `issuedAt` (DateTime, Required)

### 2.4 ValidateTicketResponse

1. `valid` (Boolean, Required)
2. `reason` (Text, Required)
3. `status` (Text, Required)

### 2.5 UpdateTicketStatusRequest

1. `status` (Text, Required)
2. `correlationID` (Text, Optional)

### 2.6 UpdateTicketStatusResponse

1. `ticketID` (Text, Required)
2. `oldStatus` (Text, Required)
3. `newStatus` (Text, Required)
4. `updatedAt` (DateTime, Required)

### 2.7 UpdateETicketsRequest

1. `oldTicketID` (Text, Required)
2. `newOwnerUserID` (Text, Optional)
3. `newHoldID` (Text, Optional)
4. `newSeatID` (Text, Optional)
5. `newSeatNumber` (Text, Optional)
6. `operation` (Text, Required)
7. `correlationID` (Text, Optional)
8. `newTransactionID` (Text, Optional)

### 2.8 UpdateETicketsResponse

1. `operation` (Text, Required)
2. `oldTicketStatus` (Text, Required)
3. `newTicketID` (Text, Optional)

### 2.9 ApiError

1. `code` (Text, Required)
2. `message` (Text, Required)
3. `details` (Text, Optional)
4. `correlationID` (Text, Optional)

Publish `TB_Fnd_Contracts` after creating the structures.

---

## 3. Create the Core Module

Create a Service module named `TB_Core_ETicket`.

After the module is created:

1. Publish once.
2. Open Manage Dependencies.
3. Import the structures from `TB_Fnd_Contracts`.
4. Apply dependencies.
5. Publish again.

The core module owns the database entities and server logic.

---

## 4. Create Entities and Indexes

Create these entities in `TB_Core_ETicket`.

### 4.1 Static Entity: ETicketStatus

Create these records:

1. `VALID`
2. `USED`
3. `CANCELLED`
4. `CANCELLATION_IN_PROGRESS`

### 4.2 Entity: ETicket

Create these attributes:

1. `TicketId` (Text)
2. `HoldId` (Text)
3. `TransactionId` (Text)
4. `UserId` (Text)
5. `EventId` (Text)
6. `SeatId` (Text)
7. `SeatNumber` (Text)
8. `Status` (Text)
9. `IssuedAt` (DateTime)
10. `UsedAt` (DateTime)
11. `CancelledAt` (DateTime)
12. `SourceCorrelationId` (Text)
13. `PayloadHash` (Text)
14. `MetadataJson` (Text, use large text length if needed)
15. `CreatedAt` (DateTime)
16. `UpdatedAt` (DateTime)

### 4.3 Entity: ETicketEventLog

Create these attributes:

1. `EventName` (Text)
2. `TicketId` (Text)
3. `HoldId` (Text)
4. `CorrelationId` (Text)
5. `RequestBody` (Text)
6. `ResponseBody` (Text)
7. `Outcome` (Text)
8. `CreatedAt` (DateTime)

### 4.4 Indexes

Create these indexes:

1. Unique index on `ETicket.TicketId`
2. Unique index on `ETicket.HoldId`
3. Non-unique index on `ETicket.UserId`
4. Non-unique index on `ETicket.EventId`
5. Optional non-unique index on `SourceCorrelationId`

Publish after adding indexes.

---

## 5. Create Reusable Server Actions

Create these server actions before exposing REST methods.

### 5.1 NowUtc

1. Create a server action named `NowUtc`.
2. Add one output parameter: `UtcNow` (DateTime).
3. Add an Assign node.
4. Set `UtcNow = CurrDateTime()`.
5. End the action.

### 5.2 GenerateTicketId

1. Create a server action named `GenerateTicketId`.
2. Add one output parameter: `TicketId` (Text).
3. Add an Assign node.
4. Set `TicketId = GenerateGuid()`.
5. End the action.

If `GenerateGuid()` is not available in your build, use the equivalent UUID helper available in your environment, but keep the same output contract.

### 5.3 NormalizeTicketStatus

1. Create a server action named `NormalizeTicketStatus`.
2. Inputs:
   - `StatusIn` (Text)
3. Outputs:
   - `StatusOut` (Text)
   - `IsValid` (Boolean)
4. Add an Assign node.
5. Set:
   - `StatusOut = ToUpper(Trim(StatusIn))`
   - `IsValid = False`
6. Add an If node.
7. Condition:
   - `StatusOut = "VALID" or StatusOut = "USED" or StatusOut = "CANCELLED" or StatusOut = "CANCELLATION_IN_PROGRESS"`
8. True branch:
   - Set `IsValid = True`
9. End the action.

### 5.4 BuildApiError

1. Create a server action named `BuildApiError`.
2. Inputs:
   - `Code` (Text)
   - `Message` (Text)
   - `Details` (Text)
   - `CorrelationID` (Text)
3. Output:
   - `ErrorOut` (ApiError)
4. Add an Assign node.
5. Map:
   - `ErrorOut.code = Code`
   - `ErrorOut.message = Message`
   - `ErrorOut.details = Details`
   - `ErrorOut.correlationID = CorrelationID`
6. End the action.

### 5.5 LogApiEvent

1. Create a server action named `LogApiEvent`.
2. Inputs:
   - `EventName` (Text)
   - `TicketId` (Text)
   - `HoldId` (Text)
   - `CorrelationId` (Text)
   - `RequestBody` (Text)
   - `ResponseBody` (Text)
   - `Outcome` (Text)
3. Local variable:
   - `NewLog` (ETicketEventLog)
4. Add an If node.
5. Condition:
   - `Site.EnableRequestLogging = False`
6. True branch:
   - End the action.
7. False branch:
   - Add an Assign node.
   - Map all fields from inputs into `NewLog`.
   - Call `NowUtc`.
   - Set `NewLog.CreatedAt = NowUtc.UtcNow`.
   - Create the `ETicketEventLog` record using `NewLog` as source.
8. End the action.

Logging usage rule (mandatory):

1. Call `LogApiEvent` on every terminal branch in every REST method.
2. A terminal branch means any branch that ends the method with `OutBody`.
3. This includes:
   - success branches (`200`, `201`)
   - validation/business error branches (`400`, `403`, `404`, `409`)
   - `AllExceptions` handler branches (`500`)
4. Keep `Outcome` machine-readable. Recommended format:
   - `"<HTTP_STATUS>|<RESULT_CODE>"`
   - Examples: `"200|OK"`, `"201|CREATED"`, `"400|INVALID_REQUEST"`, `"404|TICKET_NOT_FOUND"`, `"409|INVALID_TRANSITION"`, `"500|INTERNAL_ERROR"`
5. For error branches, use `BuildApiError` output values when setting `Outcome` and `ResponseBody`.
6. Do not log secrets/tokens. If request payload includes sensitive fields, mask or omit them before logging.
7. If `RequestBody` or `ResponseBody` can become large, truncate to a safe maximum size before logging.

### 5.6 ValidateRequiredText

1. Create a server action named `ValidateRequiredText`.
2. Inputs:
   - `Value` (Text)
   - `FieldName` (Text)
3. Outputs:
   - `IsValid` (Boolean)
   - `ErrorMessage` (Text)
4. Add an Assign node.
5. Set:
   - `IsValid = True`
   - `ErrorMessage = ""`
6. Add an If node.
7. Condition:
   - `Trim(Value) = ""`
8. True branch:
   - Set `IsValid = False`
   - Set `ErrorMessage = FieldName + " is required"`
9. End the action.

Publish after creating all reusable actions.

---

## 6. Expose the REST API

1. Go to Logic tab.
2. Under Integrations, right-click REST and choose Expose REST API.
3. Set API Name to `v1`.
4. Set Authentication to `Custom`.
5. Create callback actions:
   - `OnAuthentication`
   - `OnRequest`
   - `OnResponse`
6. Publish once so the callback nodes appear.

If `OnAuthentication` is not shown in your build, keep `Custom` authentication and move token validation into `OnRequest`.

### 6.1 OnAuthentication

1. Open `REST > v1 > OnAuthentication`.
2. If your build exposes username/password inputs, compare the incoming password to `Site.InternalApiKey`.
3. If invalid, add Assign `Response.status = 401` and raise an unauthorized error.
4. If valid, end normally.

### 6.2 OnRequest

1. Open `REST > v1 > OnRequest`.
2. Add local variables:
   - `Token` (Text)
   - `CorrelationId` (Text)
3. Read headers using the HTTP request header helper available in your build.
4. Validate token against `Site.InternalApiKey`.
5. If invalid, set 401 and raise unauthorized.
6. If correlation ID is missing, generate one with `GenerateGuid()`.
7. End the action.

### 6.3 OnResponse

1. Open `REST > v1 > OnResponse`.
2. Add an Assign node.
3. Set `CustomizedResponse = Response`.
4. Optionally set headers like `X-API-Version` and request ID.
5. End the action.

Publish after callbacks are created.

---

## 6.4 CRITICAL: HTTP Status Codes in REST Endpoint Methods — The Correct Approach

**IMPORTANT:** In OutSystems 11.55.65, you set HTTP status codes using the **`SetStatusCode` action from the `HTTPRequestHandler` extension**, NOT through End node properties or Assign statements.

### The Correct Pattern

In every REST endpoint method, before the End node, you must:

1. **Call `HTTPRequestHandler.SetStatusCode()`** with an integer status code
2. Then **End with your output parameter** (`OutBody` — the only output parameter)

### How to Use SetStatusCode

**Action:** `HTTPRequestHandler.SetStatusCode()`

**Input Parameter:**

- `StatusCode` (Integer) — the HTTP status code to return

**Available Status Codes:**

- `200` — OK (success)
- `201` — Created (resource created)
- `400` — Bad Request (validation error)
- `404` — Not Found (resource not found)
- `409` — Conflict (invalid state transition)
- `500` — Internal Server Error

### Concrete Flow Example

**For success path** (ticket found, validation passed):

```
1. (Assign all fields to OutBody)
2. Add Action node: call HTTPRequestHandler.SetStatusCode
   → Set input parameter: StatusCode = 200
3. End with OutBody
```

**For validation error path** (invalid input):

```
1. Call BuildApiError (populate error details)
2. Add Assign and map OutBody fields for this endpoint (field-by-field; do not assign whole structure)
3. Add Action node: call HTTPRequestHandler.SetStatusCode
   → Set input parameter: StatusCode = 400
4. End with OutBody
```

**For not found path** (ticket/hold doesn't exist):

```
1. Call BuildApiError (populate "not found" error)
2. Add Assign and map OutBody fallback fields for this endpoint (field-by-field; do not assign whole structure)
3. Add Action node: call HTTPRequestHandler.SetStatusCode
   → Set input parameter: StatusCode = 404
4. End with OutBody
```

### Important Implementation Notes

- **`SetStatusCode` must be called before the End node** on each path
- Each different outcome (2xx, 4xx, 5xx) should have its own `SetStatusCode` call immediately before its End node
- The framework combines:
  - The `StatusCode` integer → HTTP status code sent to client
  - The `OutBody` variable you End with → JSON response body
- Do NOT try to use `Response.status` or End node properties — use `SetStatusCode` only

---

## 7. Implement Step 9: POST /eticket/generate

This is the most important method. Build it carefully and in exact order.

### 7.1 Method definition

1. Open `REST > v1 > GenerateETicket`.
2. Confirm input parameter is `Request` of type `GenerateETicketRequest`.
3. Rename/confirm output parameter as `OutBody` of type `GenerateETicketResponse`.
4. Add local variables:
   - `CorrelationId` (Text)
   - `ExistingTicket` (ETicket record)
   - `NormalizedMetadata` (Text)

**CRITICAL REMINDER: See Section 6.4**

To set HTTP status codes in this method:

- **Call `HTTPRequestHandler.SetStatusCode()`** before the End node
- Pass the HTTP status code as an integer (200, 201, 400, 404, 409, 500)
- Each different outcome (success, error, etc.) will call SetStatusCode with its own code, then End

### 7.2 Build the flow

1. Start.
2. Add Assign.
3. Set:
   - `CorrelationId = Request.correlationID`
   - `NormalizedMetadata = Request.metadata`
4. Add If.
5. Condition:
   - `Trim(CorrelationId) = ""`
6. True branch:
   - Add Assign.
   - Set `CorrelationId = GenerateGuid()`
   - Then connect this branch to Step 7.3.
7. False branch:
   - Connect this branch to Step 7.3.

### 7.3 Validate required fields one by one

Place this block immediately after Step 7.2 and before Step 7.4 (`GetTicketByHold`). Both the True branch and False branch of the CorrelationId decision must end at the same first validation node in Step 7.3.

**Status code rule for this guide:** When a step says "set status code to XXX", **call `HTTPRequestHandler.SetStatusCode(XXX)` before the End node** (400, 404, 200, 201, 500, etc.).

**End node rule for this guide:**

1. In OutSystems 11.55.65, you call `HTTPRequestHandler.SetStatusCode()` with an integer status code before the End node.
2. When a step says `End with OutBody`, it means:
   - Make sure you already assigned values into the output parameter variable `OutBody`
   - Add an Action node that calls `HTTPRequestHandler.SetStatusCode(XXX)`
   - Connect to an End node returning `OutBody`
3. When an error occurs, assign the error to `OutBody`:
   - For errors, map `OutBody` field-by-field using endpoint-safe fallback values
   - Add an Action node that calls `HTTPRequestHandler.SetStatusCode(XXX)`
   - Connect to an End node returning `OutBody`
4. Different paths can share the same status code if they're semantically the same (e.g., all validation errors can use 400).

Create the validation nodes in this exact order:

1. `Request.holdID`
2. `Request.userID`
3. `Request.eventID`
4. `Request.seatID`
5. `Request.seatNumber`

For each field, build the same concrete node sequence below.

### 7.3.1 Validate `Request.holdID`

1. Call `ValidateRequiredText`.
2. Map `Value = Request.holdID`.
3. Map `FieldName = "holdID"`.
4. Add a Decision node on `ValidateRequiredText.IsValid`.
5. If `False`, call `BuildApiError`.
6. Set `Code = "INVALID_REQUEST"`.
7. Set `Message = ValidateRequiredText.ErrorMessage`.
8. Set `Details = "holdID"`.
9. Set `CorrelationID = CorrelationId`.
10. Assign `OutBody` with fallback values:

- `OutBody.ticketID = ""`
- `OutBody.holdID = Request.holdID`
- `OutBody.status = "INVALID_REQUEST"`
- `OutBody.issuedAt = NullDate()`
- `OutBody.seatNumber = Request.seatNumber`

11. Call `HTTPRequestHandler.SetStatusCode(400)`.
12. End with `OutBody`.
13. If `True`, continue to Step 7.3.2.

### 7.3.2 Validate `Request.userID`

1. Call `ValidateRequiredText`.
2. Map `Value = Request.userID`.
3. Map `FieldName = "userID"`.
4. Add a Decision node on `ValidateRequiredText.IsValid`.
5. If `False`, call `BuildApiError`.
6. Set `Code = "INVALID_REQUEST"`.
7. Set `Message = ValidateRequiredText.ErrorMessage`.
8. Set `Details = "userID"`.
9. Set `CorrelationID = CorrelationId`.
10. Assign `OutBody` with fallback values:

- `OutBody.ticketID = ""`
- `OutBody.holdID = Request.holdID`
- `OutBody.status = "INVALID_REQUEST"`
- `OutBody.issuedAt = NullDate()`
- `OutBody.seatNumber = Request.seatNumber`

11. Call `HTTPRequestHandler.SetStatusCode(400)`.
12. End with `OutBody`.
13. If `True`, continue to Step 7.3.3.

### 7.3.3 Validate `Request.eventID`

1. Call `ValidateRequiredText`.
2. Map `Value = Request.eventID`.
3. Map `FieldName = "eventID"`.
4. Add a Decision node on `ValidateRequiredText.IsValid`.
5. If `False`, call `BuildApiError`.
6. Set `Code = "INVALID_REQUEST"`.
7. Set `Message = ValidateRequiredText.ErrorMessage`.
8. Set `Details = "eventID"`.
9. Set `CorrelationID = CorrelationId`.
10. Assign `OutBody` with fallback values:

- `OutBody.ticketID = ""`
- `OutBody.holdID = Request.holdID`
- `OutBody.status = "INVALID_REQUEST"`
- `OutBody.issuedAt = NullDate()`
- `OutBody.seatNumber = Request.seatNumber`

11. Call `HTTPRequestHandler.SetStatusCode(400)`.
12. End with `OutBody`.
13. If `True`, continue to Step 7.3.4.

### 7.3.4 Validate `Request.seatID`

1. Call `ValidateRequiredText`.
2. Map `Value = Request.seatID`.
3. Map `FieldName = "seatID"`.
4. Add a Decision node on `ValidateRequiredText.IsValid`.
5. If `False`, call `BuildApiError`.
6. Set `Code = "INVALID_REQUEST"`.
7. Set `Message = ValidateRequiredText.ErrorMessage`.
8. Set `Details = "seatID"`.
9. Set `CorrelationID = CorrelationId`.
10. Assign `OutBody` with fallback values:

- `OutBody.ticketID = ""`
- `OutBody.holdID = Request.holdID`
- `OutBody.status = "INVALID_REQUEST"`
- `OutBody.issuedAt = NullDate()`
- `OutBody.seatNumber = Request.seatNumber`

11. Call `HTTPRequestHandler.SetStatusCode(400)`.
12. End with `OutBody`.
13. If `True`, continue to Step 7.3.5.

### 7.3.5 Validate `Request.seatNumber`

1. Call `ValidateRequiredText`.
2. Map `Value = Request.seatNumber`.
3. Map `FieldName = "seatNumber"`.
4. Add a Decision node on `ValidateRequiredText.IsValid`.
5. If `False`, call `BuildApiError` with:
   - `Code = "INVALID_REQUEST"`
   - `Message = ValidateRequiredText.ErrorMessage`
   - `Details = "seatNumber"`
   - `CorrelationID = CorrelationId`
6. Assign `OutBody` with fallback values:
   - `OutBody.ticketID = ""`
   - `OutBody.holdID = Request.holdID`
   - `OutBody.status = "INVALID_REQUEST"`
   - `OutBody.issuedAt = NullDate()`
   - `OutBody.seatNumber = Request.seatNumber`
7. Call `HTTPRequestHandler.SetStatusCode(400)`.
8. End with `OutBody`.
9. If `True`, continue to Step 7.4.

Do not move to Step 7.4 until Step 7.3.5 has passed.

### 7.4 Check whether a ticket already exists for the hold

1. Add Aggregate named `GetTicketByHold`.
2. Source entity: `ETicket`.
3. Filter: `ETicket.HoldId = Request.holdID`.
4. Set Max Records to 1.
5. Add If node.
6. Condition:
   - `GetTicketByHold.List.Length > 0`

#### True branch: idempotent replay

1. Add Assign.
2. Set `ExistingTicket = GetTicketByHold.List.Current`.
3. Map output body:
   - `OutBody.ticketID = ExistingTicket.TicketId`
   - `OutBody.holdID = ExistingTicket.HoldId`
   - `OutBody.status = ExistingTicket.Status`
   - `OutBody.issuedAt = ExistingTicket.IssuedAt`
   - `OutBody.seatNumber = ExistingTicket.SeatNumber`
4. Call `LogApiEvent`.
5. Map the inputs exactly like this:
   - `EventName = "GenerateETicket"`
   - `TicketId = ExistingTicket.TicketId`
   - `HoldId = ExistingTicket.HoldId`
   - `CorrelationId = CorrelationId`
   - `RequestBody = Request.holdID + "|" + Request.userID + "|" + Request.eventID + "|" + Request.seatID + "|" + Request.seatNumber`
   - `ResponseBody = OutBody.ticketID + "|" + OutBody.holdID + "|" + OutBody.status + "|" + ToText(OutBody.issuedAt) + "|" + OutBody.seatNumber`
   - `Outcome = "IDEMPOTENT_REPLAY"`
6. Call `HTTPRequestHandler.SetStatusCode(200)`.
7. End with `OutBody`.

#### False branch: create a new ticket

1. Call `GenerateTicketId`.
2. Call `NowUtc`.
3. Call Create action for `ETicket` and fill the input fields with these values:
   - `TicketId = GenerateTicketId.TicketId`
   - `HoldId = Request.holdID`
   - `TransactionId = Request.transactionID`
   - `UserId = Request.userID`
   - `EventId = Request.eventID`
   - `SeatId = Request.seatID`
   - `SeatNumber = Request.seatNumber`
   - `Status = "VALID"`
   - `IssuedAt = NowUtc.UtcNow`
   - `UsedAt = NullDate()`
   - `CancelledAt = NullDate()`
   - `SourceCorrelationId = CorrelationId`
   - `PayloadHash = ""`
   - `MetadataJson = NormalizedMetadata`
   - `CreatedAt = NowUtc.UtcNow`
   - `UpdatedAt = NowUtc.UtcNow`

   The Create action will output only the `Id` of the created record, not the full record details.

4. Add an **Aggregate** to fetch the full created ETicket record:
   - Source: `ETicket` entity
   - Filter: `ETicket.TicketId = CreateETicket.Id` (or `ETicket.Id = CreateETicket.Id` if TicketId is not the primary key)
   - Name the aggregate output something like `GetCreatedETicket`

5. Add Assign.
6. Map `OutBody` field by field from the aggregated ETicket record:
   - `OutBody.ticketID = GetCreatedETicket.List.Current.ETicket.TicketId`
   - `OutBody.holdID = GetCreatedETicket.List.Current.ETicket.HoldId`
   - `OutBody.status = GetCreatedETicket.List.Current.ETicket.Status`
   - `OutBody.issuedAt = GetCreatedETicket.List.Current.ETicket.IssuedAt`
   - `OutBody.seatNumber = GetCreatedETicket.List.Current.ETicket.SeatNumber`

   (Adjust the path based on your aggregate's actual structure—use autocomplete `Ctrl+Space` to verify the correct path.)

7. Call `LogApiEvent`.
8. Map the inputs exactly like this:
   - `EventName = "GenerateETicket"`
   - `TicketId = GenerateTicketId.TicketId`
   - `HoldId = Request.holdID`
   - `CorrelationId = CorrelationId`
   - `RequestBody = Request.holdID + "|" + Request.userID + "|" + Request.eventID + "|" + Request.seatID + "|" + Request.seatNumber`
   - `ResponseBody = OutBody.ticketID + "|" + OutBody.holdID + "|" + OutBody.status + "|" + ToText(OutBody.issuedAt) + "|" + OutBody.seatNumber`
   - `Outcome = "CREATED"`
9. Call `HTTPRequestHandler.SetStatusCode(201)`.
10. End with `OutBody`.

### 7.5 Exception handler

1. In `GenerateETicket`, add an `AllExceptions` handler on the same action canvas (the standalone exception lane in the empty area is correct).
2. In the `AllExceptions` flow, call `BuildApiError` and map:
   - `Code = "500"`
   - `Message = "Internal server error."`
   - `Details = "Unexpected error in GenerateETicket."`
   - `CorrelationID = CorrelationId`
3. Add Assign with fallback values:
   - `OutBody.ticketID = ""`
   - `OutBody.holdID = Request.holdID`
   - `OutBody.status = "ERROR"`
   - `OutBody.issuedAt = NullDate()`
   - `OutBody.seatNumber = Request.seatNumber`
4. Call `HTTPRequestHandler.SetStatusCode(500)`.
5. End with `OutBody`.

Use this exception flow to catch unhandled runtime errors from create/log and other nodes in `GenerateETicket`.

### 7.6 Completion check

1. First POST for a holdID returns 201.
2. Second POST with same holdID returns 200.
3. Missing required field returns 400.

Publish after the method is complete.

---

## 8. Implement Step 10: GET /eticket/hold/{holdID}

### 8.1 Method definition

1. Open `REST > v1 > GetETicketByHold`.
2. Confirm input parameter `holdID` (Text).
3. The method has ONE output parameter. Name it `OutBody` of type `GetETicketByHoldResponse`.
4. This method returns only one output structure: `OutBody`. Always populate it with data (real data for success, fallback values for failure) and return it with the appropriate HTTP status code.
5. Add local variables:
   - `CorrelationId` (Text)
   - `FoundTicket` (ETicket record)

### 8.2 Build the flow

1. Start.
2. Add Assign.
3. Set `CorrelationId = GenerateGuid()`.
4. Call `ValidateRequiredText` for `holdID`.
5. Add a Decision node on `ValidateRequiredText.IsValid`.
6. If `False`, call `BuildApiError` and map:
   - `Code = "INVALID_REQUEST"`
   - `Message = ValidateRequiredText.ErrorMessage`
   - `Details = "holdID"`
   - `CorrelationID = CorrelationId`
7. Assign OutBody fallback values:
   - `OutBody.ticketID = ""`
   - `OutBody.holdID = holdID`
   - `OutBody.userID = ""`
   - `OutBody.eventID = ""`
   - `OutBody.seatID = ""`
   - `OutBody.seatNumber = ""`
   - `OutBody.status = "INVALID_REQUEST"`
   - `OutBody.issuedAt = NullDate()`
8. Call `HTTPRequestHandler.SetStatusCode(400)`.
9. End with `OutBody`.
10. If `True`, continue to the lookup path.
11. Add Aggregate `GetTicketByHold`.
12. Filter: `ETicket.HoldId = holdID`.
13. Set Max Records to 1.
14. Add If node with condition `GetTicketByHold.List.Length > 0`.

#### True branch

1. Add Assign.
2. Set `FoundTicket = GetTicketByHold.List.Current`.
3. Add another Assign node to map the response body fields:
   - `OutBody.ticketID = FoundTicket.TicketId`
   - `OutBody.holdID = FoundTicket.HoldId`
   - `OutBody.userID = FoundTicket.UserId`
   - `OutBody.eventID = FoundTicket.EventId`
   - `OutBody.seatID = FoundTicket.SeatId`
   - `OutBody.seatNumber = FoundTicket.SeatNumber`
   - `OutBody.status = FoundTicket.Status`
   - `OutBody.issuedAt = FoundTicket.IssuedAt`
4. Call `HTTPRequestHandler.SetStatusCode(200)`.
5. End with `OutBody`.

#### False branch

1. Call `BuildApiError` and map:
   - `Code = "TICKET_NOT_FOUND"`
   - `Message = "No ticket exists for holdID"`
   - `Details = "holdID=" + holdID`
   - `CorrelationID = CorrelationId`
2. Populate fallback values:
   - `OutBody.ticketID = ""`
   - `OutBody.holdID = holdID`
   - `OutBody.userID = ""`
   - `OutBody.eventID = ""`
   - `OutBody.seatID = ""`
   - `OutBody.seatNumber = ""`
   - `OutBody.status = "NOT_FOUND"` (safe fallback)
   - `OutBody.issuedAt = NullDate()`
3. Call `HTTPRequestHandler.SetStatusCode(404)`.
4. End with `OutBody`. The caller must check HTTP 404 status to interpret the error.

### 8.3 Completion check

1. Existing holdID returns 200.
2. Missing holdID returns 400.
3. Unknown holdID returns 404.

Publish after completion.

---

## 9. Implement Step 11: GET /eticket/validate

### 9.1 Method definition

1. Open `REST > v1 > ValidateTicketOwnership`.
2. Confirm inputs:
   - `ticketID` (Text)
   - `userID` (Text)
3. The method has ONE output parameter. Name it `OutBody` of type `ValidateTicketResponse`.
4. This method returns only one output structure: `OutBody`. Populate it with validation result data for all paths (success, failure, forbidden, conflict) and return it with the appropriate HTTP status code.
5. Add local variables:
   - `CorrelationId` (Text)
   - `FoundTicket` (ETicket record)

### 9.2 Build the flow

1. Start.
2. Set `CorrelationId = GenerateGuid()`.
3. Call `ValidateRequiredText` with `Value = ticketID` and `FieldName = "ticketID"`.
4. Add a Decision node on `ValidateRequiredText.IsValid`.
5. If `False`, call `BuildApiError` and map:
   - `Code = "INVALID_REQUEST"`
   - `Message = ValidateRequiredText.ErrorMessage`
   - `Details = "ticketID"`
   - `CorrelationID = CorrelationId`
6. Assign:
   - `OutBody.valid = False`
   - `OutBody.reason = "INVALID_REQUEST"`
   - `OutBody.status = "UNKNOWN"`
7. Call `HTTPRequestHandler.SetStatusCode(400)`.
8. End with `OutBody`.
9. Call `ValidateRequiredText` with `Value = userID` and `FieldName = "userID"`.
10. Add a Decision node on `ValidateRequiredText.IsValid`.
11. If `False`, call `BuildApiError` and map:

- `Code = "INVALID_REQUEST"`
- `Message = ValidateRequiredText.ErrorMessage`
- `Details = "userID"`
- `CorrelationID = CorrelationId`

12. Assign:

- `OutBody.valid = False`
- `OutBody.reason = "INVALID_REQUEST"`
- `OutBody.status = "UNKNOWN"`

13. Call `HTTPRequestHandler.SetStatusCode(400)`.
14. End with `OutBody`.
15. Add Aggregate `GetTicketById`.
16. Filter: `ETicket.TicketId = ticketID`.
17. Set Max Records to 1.
18. If no rows found:

- `OutBody.valid = False`
- `OutBody.reason = "TICKET_NOT_FOUND"`
- `OutBody.status = "UNKNOWN"` (safe fallback — ticket does not exist)
- Call `HTTPRequestHandler.SetStatusCode(404)`.
- End with `OutBody`.

19. If row found, assign `FoundTicket`.
20. If `FoundTicket.Status <> "VALID"`:

- `OutBody.valid = False`
- `OutBody.reason = FoundTicket.Status`
- `OutBody.status = FoundTicket.Status`
- Call `HTTPRequestHandler.SetStatusCode(409)`.
- End with `OutBody`.

21. If `FoundTicket.UserId <> userID`:

- `OutBody.valid = False`
- `OutBody.reason = "OWNER_MISMATCH"`
- `OutBody.status = FoundTicket.Status`
- Call `HTTPRequestHandler.SetStatusCode(403)`.
- End with `OutBody`.

22. Else:

- `OutBody.valid = True`
- `OutBody.reason = "OK"`
- `OutBody.status = "VALID"`
- Call `HTTPRequestHandler.SetStatusCode(200)`.
- End with `OutBody`.

### 9.3 Completion check

1. Valid owner returns 200 and `valid = true`.
2. Unknown ticket returns 404.
3. Non-VALID status returns 409.
4. Owner mismatch returns 403.

Publish after completion.

---

## 10. Implement Step 12: PUT /etickets/status/{ticketID}

### 10.1 Allowed transitions

1. `VALID -> USED`
2. `VALID -> CANCELLED`
3. `VALID -> CANCELLATION_IN_PROGRESS`
4. `CANCELLATION_IN_PROGRESS -> CANCELLED`

### 10.2 Disallowed transitions

1. `USED -> VALID`
2. `CANCELLED -> VALID`
3. Any undefined transition

### 10.3 Method definition

1. Open `REST > v1 > UpdateTicketStatus`.
2. Confirm inputs:
   - `ticketID` (Text)
   - `Request` (`UpdateTicketStatusRequest`)
3. The method has ONE output parameter. Name it `OutBody` of type `UpdateTicketStatusResponse`.
4. This method returns only one output structure: `OutBody`. Populate it with transition result data for all paths (success, failure, not found, conflict) and return it with the appropriate HTTP status code.
5. Add local variables:
   - `CorrelationId` (Text)
   - `NormalizedStatus` (Text)
   - `IsStatusValid` (Boolean)
   - `OldStatus` (Text)
   - `FoundTicket` (ETicket record)
   - `UpdateSource` (ETicket record)

### 10.4 Build the flow

1. Start.
2. Set `CorrelationId = Request.correlationID`.
3. If blank, set `CorrelationId = GenerateGuid()`.
4. Call `ValidateRequiredText` with `Value = ticketID` and `FieldName = "ticketID"`.
5. Add a Decision node on `ValidateRequiredText.IsValid`.
6. If `False`, call `BuildApiError` and map:
   - `Code = "INVALID_REQUEST"`
   - `Message = ValidateRequiredText.ErrorMessage`
   - `Details = "ticketID"`
   - `CorrelationID = CorrelationId`
     Then assign `OutBody.ticketID = ticketID`, `OutBody.oldStatus = "UNKNOWN"`, `OutBody.newStatus = "INVALID_REQUEST"`, `OutBody.updatedAt = NullDate()`, call `HTTPRequestHandler.SetStatusCode(400)`, and End with `OutBody`.
7. Call `ValidateRequiredText` with `Value = Request.status` and `FieldName = "status"`.
8. Add a Decision node on `ValidateRequiredText.IsValid`.
9. If `False`, call `BuildApiError` and map:
   - `Code = "INVALID_REQUEST"`
   - `Message = ValidateRequiredText.ErrorMessage`
   - `Details = "status"`
   - `CorrelationID = CorrelationId`
     Then assign `OutBody.ticketID = ticketID`, `OutBody.oldStatus = "UNKNOWN"`, `OutBody.newStatus = "INVALID_REQUEST"`, `OutBody.updatedAt = NullDate()`, call `HTTPRequestHandler.SetStatusCode(400)`, and End with `OutBody`.
10. Call `NormalizeTicketStatus`.
11. If `IsStatusValid = False`, call `BuildApiError` and map:

- `Code = "INVALID_STATUS"`
- `Message = "Unsupported status value"`
- `Details = "status=" + Request.status`
- `CorrelationID = CorrelationId`
  Then assign `OutBody.ticketID = ticketID`, `OutBody.oldStatus = "UNKNOWN"`, `OutBody.newStatus = "INVALID_STATUS"`, `OutBody.updatedAt = NullDate()`, call `HTTPRequestHandler.SetStatusCode(400)`, and End with `OutBody`.

12. Add Aggregate `GetTicketById`.
13. Filter: `ETicket.TicketId = ticketID`.
14. If no rows found, call `BuildApiError` and map:

- `Code = "TICKET_NOT_FOUND"`
- `Message = "Ticket not found"`
- `Details = "ticketID=" + ticketID`
- `CorrelationID = CorrelationId`
  Then assign `OutBody.ticketID = ticketID`, `OutBody.oldStatus = "NOT_FOUND"`, `OutBody.newStatus = Request.status`, `OutBody.updatedAt = NullDate()`, call `HTTPRequestHandler.SetStatusCode(404)`, and End with `OutBody`.

### 10.4.1 Step 15: Assign FoundTicket and OldStatus

After the `GetTicketById` aggregate executes successfully:

1. **Add an Assign node** on the "True" path (ticket found).
2. **Add the first assignment:**

   ```
   FoundTicket = GetTicketById.List.Current
   ```

   - `GetTicketById.List.Current` extracts the first result row from the filtered aggregate (which is the only row since `TicketId` is unique).
   - Both `FoundTicket` and the aggregate result are `ETicket` record types, so the types match.

3. **Add a second assignment in the same Assign node:**

   ```
   OldStatus = FoundTicket.Status
   ```

   - This captures the current ticket status before any changes. This is the "before" value needed for the response and validation.

4. **Click Done** to close the Assign node.

### 10.4.2 Step 16: Check Transition Validity

1. **Add a Decision node** after the Assign.
2. **Set the Decision condition exactly to:**

   ```
   (OldStatus = "VALID" AND NormalizedStatus = "USED")
   OR
   (OldStatus = "VALID" AND NormalizedStatus = "CANCELLED")
   OR
   (OldStatus = "VALID" AND NormalizedStatus = "CANCELLATION_IN_PROGRESS")
   OR
   (OldStatus = "CANCELLATION_IN_PROGRESS" AND NormalizedStatus = "CANCELLED")
   ```

   - This checks if the transition from `OldStatus` to `NormalizedStatus` is in the allowed list.
   - **True path:** Proceed to Step 10.4.4 (valid transition, update database).
   - **False path:** Proceed to Step 10.4.3 (invalid transition, return error).

### 10.4.3 Step 17: Invalid Transition Path (False Branch)

On the **False** path of the Decision:

1. **Call `BuildApiError`** with:
   - `Code = "INVALID_TRANSITION"`
   - `Message = "Status transition is not allowed"`
   - `Details = OldStatus + "->" + NormalizedStatus`
   - `CorrelationID = CorrelationId`

2. **Add an Assign node** to build the error response:
   - `OutBody.ticketID = ticketID`
   - `OutBody.oldStatus = OldStatus`
   - `OutBody.newStatus = NormalizedStatus`
   - `OutBody.updatedAt = NullDate()`

3. **Call `HTTPRequestHandler.SetStatusCode(409)`** to set HTTP 409 Conflict.

4. **Add an End node** to terminate this branch and return `OutBody` to the client.

### 10.4.4 Step 18: Valid Transition Path - Conditional Field Updates

On the **True** path of the Decision node:

#### **Sub-step A: Get current timestamp**

1. **Add a Service Call node** that calls the `NowUtc` action.
   - This provides the current UTC time via `NowUtc.UtcNow` for use in subsequent steps.

#### **Sub-step B: Copy ticket record for update**

2. **Add an Assign node** with:

   ```
   UpdateSource = FoundTicket
   ```

   - This copies the entire `ETicket` record structure from the database (`FoundTicket`) into a working copy (`UpdateSource`) so you can modify it before updating the database.
   - Both variables are `ETicket` record types, so the assignment is direct.

#### **Sub-step C: Set status and update timestamp (unconditional)**

3. **Add an Assign node** (or extend the previous one by clicking "Add another") with:

   ```
   UpdateSource.Status = NormalizedStatus
   UpdateSource.UpdatedAt = NowUtc.UtcNow
   ```

   - `UpdateSource.Status`: Set the status field to the new validated status.
   - `UpdateSource.UpdatedAt`: Set the timestamp to capture when the status changed.
   - These assignments happen for **every** valid transition.

#### **Sub-step D: Conditionally set UsedAt or CancelledAt**

This is the conditional logic section. You must do **either** of these two approaches:

**OPTION 1: Separate Decision nodes (Recommended for clarity)**

1. **Add a Decision node** with condition:

   ```
   NormalizedStatus = "USED"
   ```

   - **True path:** Add an Assign node with:
     ```
     UpdateSource.UsedAt = NowUtc.UtcNow
     ```
   - **False path:** Continue without assignment (no action node needed).

2. **Merge the paths** and add another Decision node with condition:

   ```
   NormalizedStatus = "CANCELLED"
   ```

   - **True path:** Add an Assign node with:
     ```
     UpdateSource.CancelledAt = NowUtc.UtcNow
     ```
   - **False path:** Continue without assignment.

3. **Both paths merge** and continue to Sub-step E.

**OPTION 2: Nested assignments in a single Decision (More compact)**

1. **Add a single Decision node** with condition:

   ```
   NormalizedStatus = "USED" OR NormalizedStatus = "CANCELLED"
   ```

   - **True path:** Add an Assign node with both assignments:
     ```
     UpdateSource.UsedAt = If(NormalizedStatus = "USED", NowUtc.UtcNow, NullDate())
     UpdateSource.CancelledAt = If(NormalizedStatus = "CANCELLED", NowUtc.UtcNow, NullDate())
     ```
   - **False path:** Continue without assignment.

> **Recommendation:** Use **OPTION 1** for maximum clarity and easier debugging. You can trace exactly which branch was taken.

#### **Sub-step E: Write updated record to database**

4. **Add a Service Call node** that calls the `UpdateETicket` action:
   - Input parameter: `UpdateSource` (the modified ticket record)
   - This persists your changes to the database.

#### **Sub-step F: Build success response**

5. **Add an Assign node** to populate the response structure:

   ```
   OutBody.ticketID = FoundTicket.TicketId
   OutBody.oldStatus = OldStatus
   OutBody.newStatus = NormalizedStatus
   OutBody.updatedAt = NowUtc.UtcNow
   ```

   - `OutBody.ticketID`: The ticket ID being updated (from the path parameter).
   - `OutBody.oldStatus`: The previous status (captured in Step 10.4.1).
   - `OutBody.newStatus`: The new status after update.
   - `OutBody.updatedAt`: The exact timestamp when the update occurred.

#### **Sub-step G: Set HTTP 200 and return**

6. **Call `HTTPRequestHandler.SetStatusCode(200)`** to indicate successful status update.

7. **Add an End node** to return `OutBody` to the client with the 200 status code.

---

#### **Visual Flow Summary for Step 18 (Valid Transition Path)**

```
[Valid Transition Decision] → True
    ↓
[Call NowUtc]
    ↓
[Assign: UpdateSource = FoundTicket]
    ↓
[Assign: UpdateSource.Status = NormalizedStatus, UpdateSource.UpdatedAt = NowUtc.UtcNow]
    ↓
[Decision: NormalizedStatus = "USED"?]
    ├─ True:  [Assign: UpdateSource.UsedAt = NowUtc.UtcNow]
    └─ False: (continue)
    ↓
[Decision: NormalizedStatus = "CANCELLED"?]
    ├─ True:  [Assign: UpdateSource.CancelledAt = NowUtc.UtcNow]
    └─ False: (continue)
    ↓
[Call UpdateETicket with UpdateSource]
    ↓
[Assign: OutBody fields]
    ↓
[Call HTTPRequestHandler.SetStatusCode(200)]
    ↓
[End with OutBody]
```

### 10.5 Completion check

1. Allowed transitions return 200.
2. Unknown ticket returns 404.
3. Invalid status returns 400.
4. Invalid transition returns 409.

Publish after completion.

---

## 11. Implement Step 13: POST /etickets/update

This method supports cancellation and transfer/reissue.

### 11.1 Method definition

1. Open `REST > v1 > UpdateETickets`.
2. Confirm input `Request` of type `UpdateETicketsRequest`.
3. The method has ONE output parameter. Name it `OutBody` of type `UpdateETicketsResponse`.
4. This method returns only one output structure: `OutBody`. Populate it with operation result data for all paths (success, failure, not found) and return it with the appropriate HTTP status code.
5. Add local variables:
   - `CorrelationId` (Text)
   - `OldTicket` (ETicket record)
   - `ExistingNewHoldTicket` (ETicket record)
   - `UpdateOldSource` (ETicket record)
   - `NewTicketId` (Text)
6. Do NOT create or return an `OutError` variable in this method. This endpoint returns only `OutBody` for both success and error paths.

### 11.2 Build the flow

1. Start.
2. Set `CorrelationId = Request.correlationID`.
3. If blank, set `CorrelationId = GenerateGuid()`.
4. Call `ValidateRequiredText` with `Value = Request.oldTicketID` and `FieldName = "oldTicketID"`.
5. Add a Decision node on `ValidateRequiredText.IsValid`.
6. If `False`, call `BuildApiError` and map:
   - `Code = "INVALID_REQUEST"`
   - `Message = ValidateRequiredText.ErrorMessage`
   - `Details = "oldTicketID"`
   - `CorrelationID = CorrelationId`
     Then assign `OutBody.operation = Request.operation`, `OutBody.oldTicketStatus = "UNKNOWN"`, `OutBody.newTicketID = ""`, call `HTTPRequestHandler.SetStatusCode(400)`, and End with `OutBody`.
7. Call `ValidateRequiredText` with `Value = Request.operation` and `FieldName = "operation"`.
8. Add a Decision node on `ValidateRequiredText.IsValid`.
9. If `False`, call `BuildApiError` and map:
   - `Code = "INVALID_REQUEST"`
   - `Message = ValidateRequiredText.ErrorMessage`
   - `Details = "operation"`
   - `CorrelationID = CorrelationId`
     Then assign `OutBody.operation = Request.operation`, `OutBody.oldTicketStatus = "UNKNOWN"`, `OutBody.newTicketID = ""`, call `HTTPRequestHandler.SetStatusCode(400)`, and End with `OutBody`.
10. Add a Decision node named `IsSupportedOperation` with condition:

```
Request.operation = "CANCEL_ONLY" OR Request.operation = "TRANSFER_AND_REISSUE"
```

11. On the **False** path of `IsSupportedOperation`:
1. Call `BuildApiError` and map:
   - `Code = "INVALID_OPERATION"`
   - `Message = "Unsupported operation"`
   - `Details = "operation=" + Request.operation`
   - `CorrelationID = CorrelationId`
1. Add an Assign node:
   - `OutBody.operation = Request.operation`
   - `OutBody.oldTicketStatus = "UNKNOWN"`
   - `OutBody.newTicketID = ""`
1. Call `HTTPRequestHandler.SetStatusCode(400)`.
1. End with `OutBody`.

1. On the **True** path of `IsSupportedOperation`, add Aggregate `GetOldTicket`.
1. Set filter:

```
ETicket.TicketId = Request.oldTicketID
```

14. Add a Decision node named `OldTicketFound` with condition:

```
GetOldTicket.List.Length > 0
```

15. On the **False** path of `OldTicketFound`:
1. Call `BuildApiError` and map:
   - `Code = "TICKET_NOT_FOUND"`
   - `Message = "Old ticket not found"`
   - `Details = "oldTicketID=" + Request.oldTicketID`
   - `CorrelationID = CorrelationId`
1. Add an Assign node:
   - `OutBody.operation = Request.operation`
   - `OutBody.oldTicketStatus = "NOT_FOUND"`
   - `OutBody.newTicketID = ""`
1. Call `HTTPRequestHandler.SetStatusCode(404)`.
1. End with `OutBody`.

1. On the **True** path of `OldTicketFound`, add an Assign node:

- `OldTicket = GetOldTicket.List.Current`

### 11.2.1 CANCEL_ONLY branch (explicit)

17. Add a Decision node named `IsCancelOnly` with condition:

```
Request.operation = "CANCEL_ONLY"
```

18. On the **True** path of `IsCancelOnly`:
1. Call `NowUtc`.
1. Add an Assign node:
   - `UpdateOldSource = OldTicket`
   - `UpdateOldSource.Status = "CANCELLED"`
   - `UpdateOldSource.CancelledAt = NowUtc.UtcNow`
   - `UpdateOldSource.UpdatedAt = NowUtc.UtcNow`
1. Run `UpdateETicket` with `UpdateOldSource`.
1. Add an Assign node:
   - `OutBody.operation = "CANCEL_ONLY"`
   - `OutBody.oldTicketStatus = "CANCELLED"`
   - `OutBody.newTicketID = ""`
1. Call `HTTPRequestHandler.SetStatusCode(200)`.
1. End with `OutBody`.

### 11.2.2 TRANSFER_AND_REISSUE branch (explicit)

19. On the **False** path of `IsCancelOnly`, continue as transfer-and-reissue flow.

20. Add four `ValidateRequiredText` calls (or one reusable validation subflow) for:

- `Request.newOwnerUserID`
- `Request.newHoldID`
- `Request.newSeatID`
- `Request.newSeatNumber`

`Request.newTransactionID` is optional. If provided by the orchestrator/payment flow, use it when creating the new ticket. If blank, fallback to the old ticket transaction ID.

21. Add a Decision node named `TransferFieldsValid` with condition:

```
(ValidateNewOwner.IsValid)
AND (ValidateNewHold.IsValid)
AND (ValidateNewSeatId.IsValid)
AND (ValidateNewSeatNumber.IsValid)
```

Use your actual action output variable names if different.

22. On the **False** path of `TransferFieldsValid`:
1. Call `BuildApiError` and map:
   - `Code = "INVALID_REQUEST"`
   - `Message = "Transfer fields are required"`
   - `Details = "newOwnerUserID, newHoldID, newSeatID, newSeatNumber"`
   - `CorrelationID = CorrelationId`
1. Add an Assign node:
   - `OutBody.operation = Request.operation`
   - `OutBody.oldTicketStatus = OldTicket.Status`
   - `OutBody.newTicketID = ""`
1. Call `HTTPRequestHandler.SetStatusCode(400)`.
1. End with `OutBody`.

1. On the **True** path of `TransferFieldsValid`, add a Decision node named `OldTicketTransferable` with condition:

```
OldTicket.Status = "VALID" OR OldTicket.Status = "CANCELLATION_IN_PROGRESS"
```

24. On the **False** path of `OldTicketTransferable`:
1. Call `BuildApiError` and map:
   - `Code = "INVALID_TICKET_STATE"`
   - `Message = "Old ticket status does not allow transfer/cancel transition"`
   - `Details = "oldStatus=" + OldTicket.Status`
   - `CorrelationID = CorrelationId`
1. Add an Assign node:
   - `OutBody.operation = Request.operation`
   - `OutBody.oldTicketStatus = OldTicket.Status`
   - `OutBody.newTicketID = ""`
1. Call `HTTPRequestHandler.SetStatusCode(409)`.
1. End with `OutBody`.

1. On the **True** path of `OldTicketTransferable`, add Aggregate `GetTicketByNewHold`.

1. Set filter and max records:

```
ETicket.HoldId = Request.newHoldID
Max Records = 1
```

27. Add a Decision node named `NewHoldAlreadyHasTicket` with condition:

```
GetTicketByNewHold.List.Length > 0
```

28. On the **True** path of `NewHoldAlreadyHasTicket`, add an Assign node:

- `ExistingNewHoldTicket = GetTicketByNewHold.List.Current`

29. Add a Decision node named `ExistingTicketMatchesRequestContext` with condition:

```
ExistingNewHoldTicket.UserId = Request.newOwnerUserID
AND ExistingNewHoldTicket.EventId = OldTicket.EventId
AND ExistingNewHoldTicket.SeatId = Request.newSeatID
AND ExistingNewHoldTicket.SeatNumber = Request.newSeatNumber
AND ExistingNewHoldTicket.TransactionId = If(Request.newTransactionID = "", OldTicket.TransactionId, Request.newTransactionID)
```

30. On the **True** path of `ExistingTicketMatchesRequestContext` (idempotent replay):
1. Add an Assign node:
   - `OutBody.operation = "TRANSFER_AND_REISSUE"`
   - `OutBody.oldTicketStatus = OldTicket.Status`
   - `OutBody.newTicketID = ExistingNewHoldTicket.TicketId`
1. Call `HTTPRequestHandler.SetStatusCode(200)`.
1. End with `OutBody`.

1. On the **False** path of `ExistingTicketMatchesRequestContext` (true business conflict):
1. Call `BuildApiError` and map:
   - `Code = "TRANSFER_CONFLICT"`
   - `Message = "newHoldID already has a ticket that conflicts with request context"`
   - `Details = "owner/seat/event/transaction mismatch on newHoldID"`
   - `CorrelationID = CorrelationId`
1. Add an Assign node:
   - `OutBody.operation = Request.operation`
   - `OutBody.oldTicketStatus = OldTicket.Status`
   - `OutBody.newTicketID = ""`
1. Call `HTTPRequestHandler.SetStatusCode(409)`.
1. End with `OutBody`.

1. On the **False** path of `NewHoldAlreadyHasTicket` (fresh transfer), execute update/create in this order:
1. Call `NowUtc`.
1. Add an Assign node to prepare the old ticket update:
   - `UpdateOldSource = OldTicket`
   - `UpdateOldSource.Status = "CANCELLED"`
   - `UpdateOldSource.CancelledAt = NowUtc.UtcNow`
   - `UpdateOldSource.UpdatedAt = NowUtc.UtcNow`
1. Run `UpdateETicket` with `UpdateOldSource`.
1. Call `GenerateTicketId` and store output in `NewTicketId`.
1. Call `NowUtc` (or reuse a second UTC call variable for create timestamps).
1. Add a `CreateETicket` call and map fields exactly:
   - `TicketId = NewTicketId`
   - `HoldId = Request.newHoldID`
   - `UserId = Request.newOwnerUserID`
   - `EventId = OldTicket.EventId`
   - `SeatId = Request.newSeatID`
   - `SeatNumber = Request.newSeatNumber`
   - `TransactionId = If(Request.newTransactionID = "", OldTicket.TransactionId, Request.newTransactionID)`
   - `Status = "VALID"`
   - `IssuedAt = NowUtc.UtcNow`
   - `CreatedAt = NowUtc.UtcNow`
   - `UpdatedAt = NowUtc.UtcNow`
   - `UsedAt = NullDate()`
   - `CancelledAt = NullDate()`

1. Add an Assign node for success response:

- `OutBody.operation = "TRANSFER_AND_REISSUE"`
- `OutBody.oldTicketStatus = "CANCELLED"`
- `OutBody.newTicketID = NewTicketId`

34. Call `HTTPRequestHandler.SetStatusCode(200)`.
35. End with `OutBody`.

### 11.2.3 Expected outcomes

1. `CANCEL_ONLY` returns HTTP 200 and `OutBody.newTicketID = ""`.
2. `TRANSFER_AND_REISSUE` fresh create returns HTTP 200 and `OutBody.newTicketID = NewTicketId`.
3. `TRANSFER_AND_REISSUE` idempotent replay (existing ticket on `newHoldID` that matches request context) returns HTTP 200 with `OutBody.newTicketID = ExistingNewHoldTicket.TicketId`.
4. Missing transfer fields returns HTTP 400.
5. Unknown old ticket returns HTTP 404.
6. Unsupported operation returns HTTP 400.
7. Transfer conflict (`newHoldID` existing ticket mismatch, or old ticket non-transferable state) returns HTTP 409.

Publish after completion.

---

## 11.4 Response Pattern — Standard Across All Methods

All 5 REST methods follow the **same single response pattern** since each has only ONE output parameter: `OutBody`.

**Reminder: See Section 6.4 for how to use `HTTPRequestHandler.SetStatusCode()`.**

---

### Pattern: Single Output Parameter

All methods return only `OutBody`. For every code path (success or error), you:

Important: Do not use `OutError` as a returned payload variable in these REST methods.

1. **Populate `OutBody`** with appropriate data:
   - **Success paths (200, 201):** Assign real data from database or computation into `OutBody` fields
   - **Error paths (400, 403, 404, 409, 500):** Assign endpoint-specific fallback values field-by-field (do not assign `ApiError` structure directly)

2. **Call `HTTPRequestHandler.SetStatusCode()`** with the appropriate code:
   - `SetStatusCode(200)` or `SetStatusCode(201)` for success
   - `SetStatusCode(400)` for validation errors
   - `SetStatusCode(403)` for forbidden (owner mismatch)
   - `SetStatusCode(404)` for not found
   - `SetStatusCode(409)` for conflict (invalid state transition)
   - `SetStatusCode(500)` for internal server errors

3. **End with `OutBody`** — the response is serialized to JSON with the status code you set

### Why This Works

- **Single output:** REST exposed API automatically returns only `OutBody` to the client
- **Status code:** `HTTPRequestHandler.SetStatusCode()` sets the HTTP response code
- **Unified handling:** Same code path logic for all outcomes—just assign different data and status codes

### Example Flows

**Success path:**

```
1. Get data from database → assign to OutBody
2. HTTPRequestHandler.SetStatusCode(200)
3. End with OutBody
Result: HTTP 200 + OutBody as JSON
```

**Error path:**

```
1. Call BuildApiError, then map endpoint-specific OutBody fields (field-by-field)
2. HTTPRequestHandler.SetStatusCode(404)
3. End with OutBody
Result: HTTP 404 + OutBody (with error fields) as JSON
```

**Logging path (must exist before every End):**

```
1. Assign OutBody fields
2. HTTPRequestHandler.SetStatusCode(<code>)
3. LogApiEvent(EventName, TicketId/HoldId, CorrelationId, RequestBody, ResponseBody, Outcome)
4. End with OutBody
```

- Assign all required fields in `OutBody` with data or safe fallback values:
  - Text fields: empty string `""` or sentinel values like `"NOT_FOUND"`, `"UNKNOWN"`
  - DateTime fields: `NullDate()`
  - Boolean fields: `False`
  - Numeric fields: `0`
- Call `HTTPRequestHandler.SetStatusCode(4xx or 5xx)` with the appropriate error code
- End with `OutBody` — the response object is serialized to JSON with the status code you set
- The caller must check the HTTP status code to interpret whether this is an error

### 11.5 Logging Retrofit Checklist (Apply to All 5 Methods)

Use this checklist if your current implementation logs only `GenerateETicket`.

1. `GenerateETicket`: keep current logging, and ensure `400` and `500` branches also call `LogApiEvent` before End.
2. `GetETicketByHold`: add `LogApiEvent` before every End (`200`, `400`, `404`, `500`).
3. `ValidateTicketOwnership`: add `LogApiEvent` before every End (`200`, `400`, `403`, `404`, `409`, `500`).
4. `UpdateTicketStatus`: add `LogApiEvent` before every End (`200`, `400`, `404`, `409`, `500`).
5. `UpdateETickets`: add `LogApiEvent` before every End (`200`, `400`, `404`, `500`).
6. Ensure `CorrelationId` is set once at method start (incoming value or generated GUID) and reused in all log calls.
7. Ensure every `AllExceptions` handler logs `Outcome = "500|INTERNAL_ERROR"` before End.

### 11.6 Exact LogApiEvent Field Mapping for Error Paths

Use this mapping immediately before each error-path End node.

#### A) GenerateETicket (`POST /eticket/generate`)

For validation errors (`400`) in Step 7.3.1 to 7.3.5:

1. `EventName = "GenerateETicket"`
2. `TicketId = ""`
3. `HoldId = Request.holdID`
4. `CorrelationId = CorrelationId`
5. `RequestBody = Request.holdID + "|" + Request.userID + "|" + Request.eventID + "|" + Request.seatID + "|" + Request.seatNumber`
6. `ResponseBody = BuildApiError.ErrorOut.code + "|" + BuildApiError.ErrorOut.message + "|" + BuildApiError.ErrorOut.details`
7. `Outcome = "400|" + BuildApiError.ErrorOut.code`

For exception path (`500`) in Step 7.5:

1. `EventName = "GenerateETicket"`
2. `TicketId = ""`
3. `HoldId = Request.holdID`
4. `CorrelationId = CorrelationId`
5. `RequestBody = Request.holdID + "|" + Request.userID + "|" + Request.eventID + "|" + Request.seatID + "|" + Request.seatNumber`
6. `ResponseBody = BuildApiError.ErrorOut.code + "|" + BuildApiError.ErrorOut.message + "|" + BuildApiError.ErrorOut.details`
7. `Outcome = "500|INTERNAL_ERROR"`

#### B) GetETicketByHold (`GET /eticket/hold/{holdID}`)

For invalid input (`400`) in Step 8.2:

1. `EventName = "GetETicketByHold"`
2. `TicketId = ""`
3. `HoldId = holdID`
4. `CorrelationId = CorrelationId`
5. `RequestBody = "holdID=" + holdID`
6. `ResponseBody = BuildApiError.ErrorOut.code + "|" + BuildApiError.ErrorOut.message + "|" + BuildApiError.ErrorOut.details`
7. `Outcome = "400|" + BuildApiError.ErrorOut.code`

For not found (`404`) in Step 8.2 false branch:

1. `EventName = "GetETicketByHold"`
2. `TicketId = ""`
3. `HoldId = holdID`
4. `CorrelationId = CorrelationId`
5. `RequestBody = "holdID=" + holdID`
6. `ResponseBody = BuildApiError.ErrorOut.code + "|" + BuildApiError.ErrorOut.message + "|" + BuildApiError.ErrorOut.details`
7. `Outcome = "404|" + BuildApiError.ErrorOut.code`

For exception path (`500`):

1. `EventName = "GetETicketByHold"`
2. `TicketId = ""`
3. `HoldId = holdID`
4. `CorrelationId = CorrelationId`
5. `RequestBody = "holdID=" + holdID`
6. `ResponseBody = "500|Internal server error"`
7. `Outcome = "500|INTERNAL_ERROR"`

#### C) ValidateTicketOwnership (`GET /eticket/validate`)

For invalid input (`400`) on `ticketID` or `userID`:

1. `EventName = "ValidateTicketOwnership"`
2. `TicketId = ticketID`
3. `HoldId = ""`
4. `CorrelationId = CorrelationId`
5. `RequestBody = "ticketID=" + ticketID + "|userID=" + userID`
6. `ResponseBody = BuildApiError.ErrorOut.code + "|" + BuildApiError.ErrorOut.message + "|" + BuildApiError.ErrorOut.details`
7. `Outcome = "400|" + BuildApiError.ErrorOut.code`

For not found (`404`) in Step 9.2 ticket lookup miss:

1. `EventName = "ValidateTicketOwnership"`
2. `TicketId = ticketID`
3. `HoldId = ""`
4. `CorrelationId = CorrelationId`
5. `RequestBody = "ticketID=" + ticketID + "|userID=" + userID`
6. `ResponseBody = "TICKET_NOT_FOUND|No ticket for ticketID|ticketID=" + ticketID`
7. `Outcome = "404|TICKET_NOT_FOUND"`

For invalid state (`409`) in Step 9.2 (`FoundTicket.Status <> "VALID"`):

1. `EventName = "ValidateTicketOwnership"`
2. `TicketId = ticketID`
3. `HoldId = FoundTicket.HoldId`
4. `CorrelationId = CorrelationId`
5. `RequestBody = "ticketID=" + ticketID + "|userID=" + userID`
6. `ResponseBody = "INVALID_STATE|status=" + FoundTicket.Status`
7. `Outcome = "409|" + FoundTicket.Status`

For owner mismatch (`403`) in Step 9.2:

1. `EventName = "ValidateTicketOwnership"`
2. `TicketId = ticketID`
3. `HoldId = FoundTicket.HoldId`
4. `CorrelationId = CorrelationId`
5. `RequestBody = "ticketID=" + ticketID + "|userID=" + userID`
6. `ResponseBody = "OWNER_MISMATCH|ticketOwner=" + FoundTicket.UserId + "|requestUser=" + userID`
7. `Outcome = "403|OWNER_MISMATCH"`

For exception path (`500`):

1. `EventName = "ValidateTicketOwnership"`
2. `TicketId = ticketID`
3. `HoldId = ""`
4. `CorrelationId = CorrelationId`
5. `RequestBody = "ticketID=" + ticketID + "|userID=" + userID`
6. `ResponseBody = "500|Internal server error"`
7. `Outcome = "500|INTERNAL_ERROR"`

#### D) UpdateTicketStatus (`PUT /etickets/status/{ticketID}`)

For invalid input/status (`400`) in Step 10.4:

1. `EventName = "UpdateTicketStatus"`
2. `TicketId = ticketID`
3. `HoldId = ""`
4. `CorrelationId = CorrelationId`
5. `RequestBody = "ticketID=" + ticketID + "|status=" + Request.status`
6. `ResponseBody = BuildApiError.ErrorOut.code + "|" + BuildApiError.ErrorOut.message + "|" + BuildApiError.ErrorOut.details`
7. `Outcome = "400|" + BuildApiError.ErrorOut.code`

For not found (`404`) in Step 10.4:

1. `EventName = "UpdateTicketStatus"`
2. `TicketId = ticketID`
3. `HoldId = ""`
4. `CorrelationId = CorrelationId`
5. `RequestBody = "ticketID=" + ticketID + "|status=" + Request.status`
6. `ResponseBody = BuildApiError.ErrorOut.code + "|" + BuildApiError.ErrorOut.message + "|" + BuildApiError.ErrorOut.details`
7. `Outcome = "404|" + BuildApiError.ErrorOut.code`

For invalid transition (`409`) in Step 10.4.3:

1. `EventName = "UpdateTicketStatus"`
2. `TicketId = ticketID`
3. `HoldId = FoundTicket.HoldId`
4. `CorrelationId = CorrelationId`
5. `RequestBody = "ticketID=" + ticketID + "|status=" + Request.status`
6. `ResponseBody = BuildApiError.ErrorOut.code + "|" + BuildApiError.ErrorOut.message + "|" + BuildApiError.ErrorOut.details`
7. `Outcome = "409|INVALID_TRANSITION"`

For exception path (`500`):

1. `EventName = "UpdateTicketStatus"`
2. `TicketId = ticketID`
3. `HoldId = ""`
4. `CorrelationId = CorrelationId`
5. `RequestBody = "ticketID=" + ticketID + "|status=" + Request.status`
6. `ResponseBody = "500|Internal server error"`
7. `Outcome = "500|INTERNAL_ERROR"`

#### E) UpdateETickets (`POST /etickets/update`)

For invalid input/operation (`400`) in Step 11.2:

1. `EventName = "UpdateETickets"`
2. `TicketId = Request.oldTicketID`
3. `HoldId = Request.newHoldID`
4. `CorrelationId = CorrelationId`
5. `RequestBody = Request.oldTicketID + "|" + Request.operation + "|" + Request.newOwnerUserID + "|" + Request.newHoldID + "|" + Request.newSeatID + "|" + Request.newSeatNumber`
6. `ResponseBody = BuildApiError.ErrorOut.code + "|" + BuildApiError.ErrorOut.message + "|" + BuildApiError.ErrorOut.details`
7. `Outcome = "400|" + BuildApiError.ErrorOut.code`

For old ticket not found (`404`) in Step 11.2:

1. `EventName = "UpdateETickets"`
2. `TicketId = Request.oldTicketID`
3. `HoldId = ""`
4. `CorrelationId = CorrelationId`
5. `RequestBody = Request.oldTicketID + "|" + Request.operation`
6. `ResponseBody = BuildApiError.ErrorOut.code + "|" + BuildApiError.ErrorOut.message + "|" + BuildApiError.ErrorOut.details`
7. `Outcome = "404|" + BuildApiError.ErrorOut.code`

For transfer fields missing (`400`) in Step 11.2.2:

1. `EventName = "UpdateETickets"`
2. `TicketId = Request.oldTicketID`
3. `HoldId = Request.newHoldID`
4. `CorrelationId = CorrelationId`
5. `RequestBody = Request.oldTicketID + "|" + Request.operation + "|" + Request.newOwnerUserID + "|" + Request.newHoldID + "|" + Request.newSeatID + "|" + Request.newSeatNumber`
6. `ResponseBody = BuildApiError.ErrorOut.code + "|" + BuildApiError.ErrorOut.message + "|" + BuildApiError.ErrorOut.details`
7. `Outcome = "400|INVALID_REQUEST"`

For exception path (`500`):

1. `EventName = "UpdateETickets"`
2. `TicketId = Request.oldTicketID`
3. `HoldId = Request.newHoldID`
4. `CorrelationId = CorrelationId`
5. `RequestBody = Request.oldTicketID + "|" + Request.operation + "|" + Request.newOwnerUserID + "|" + Request.newHoldID + "|" + Request.newSeatID + "|" + Request.newSeatNumber`
6. `ResponseBody = "500|Internal server error"`
7. `Outcome = "500|INTERNAL_ERROR"`

Implementation order reminder for every error path:

1. `BuildApiError` (when applicable)
2. Assign `OutBody` fallback values
3. `HTTPRequestHandler.SetStatusCode(...)`
4. `LogApiEvent(...)` using mappings above
5. End with `OutBody`

### 11.7 Exact LogApiEvent Field Mapping for Success Paths

Use this mapping immediately before each success-path End node.

#### A) GenerateETicket (`POST /eticket/generate`)

For idempotent replay (`200`) in Step 7.4 true branch:

1. `EventName = "GenerateETicket"`
2. `TicketId = OutBody.ticketID`
3. `HoldId = OutBody.holdID`
4. `CorrelationId = CorrelationId`
5. `RequestBody = Request.holdID + "|" + Request.userID + "|" + Request.eventID + "|" + Request.seatID + "|" + Request.seatNumber`
6. `ResponseBody = OutBody.ticketID + "|" + OutBody.holdID + "|" + OutBody.status + "|" + ToText(OutBody.issuedAt) + "|" + OutBody.seatNumber`
7. `Outcome = "200|IDEMPOTENT_REPLAY"`

For created (`201`) in Step 7.4 false branch:

1. `EventName = "GenerateETicket"`
2. `TicketId = OutBody.ticketID`
3. `HoldId = OutBody.holdID`
4. `CorrelationId = CorrelationId`
5. `RequestBody = Request.holdID + "|" + Request.userID + "|" + Request.eventID + "|" + Request.seatID + "|" + Request.seatNumber`
6. `ResponseBody = OutBody.ticketID + "|" + OutBody.holdID + "|" + OutBody.status + "|" + ToText(OutBody.issuedAt) + "|" + OutBody.seatNumber`
7. `Outcome = "201|CREATED"`

#### B) GetETicketByHold (`GET /eticket/hold/{holdID}`)

For found ticket (`200`) in Step 8.2 true branch:

1. `EventName = "GetETicketByHold"`
2. `TicketId = OutBody.ticketID`
3. `HoldId = OutBody.holdID`
4. `CorrelationId = CorrelationId`
5. `RequestBody = "holdID=" + holdID`
6. `ResponseBody = OutBody.ticketID + "|" + OutBody.holdID + "|" + OutBody.userID + "|" + OutBody.eventID + "|" + OutBody.seatID + "|" + OutBody.seatNumber + "|" + OutBody.status + "|" + ToText(OutBody.issuedAt)`
7. `Outcome = "200|OK"`

#### C) ValidateTicketOwnership (`GET /eticket/validate`)

For valid owner (`200`) in Step 9.2 final else branch:

1. `EventName = "ValidateTicketOwnership"`
2. `TicketId = ticketID`
3. `HoldId = FoundTicket.HoldId`
4. `CorrelationId = CorrelationId`
5. `RequestBody = "ticketID=" + ticketID + "|userID=" + userID`
6. `ResponseBody = ToText(OutBody.valid) + "|" + OutBody.reason + "|" + OutBody.status`
7. `Outcome = "200|OK"`

#### D) UpdateTicketStatus (`PUT /etickets/status/{ticketID}`)

For successful transition (`200`) in Step 10.4.4:

1. `EventName = "UpdateTicketStatus"`
2. `TicketId = OutBody.ticketID`
3. `HoldId = FoundTicket.HoldId`
4. `CorrelationId = CorrelationId`
5. `RequestBody = "ticketID=" + ticketID + "|status=" + Request.status`
6. `ResponseBody = OutBody.ticketID + "|" + OutBody.oldStatus + "|" + OutBody.newStatus + "|" + ToText(OutBody.updatedAt)`
7. `Outcome = "200|UPDATED"`

#### E) UpdateETickets (`POST /etickets/update`)

For `CANCEL_ONLY` success (`200`) in Step 11.2.1:

1. `EventName = "UpdateETickets"`
2. `TicketId = Request.oldTicketID`
3. `HoldId = OldTicket.HoldId`
4. `CorrelationId = CorrelationId`
5. `RequestBody = Request.oldTicketID + "|" + Request.operation`
6. `ResponseBody = OutBody.operation + "|" + OutBody.oldTicketStatus + "|" + OutBody.newTicketID`
7. `Outcome = "200|CANCEL_ONLY"`

For `TRANSFER_AND_REISSUE` success (`200`) in Step 11.2.2:

1. `EventName = "UpdateETickets"`
2. `TicketId = OutBody.newTicketID`
3. `HoldId = Request.newHoldID`
4. `CorrelationId = CorrelationId`
5. `RequestBody = Request.oldTicketID + "|" + Request.operation + "|" + Request.newOwnerUserID + "|" + Request.newHoldID + "|" + Request.newSeatID + "|" + Request.newSeatNumber + "|" + Request.newTransactionID`
6. `ResponseBody = OutBody.operation + "|" + OutBody.oldTicketStatus + "|" + OutBody.newTicketID`
7. `Outcome = "200|TRANSFER_AND_REISSUE"`

Implementation order reminder for every success path:

1. Assign `OutBody` success values
2. `HTTPRequestHandler.SetStatusCode(200 or 201)`
3. `LogApiEvent(...)` using mappings above
4. End with `OutBody`

---

**Key Distinction: `OutBody.status` (business field) vs HTTP Status Code**

They are INDEPENDENT:

- `OutBody.status` = Text field in your response structure (e.g., ticket status: "VALID", "USED", "CANCELLED", "NOT_FOUND")
  - Set via normal Assign: `OutBody.status = "VALID"`
- **HTTP Status Code** = Set via `HTTPRequestHandler.SetStatusCode()` (e.g., 200, 201, 400, 404, 409, 500)
  - Examples: `SetStatusCode(200)`, `SetStatusCode(404)`

Example in GetETicketByHold:

- Ticket found: `OutBody.status = "VALID"` + `SetStatusCode(200)`
- Ticket not found: `OutBody.status = "NOT_FOUND"` + `SetStatusCode(404)`

Example in ValidateTicketOwnership:

- Valid owner: `OutBody.status = "VALID"` + `SetStatusCode(200)`
- Ticket not found: `OutBody.valid = False`, `OutBody.reason = "TICKET_NOT_FOUND"`, `OutBody.status = "UNKNOWN"` + `SetStatusCode(404)`
- Owner mismatch: `OutBody.valid = False`, `OutBody.reason = "OWNER_MISMATCH"`, `OutBody.status = FoundTicket.Status` + `SetStatusCode(403)`

---

## 12. Custom URL Paths and Naming

Keep these URLs exactly:

1. `/eticket/generate`
2. `/eticket/hold/{holdID}`
3. `/eticket/validate`
4. `/etickets/status/{ticketID}`
5. `/etickets/update`

Do not rename path segments after publishing unless you also update all consumers.

---

## 13. Status Code Rules

Use the correct status code for the final branch of each method:

1. `200` for successful reads, successful updates, and idempotent replay.
2. `201` for newly created tickets.
3. `400` for invalid requests.
4. `401` for auth failure.
5. `403` for ownership mismatch.
6. `404` for ticket not found.
7. `409` for invalid transition or non-VALID validation failure.
8. `500` for unexpected internal errors.

### 13.1 All Exceptions rule for every endpoint

For each REST method in this guide (`GenerateETicket`, `GetETicketByHold`, `ValidateTicketOwnership`, `UpdateTicketStatus`, `UpdateETickets`):

1. Add an `AllExceptions` handler at action level.
2. Call `BuildApiError` with:
   - `Code = "500"`
   - `Message = "Internal server error."`
   - `Details = "Unexpected error in <MethodName>."`
   - `CorrelationID = CorrelationId` (or generated request correlation variable)
3. Assign endpoint-specific fallback fields into `OutBody` (field-by-field; no structure assignment).
4. Call `HTTPRequestHandler.SetStatusCode(500)`.
5. End with `OutBody`.

Important naming rule: do not name your business output parameter `Response` in methods that also set HTTP status. Use `OutBody` for payload fields, and use `HTTPRequestHandler.SetStatusCode()` to set the HTTP transport status code.

---

## 14. Error Payload Rules

Return errors using the same shape everywhere.

Example:

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

---

## 15. Test with Real Supabase Data

Use a real confirmed hold from your Supabase database.

Run a query like this to find test data:

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

Test this order:

1. `POST /eticket/generate` with a new holdID.
2. Repeat the same request.
3. `GET /eticket/hold/{holdID}`.
4. `GET /eticket/validate` with the correct user.
5. `GET /eticket/validate` with the wrong user.
6. `PUT /etickets/status/{ticketID}` to update status.
7. `POST /etickets/update` for transfer flow if needed.

---

## 16. Integrate the Backend Services

Your backend must call OutSystems explicitly. Use the environment values already present in the project.

### 16.1 Booking Fulfillment Orchestrator

When payment succeeds and the hold is confirmed:

1. Call `POST /eticket/generate`.
2. Send the internal auth header.
3. Pass the correlation ID.
4. Treat `200` and `201` as success.

### 16.2 Booking Status Service

For the UI/status poll:

1. Call `GET /eticket/hold/{holdID}`.
2. If `200`, show ticket data.
3. If `404`, treat it as still processing unless other business errors exist.

### 16.3 Cancellation / Transfer flows

Use:

1. `GET /eticket/validate`
2. `PUT /etickets/status/{ticketID}`
3. `POST /etickets/update`

---

## 17. Fix the Scenario Documentation

Update scenario docs so they no longer describe E-Ticket as gRPC.

Replace any `gRPC ValidateTicket` wording with REST validation.

The canonical E-Ticket API list is:

1. `POST /eticket/generate`
2. `GET /eticket/hold/{holdID}`
3. `GET /eticket/validate`
4. `PUT /etickets/status/{ticketID}`
5. `POST /etickets/update`

---

## 18. Definition of Done

The implementation is complete only when all of these are true:

1. The OutSystems module is published.
2. All 5 endpoints appear in Swagger.
3. Custom authentication is enforced.
4. `POST /eticket/generate` is idempotent by `holdID`.
5. `GET /eticket/hold/{holdID}` works.
6. `GET /eticket/validate` works.
7. `PUT /etickets/status/{ticketID}` works.
8. `POST /etickets/update` works.

---

## 19. Orchestrator API Integration Contract (Comprehensive)

This section is the integration contract for developers building composite/orchestrator services.

### 19.1 Base URL, Auth, and Headers

Use the E-Ticket REST base path exposed in OutSystems for the `v1` service.

Required request headers for all endpoints:

1. `Content-Type: application/json` (for POST/PUT with body)
2. `Accept: application/json`
3. Internal auth header used by your environment/API gateway policy
4. Correlation header (recommended), and also pass `correlationID` in request body where supported

### 19.2 Endpoint Summary

1. `POST /eticket/generate`
   - Purpose: Create ticket after successful hold confirmation. Idempotent by `holdID`.
2. `GET /eticket/hold/{holdID}`
   - Purpose: Retrieve ticket by hold for booking-status/read flows.
3. `GET /eticket/validate`
   - Purpose: Validate ticket ownership and status for cancellation/transfer checks.
4. `PUT /etickets/status/{ticketID}`
   - Purpose: Transition ticket status with explicit transition rules.
5. `POST /etickets/update`
   - Purpose: Perform cancel-only or transfer-and-reissue in one operation.

### 19.3 Detailed Contract by Endpoint

#### A) POST /eticket/generate

Purpose:

1. Generate a `VALID` ticket from a confirmed hold.
2. Return existing ticket if the same hold was already processed.

Input body (`GenerateETicketRequest`):

1. `holdID` (required)
2. `transactionID` (optional)
3. `userID` (required)
4. `eventID` (required)
5. `seatID` (required)
6. `seatNumber` (required)
7. `correlationID` (optional)
8. `metadata` (optional)

Success responses:

1. `201` ticket created
2. `200` idempotent replay (ticket already exists for hold)

Output body (`GenerateETicketResponse`):

1. `ticketID`
2. `holdID`
3. `status`
4. `issuedAt`
5. `seatNumber`

Common error status codes:

1. `400` invalid request payload
2. `500` internal error

#### B) GET /eticket/hold/{holdID}

Purpose:

1. Read ticket details by hold identifier.

Path input:

1. `holdID` (required)

Success response:

1. `200`

Output body (`GetETicketByHoldResponse`):

1. `ticketID`
2. `holdID`
3. `userID`
4. `eventID`
5. `seatID`
6. `seatNumber`
7. `status`
8. `issuedAt`

Common error status codes:

1. `404` not found
2. `400` invalid holdID
3. `500` internal error

#### C) GET /eticket/validate

Purpose:

1. Validate ownership and business status before cancellation/transfer orchestration.

Inputs:

1. `ticketID` (required)
2. `userID` (required)

Pass these as query string parameters for this GET endpoint.

Success response:

1. `200` with validation result body

Output body (`ValidateTicketResponse`):

1. `valid` (Boolean)
2. `reason` (Text)
3. `status` (Text)

Common error status codes:

1. `403` owner mismatch
2. `404` ticket not found
3. `400` invalid inputs
4. `500` internal error

#### D) PUT /etickets/status/{ticketID}

Purpose:

1. Transition ticket status for controlled lifecycle changes.

Path input:

1. `ticketID` (required)

Body (`UpdateTicketStatusRequest`):

1. `status` (required)
2. `correlationID` (optional)

Allowed transitions:

1. `VALID -> USED`
2. `VALID -> CANCELLED`
3. `VALID -> CANCELLATION_IN_PROGRESS`
4. `CANCELLATION_IN_PROGRESS -> CANCELLED`

Success response:

1. `200`

Output body (`UpdateTicketStatusResponse`):

1. `ticketID`
2. `oldStatus`
3. `newStatus`
4. `updatedAt`

Common error status codes:

1. `400` invalid request or unsupported status value
2. `404` ticket not found
3. `409` invalid transition
4. `500` internal error

#### E) POST /etickets/update

Purpose:

1. Execute `CANCEL_ONLY`.
2. Execute `TRANSFER_AND_REISSUE` (cancel old ticket, create new valid ticket).

Body (`UpdateETicketsRequest`):

1. `oldTicketID` (required)
2. `newOwnerUserID` (required for `TRANSFER_AND_REISSUE`)
3. `newHoldID` (required for `TRANSFER_AND_REISSUE`)
4. `newSeatID` (required for `TRANSFER_AND_REISSUE`)
5. `newSeatNumber` (required for `TRANSFER_AND_REISSUE`)
6. `operation` (required; values: `CANCEL_ONLY`, `TRANSFER_AND_REISSUE`)
7. `correlationID` (optional)
8. `newTransactionID` (optional; recommended for `TRANSFER_AND_REISSUE`)

Transfer transaction mapping rule:

1. If `newTransactionID` is present, new ticket `TransactionId = newTransactionID`.
2. If `newTransactionID` is blank, fallback to `OldTicket.TransactionId`.

Success responses:

1. `200` cancel-only completed
2. `200` transfer-and-reissue completed

Output body (`UpdateETicketsResponse`):

1. `operation`
2. `oldTicketStatus`
3. `newTicketID` (empty string for cancel-only)

Common error status codes:

1. `400` invalid request, missing transfer fields, invalid operation
2. `404` old ticket not found
3. `500` internal error

### 19.4 Orchestrator Call Sequencing Recommendations

For cancellation flow:

1. Call `GET /eticket/validate`.
2. If valid, call `PUT /etickets/status/{ticketID}` to `CANCELLATION_IN_PROGRESS` when needed.
3. After payment/refund outcome, call `POST /etickets/update` with the chosen operation.

For transfer/reissue flow:

1. Complete payment setup in Payment Service first.
2. Pass `newTransactionID` from payment context into `POST /etickets/update`.
3. Persist returned `newTicketID` in orchestrator domain records and notifications.

### 19.5 Request/Response Examples (Orchestrator Ready)

#### Example 1: Validate ownership before cancellation

Request:

```
GET /eticket/validate?ticketID=TKT-9988&userID=U-001
```

Success response (`200`):

```json
{
  "valid": true,
  "reason": "OK",
  "status": "VALID"
}
```

Owner mismatch (`403`):

```json
{
  "valid": false,
  "reason": "OWNER_MISMATCH",
  "status": "VALID"
}
```

#### Example 2: Mark ticket as cancellation in progress

Request:

```json
PUT /etickets/status/TKT-9988
{
   "status": "CANCELLATION_IN_PROGRESS",
   "correlationID": "corr-123"
}
```

Success response (`200`):

```json
{
  "ticketID": "TKT-9988",
  "oldStatus": "VALID",
  "newStatus": "CANCELLATION_IN_PROGRESS",
  "updatedAt": "2026-04-04T10:30:00Z"
}
```

#### Example 3: Cancel only in UpdateETickets

Request:

```json
POST /etickets/update
{
   "oldTicketID": "TKT-9988",
   "operation": "CANCEL_ONLY",
   "correlationID": "corr-123"
}
```

Success response (`200`):

```json
{
  "operation": "CANCEL_ONLY",
  "oldTicketStatus": "CANCELLED",
  "newTicketID": ""
}
```

#### Example 4: Transfer and reissue with new transaction ID

Request:

```json
POST /etickets/update
{
   "oldTicketID": "TKT-9988",
   "newOwnerUserID": "U-077",
   "newHoldID": "H-002",
   "newSeatID": "S-42",
   "newSeatNumber": "D12",
   "operation": "TRANSFER_AND_REISSUE",
   "correlationID": "corr-456",
   "newTransactionID": "TXN-90001"
}
```

Success response (`200`):

```json
{
  "operation": "TRANSFER_AND_REISSUE",
  "oldTicketStatus": "CANCELLED",
  "newTicketID": "TKT-9989"
}
```

Validation failure (`400`) example:

```json
{
  "operation": "TRANSFER_AND_REISSUE",
  "oldTicketStatus": "CANCELLED",
  "newTicketID": ""
}
```

### 19.6 Client Handling Rules

1. Always check HTTP status code first.
2. Treat non-2xx as business/validation/system failure based on status code.
3. Use returned `OutBody` fields for endpoint-specific details.
4. Log and propagate `correlationID` across all orchestrated calls.
5. Scenario docs no longer mention gRPC for ticket validation.
6. All payloads use UUID-style identifiers.

If any item is false, keep working.
