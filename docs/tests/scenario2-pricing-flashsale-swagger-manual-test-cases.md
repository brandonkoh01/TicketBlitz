# Scenario 2 Manual Swagger Test Cases

## 1) Scope and Objective

This suite provides comprehensive manual test cases for Scenario 2 services:

- Pricing Service
- Flash Sale Orchestrator
- Pricing Orchestrator (worker)

Coverage goals align to critical business logic first:

1. Flash sale launch, escalation, and end lifecycle correctness
2. Input validation and error behavior
3. State consistency across Supabase tables
4. At-least-once sold-out processing behavior for worker flow
5. Public vs organiser-auth route behavior through Kong

This is a manual integration suite intended for Swagger-driven API execution plus SQL/log verification.

## 2) Project Context Used

Sources analyzed before writing this suite:

- `docs/Setup.md`
- `docs/Scenarios.md` (Scenario 2A/2B/2C)
- service runtime contracts in:
  - `backend/atomic/pricing-service/pricing.py`
  - `backend/composite/flash-sale-orchestrator/flash_sale_orchestrator.py`
  - `backend/composite/pricing-orchestrator/pricing_orchestrator.py`
- API gateway routes and auth in `kong/kong.yml`
- Live Supabase context from project `cpxcpvcfbohvpiubbujg`
- Context7 references:
  - Flask error/response handling guidance (`/pallets/flask`)
  - OpenAPI response/example semantics (`/websites/spec_openapis_oas_v3_1_0`)

## 3) Environment and Entry Points

### 3.1 Runtime endpoints

- Kong Gateway: `http://localhost:8000`
- Pricing Service direct: `http://localhost:5006`
- Flash Sale Orchestrator direct: `http://localhost:6003`
- Event Service direct: `http://localhost:5001`
- Inventory Service direct: `http://localhost:5003`
- Waitlist Service direct: `http://localhost:5005`

### 3.2 Auth model from Kong

- Protected organiser routes:
  - `POST /flash-sale/launch`
  - `POST /flash-sale/end`
- Public route:
  - `GET /flash-sale/{eventID}/status`
- Required organiser header:
  - `x-organiser-api-key: ticketblitz-organiser-dev-key`

### 3.3 Note on Swagger usage

Pricing Service and Flash Sale Orchestrator currently expose JSON APIs and health endpoints, but no dedicated `/docs` route in the current implementation. Run these test inputs via Swagger client tooling or equivalent request runner, using the exact method/path/body in each case.

Pricing Orchestrator is a worker with no HTTP API; its cases are verified via AMQP trigger input plus API/SQL/log outputs.

## 4) Global Components (Reusable)

### 4.1 Reusable headers

- `GC-HDR-JSON`
  - `Content-Type: application/json`
- `GC-HDR-ORG`
  - `x-organiser-api-key: ticketblitz-organiser-dev-key`

### 4.2 Reusable IDs and deterministic anchors

From Supabase project `cpxcpvcfbohvpiubbujg`:

- `GC-EVENT-ID`: `10000000-0000-0000-0000-000000000301`
- `GC-CAT1-ID`: `20000000-0000-0000-0000-000000000101`
- `GC-CAT2-ID`: `20000000-0000-0000-0000-000000000102`
- `GC-PEN-ID`: `20000000-0000-0000-0000-000000000103`
- `GC-ORG-USER-ID`: `00000000-0000-0000-0000-000000000004`

Current snapshot characteristics (at authoring time):

- CAT1 status: sold out in snapshot
- CAT2 status: sold out in snapshot
- PEN status: available

### 4.3 Reusable request templates

`GC-BODY-LAUNCH`

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "discountPercentage": "30",
  "durationMinutes": 30,
  "escalationPercentage": "20",
  "correlationID": "manual-suite-launch-001"
}
```

`GC-BODY-END`

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "flashSaleID": "<FLASH_SALE_ID>",
  "correlationID": "manual-suite-end-001"
}
```

`GC-BODY-ESCALATE`

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "flashSaleID": "<FLASH_SALE_ID>",
  "soldOutCategory": "CAT1",
  "remainingCategories": [
    {
      "categoryID": "20000000-0000-0000-0000-000000000103"
    }
  ],
  "soldAt": "2026-04-04T10:05:00Z"
}
```

### 4.4 Reusable expected response assertions

- `GC-ERR-JSON`
  - status code matches test case
  - response includes `error`
  - when downstream fails, response may include `details`
- `GC-LAUNCH-SUCCESS`
  - response includes: `status=success`, `eventID`, `flashSaleID`, `updatedPrices[]`, `expiresAt`, `broadcastPublished`, `correlationID`
- `GC-END-SUCCESS`
  - response includes: `status=success`, `eventID`, `flashSaleID`, `revertedPrices[]`, `broadcastPublished`, `correlationID`

### 4.5 Captured runtime variables

Capture these during run:

- `VAR_FLASH_SALE_ID`
- `VAR_LAUNCH_CORRELATION_ID`
- `VAR_END_CORRELATION_ID`
- `VAR_SOLD_AT`

## 5) Supabase Verification Queries (Reusable)

`Q-FLASH-SALES-BY-EVENT`

```sql
select flash_sale_id, status, discount_percentage, escalation_percentage, starts_at, ends_at, ended_at, created_at
from public.flash_sales
where event_id = '10000000-0000-0000-0000-000000000301'
order by created_at desc;
```

`Q-PRICE-CHANGES-BY-FLASH`

```sql
select change_id, flash_sale_id, category_id, reason, old_price, new_price, changed_at, changed_by, context
from public.price_changes
where flash_sale_id = '<FLASH_SALE_ID>'
order by changed_at desc;
```

`Q-INVENTORY-EVENT-STATE`

```sql
select event_id, flash_sale_active, active_flash_sale_id, last_sold_out_category, last_sold_out_at, updated_at
from public.inventory_event_state
where event_id = '10000000-0000-0000-0000-000000000301';
```

`Q-SEAT-CATEGORY-PRICES`

```sql
select category_id, category_code, base_price, current_price, is_active
from public.seat_categories
where event_id = '10000000-0000-0000-0000-000000000301'
order by sort_order;
```

## 6) Preflight Cases

| ID | Test name | Input | Expected output |
|---|---|---|---|
| PF-001 | should_return_healthy_pricing_service | `GET http://localhost:5006/health` | HTTP `200`, body has `status="ok"`, `service="pricing-service"` |
| PF-002 | should_return_healthy_flash_sale_orchestrator | `GET http://localhost:6003/health` | HTTP `200`, body has `status="ok"`, `service="flash-sale-orchestrator"` |
| PF-003 | should_verify_kong_route_protection_for_launch | `POST /flash-sale/launch` without `GC-HDR-ORG` | HTTP `401` (or Kong auth denial), no success payload |
| PF-004 | should_verify_public_flash_sale_status_route | `GET /flash-sale/{GC-EVENT-ID}/status` without `GC-HDR-ORG` | HTTP `200`, body has `event` object |
| PF-005 | should_confirm_event_and_categories_exist_in_db | Run `Q-SEAT-CATEGORY-PRICES` | 3 categories returned (CAT1, CAT2, PEN) |

## 7) Pricing Service Manual Cases

### Group A: Configure Flash Sale

| ID | Test name | Test input | Expected output |
|---|---|---|---|
| PRC-001 | should_create_flash_sale_when_configure_input_valid | `POST http://localhost:5006/pricing/flash-sale/configure` with JSON `{eventID: GC-EVENT-ID, discountPercentage:"30", durationMinutes:30, escalationPercentage:"20", launchedByUserID:GC-ORG-USER-ID}` | HTTP `200`; body includes `status=success`, non-empty `flashSaleID`, `eventID=GC-EVENT-ID`, `updatedPrices` with entries for CAT1/CAT2/PEN; capture `VAR_FLASH_SALE_ID` |
| PRC-002 | should_return_400_when_configure_body_missing | `POST .../configure` with empty body or non-JSON | HTTP `400`; `GC-ERR-JSON`, message includes `Request body must be a JSON object` |
| PRC-003 | should_return_400_when_event_id_invalid | configure body with `eventID:"not-a-uuid"` | HTTP `400`; error contains `eventID must be a valid UUID` |
| PRC-004 | should_return_400_when_discount_out_of_range | configure body with `discountPercentage:"101"` | HTTP `400`; error mentions allowed range |
| PRC-005 | should_return_400_when_duration_non_positive | configure body with `durationMinutes:0` | HTTP `400`; error contains `durationMinutes must be greater than 0` |
| PRC-006 | should_return_404_when_event_not_found | configure body with random valid UUID not in `events` | HTTP `404`; error contains `Event not found` |
| PRC-007 | should_return_409_when_active_sale_already_exists | call PRC-001 twice without ending first | Second response HTTP `409`; error contains `An active flash sale already exists for this event` |

### Group B: Get Active Flash Sale

| ID | Test name | Test input | Expected output |
|---|---|---|---|
| PRC-008 | should_return_active_flash_sale_when_exists | `GET http://localhost:5006/pricing/{GC-EVENT-ID}/flash-sale/active` | HTTP `200`; body has `flashSaleID=VAR_FLASH_SALE_ID`, `status=ACTIVE`, `discountPercentage`, `escalationPercentage`, `expiresAt` |
| PRC-009 | should_return_400_when_active_event_uuid_invalid | `GET .../pricing/not-a-uuid/flash-sale/active` | HTTP `400`; error includes `eventID must be a valid UUID` |

### Group C: Escalate Prices

| ID | Test name | Test input | Expected output |
|---|---|---|---|
| PRC-010 | should_escalate_selected_remaining_categories_when_valid_input | `POST http://localhost:5006/pricing/escalate` with `GC-BODY-ESCALATE` (replace `<FLASH_SALE_ID>`) | HTTP `200`; body has `eventID`, `flashSaleID`, `soldOutCategory`, `updatedPrices`, `count`; `count` equals number of valid active categories in `remainingCategories` |
| PRC-011 | should_return_400_when_remaining_categories_missing | escalate body without `remainingCategories` | HTTP `400`; error includes `remainingCategories must be an array` |
| PRC-012 | should_return_400_when_remaining_categories_not_array | escalate body with `remainingCategories:{}` | HTTP `400`; same error |
| PRC-013 | should_return_400_when_sold_out_category_missing | escalate body with empty `soldOutCategory` | HTTP `400`; error contains `soldOutCategory is required` |
| PRC-014 | should_return_400_when_remaining_item_not_object | escalate body with `remainingCategories:["bad"]` | HTTP `400`; error contains `remainingCategories items must be objects` |
| PRC-015 | should_return_400_when_remaining_category_uuid_invalid | escalate body with `remainingCategories:[{categoryID:"not-a-uuid"}]` | HTTP `400`; error contains `remainingCategories.categoryID must be a valid UUID` |
| PRC-016 | should_return_400_when_remaining_category_not_in_event | escalate body with valid UUID not belonging to event | HTTP `400`; error contains `remainingCategories contains category not found for event` |
| PRC-017 | should_return_404_when_no_active_sale_for_escalation | run escalate after sale ended | HTTP `404`; error contains `No active flash sale available for escalation` |

### Group D: End Flash Sale

| ID | Test name | Test input | Expected output |
|---|---|---|---|
| PRC-018 | should_end_active_flash_sale_when_valid_id | `PUT http://localhost:5006/pricing/{VAR_FLASH_SALE_ID}/end` | HTTP `200`; body has `flashSaleID=VAR_FLASH_SALE_ID`, `status=ENDED`, non-null `endedAt` |
| PRC-019 | should_return_ended_idempotently_when_called_again | repeat PRC-018 | HTTP `200`; body remains `status=ENDED` |
| PRC-020 | should_return_400_when_end_flash_sale_id_invalid | `PUT .../pricing/not-a-uuid/end` | HTTP `400`; error contains `flashSaleID must be a valid UUID` |
| PRC-021 | should_return_404_when_end_flash_sale_missing | `PUT .../pricing/<random-valid-uuid>/end` | HTTP `404`; error contains `Flash sale not found` |

### Group E: Snapshot and History

| ID | Test name | Test input | Expected output |
|---|---|---|---|
| PRC-022 | should_return_effective_pricing_snapshot_for_event | `GET http://localhost:5006/pricing/{GC-EVENT-ID}` | HTTP `200`; body has `eventID`, `eventStatus`, `flashSaleActive`, `categories[]`; each category contains `basePrice`, `currentPrice`, `status` |
| PRC-023 | should_return_400_when_snapshot_event_uuid_invalid | `GET .../pricing/not-a-uuid` | HTTP `400`; error includes `eventID must be a valid UUID` |
| PRC-024 | should_return_pricing_history_with_default_limit | `GET http://localhost:5006/pricing/{GC-EVENT-ID}/history` | HTTP `200`; body has `priceChanges[]`, `count`; each row has `reason`, `oldPrice`, `newPrice`, `changedAt`, `context` |
| PRC-025 | should_return_pricing_history_filtered_by_flash_sale | `GET .../history?flashSaleID={VAR_FLASH_SALE_ID}&limit=50` | HTTP `200`; rows belong to provided `flashSaleID` |
| PRC-026 | should_return_400_when_history_limit_invalid | `GET .../history?limit=0` | HTTP `400`; error contains `limit must be greater than 0` |
| PRC-027 | should_return_400_when_history_flash_sale_id_invalid | `GET .../history?flashSaleID=not-a-uuid` | HTTP `400`; error contains `flashSaleID must be a valid UUID` |

## 8) Flash Sale Orchestrator Manual Cases (Kong-facing)

### Group F: Launch

| ID | Test name | Test input | Expected output |
|---|---|---|---|
| FSO-001 | should_reject_launch_without_organiser_key | `POST http://localhost:8000/flash-sale/launch` with `GC-BODY-LAUNCH` but no `GC-HDR-ORG` | HTTP `401` (auth failure) |
| FSO-002 | should_launch_flash_sale_with_valid_organiser_key | same request with `GC-HDR-ORG` | HTTP `200`; response satisfies `GC-LAUNCH-SUCCESS`; capture `VAR_FLASH_SALE_ID` |
| FSO-003 | should_return_400_when_launch_event_id_invalid | launch with `eventID:"not-a-uuid"` | HTTP `400`; error contains `eventID must be a valid UUID` |
| FSO-004 | should_return_400_when_launch_discount_invalid | launch with `discountPercentage:"0"` or non-numeric | HTTP `400`; range/format error |
| FSO-005 | should_return_400_when_launch_duration_invalid | launch with `durationMinutes:0` | HTTP `400`; duration validation error |
| FSO-006 | should_return_downstream_error_payload_when_launch_fails_dependency | launch with valid request but induced downstream failure (service unavailable) | HTTP `503` or `504`; body includes `error="Flash sale launch failed"` and `details.service` |

### Group G: Status (Public)

| ID | Test name | Test input | Expected output |
|---|---|---|---|
| FSO-007 | should_return_flash_sale_status_publicly | `GET http://localhost:8000/flash-sale/{GC-EVENT-ID}/status` without organiser key | HTTP `200`; body has `event` and `pricing` objects |
| FSO-008 | should_return_400_when_status_event_id_invalid | `GET .../flash-sale/not-a-uuid/status` | HTTP `400`; error contains `eventID must be a valid UUID` |

### Group H: End

| ID | Test name | Test input | Expected output |
|---|---|---|---|
| FSO-009 | should_reject_end_without_organiser_key | `POST http://localhost:8000/flash-sale/end` with valid body but no key | HTTP `401` |
| FSO-010 | should_end_flash_sale_with_valid_key | `POST .../flash-sale/end` with `GC-HDR-ORG` and `GC-BODY-END` | HTTP `200`; response satisfies `GC-END-SUCCESS` |
| FSO-011 | should_return_400_when_end_flash_sale_id_missing_or_invalid | end body missing `flashSaleID` or invalid UUID | HTTP `400`; validation error |
| FSO-012 | should_return_downstream_error_payload_when_end_fails_dependency | end request with induced downstream failure | HTTP `503` or `504`; body has `error="Flash sale end failed"` and downstream `service` |

## 9) Pricing Orchestrator Worker Manual Cases

Pricing Orchestrator has no Swagger endpoint. These cases validate worker behavior through:

- AMQP input payload (manual publish)
- Swagger/API observable outputs (pricing/event snapshots)
- SQL verification (`price_changes`, `inventory_event_state`)
- worker logs

### 9.1 AMQP trigger template

`GC-AMQP-SOLDOUT`

```json
{
  "eventID": "10000000-0000-0000-0000-000000000301",
  "category": "CAT1",
  "flashSaleID": "<FLASH_SALE_ID>",
  "soldAt": "2026-04-04T10:05:00Z",
  "correlationID": "manual-worker-001"
}
```

### 9.2 Manual worker cases

| ID | Test name | Input | Expected output |
|---|---|---|---|
| POR-001 | should_process_valid_sold_out_event_and_create_escalation | Publish `GC-AMQP-SOLDOUT` to exchange `ticketblitz` routing key `category.sold_out` while sale is ACTIVE | Worker log contains `Processed sold-out event`; `Q-PRICE-CHANGES-BY-FLASH` includes new `reason=ESCALATION` rows with `context.soldOutCategory=CAT1` and matching `soldAt` |
| POR-002 | should_skip_duplicate_sold_out_event_for_same_sold_at | Publish same payload again with same `soldAt` and `flashSaleID` | No additional ESCALATION rows for same `(soldOutCategory, soldAt)` fingerprint |
| POR-003 | should_drop_event_when_flash_sale_not_active | End sale, then publish sold_out payload | No new ESCALATION rows; worker logs permanent skip reason (`No active flash sale` or mismatch) |
| POR-004 | should_skip_escalation_when_no_available_remaining_categories | Publish sold_out where all remaining categories are unavailable | Worker logs `No available categories remain for escalation`; no ESCALATION updates written |
| POR-005 | should_use_inventory_as_authority_for_remaining_categories | Keep only PEN available, publish CAT1 sold_out | ESCALATION affects only PEN category in `price_changes` and event category prices |
| POR-006 | should_eventually_process_after_transient_downstream_recovery | Temporarily break downstream (e.g. pricing service unreachable), publish sold_out, restore service | Initial transient failure logged; message retried; eventual processed log and ESCALATION row created (at-least-once behavior) |

## 10) End-to-End Sequence (Recommended Manual Run Order)

1. Run preflight PF-001..PF-005.
2. Run pricing configure PRC-001 and capture `VAR_FLASH_SALE_ID`.
3. Run active/snapshot/history checks PRC-008, PRC-022, PRC-024.
4. Run Kong launch test FSO-002 (or skip if PRC-001 already created active sale and conflict expected).
5. Run worker cases POR-001 and POR-005 using `VAR_FLASH_SALE_ID`.
6. Validate pricing history and DB (`Q-PRICE-CHANGES-BY-FLASH`, `Q-SEAT-CATEGORY-PRICES`).
7. End sale via FSO-010 and verify post-state (`Q-FLASH-SALES-BY-EVENT`, `Q-INVENTORY-EVENT-STATE`).
8. Run negative/idempotency checks: PRC-019, PRC-021, PRC-026, FSO-011.

## 11) Coverage Map

| Surface | Covered by case IDs |
|---|---|
| Pricing health | PF-001 |
| Pricing configure | PRC-001..PRC-007 |
| Pricing active | PRC-008..PRC-009 |
| Pricing escalate | PRC-010..PRC-017 |
| Pricing end | PRC-018..PRC-021 |
| Pricing snapshot/history | PRC-022..PRC-027 |
| Flash launch/status/end | FSO-001..FSO-012 |
| Worker trigger, dedupe, availability, retry | POR-001..POR-006 |

## 12) Expected Response and Assertion Guidance

- For dynamic fields (`flashSaleID`, timestamps, correlation IDs), assert presence and format, not exact fixed value.
- For money values, assert two-decimal string format where service returns normalized money fields.
- For error cases, assert both HTTP code and clear semantic `error` text.
- For worker flow, assert behavior via SQL and logs, not internal implementation details.
