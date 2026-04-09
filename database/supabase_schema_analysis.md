# TicketBlitz Supabase Database Schema Analysis

Generated on: 2026-04-09
Target project: `cpxcpvcfbohvpiubbujg`

## 0) Scope, Method, and Evidence Sources

This document is based on live schema introspection and workload evidence, not assumptions.

Evidence used:
- Supabase PostgREST OpenAPI snapshot from `https://cpxcpvcfbohvpiubbujg.supabase.co/rest/v1/` (schema title: `standard public schema`, version `14.4`).
- Live table cardinalities and status distributions queried via PostgREST with service role credentials.
- Repository query patterns from service code (`inventory-service`, `event-service`, `pricing-service`, `waitlist-service`, `payment-service`, `user-service`).
- Existing project docs with live migration/security notes (`docs/tests/ExpirySchedulerManualSwaggerTestSuite.md`).
- Context7 Supabase documentation for RLS/indexing/migration best practices.

Limitations (important):
- PostgREST OpenAPI does not fully expose all physical index definitions, all CHECK constraints, or all RLS policies.
- Therefore, index and policy sections combine verified facts + high-confidence recommendations, and include verification SQL to close remaining gaps.

---

## 1) Requirements Analysis

### 1.1 What data is stored?
TicketBlitz stores:
- Identity and authorization: `users`, `user_roles`
- Event catalog and inventory: `events`, `seat_categories`, `seats`, `inventory_event_state`
- Reservation workflow: `seat_holds`, `waitlist_entries`
- Payments and refunds: `transactions`, `payment_webhook_events`, `cancellation_requests`, `refund_attempts`
- Pricing and campaigns: `flash_sales`, `price_changes`
- Integration/outbox: `integration_events` (partitioned event log)
- Reporting/read models: `v_waitlist_ranked`, `mv_sales_velocity_hourly`

### 1.2 Entity relationships
High-level cardinality:
- `events` 1:N `seat_categories`, `seats`, `seat_holds`, `waitlist_entries`, `transactions`, `flash_sales`, `price_changes`
- `seat_categories` 1:N `seats`, `seat_holds`, `waitlist_entries`, `price_changes`
- `seats` 1:N `seat_holds` (historical holds across time)
- `seat_holds` 1:N `transactions`, 1:N `waitlist_entries` (via offered hold linkage), 1:N `cancellation_requests`
- `cancellation_requests` 1:N `refund_attempts`
- `users` 1:N across operational workflow tables

### 1.3 Most common queries (from code)
Observed query patterns:
- Inventory reads:
  - `seat_categories` by `(event_id, category_code)`
  - `seats` by `(event_id, category_id, status)`
  - `seat_holds` by `hold_id`
- Waitlist reads:
  - `waitlist_entries` by `(event_id, category_id, status)` ordered by `(joined_at, waitlist_id)`
  - `waitlist_entries` by `hold_id` ordered by `updated_at desc`
  - `v_waitlist_ranked` by `waitlist_id`
- Pricing reads:
  - `flash_sales` by `(event_id, status, ends_at)` and `(event_id, starts_at desc)`
  - `price_changes` by `(event_id, changed_at desc)`
- Payment reads:
  - `transactions` by `transaction_id`, `hold_id`, `stripe_payment_intent_id`
  - `cancellation_requests` by `hold_id` ordered `requested_at desc`
  - `refund_attempts` by `(cancellation_request_id, status)` ordered `attempted_at desc`
- User reads:
  - `users` by `user_id`, fallback `auth_user_id`, filtered by `deleted_at is null`, ordered `created_at`

### 1.4 Read/write ratio (inferred)
Current dataset is still modest, but workflow tables already show write-heavy behavior:
- Write-heavy: `seat_holds`, `transactions`, `payment_webhook_events`, `integration_events`, `cancellation_requests`, `refund_attempts`
- Mixed: `waitlist_entries`, `flash_sales`, `price_changes`
- Mostly read-heavy/reference: `events`, `seat_categories`, `users` (outside sign-up bursts)
- Analytics read-heavy: `mv_sales_velocity_hourly`

### 1.5 Scalability requirements
Domain requirements imply:
- High concurrency on hold/create/confirm/release paths
- Idempotent payment and webhook handling
- Efficient queue ordering for waitlist promotions
- Time-series growth for outbox/events and transactions
- Operational observability and replay support

### 1.6 Data retention requirements
Live timestamps indicate operational history retention currently spans weeks to months and includes completed/expired states.
Retention should be explicit by table class:
- Hot operational: 30-90 days (`seat_holds`, `waitlist_entries`, pending webhook/refund work)
- Financial/legal: 7 years (`transactions`, refund artifacts)
- Integration logs: tiered retention (hot + archive)
- Soft-delete entities (`users`, `events`, `seat_categories`): keep tombstones for audit/restoration windows

---

## 2) Current Exposed Schema Inventory

### 2.1 Base tables (15)
- `users`
- `events`
- `seat_categories`
- `seats`
- `seat_holds`
- `waitlist_entries`
- `transactions`
- `payment_webhook_events`
- `cancellation_requests`
- `refund_attempts`
- `flash_sales`
- `price_changes`
- `inventory_event_state`
- `integration_events` (partitioned)
- `user_roles`

### 2.2 Views/read models (2)
- `v_waitlist_ranked` (queue positions)
- `mv_sales_velocity_hourly` (hourly sales aggregate)

### 2.3 RPC functions (6)
- `inventory_create_hold`
- `inventory_confirm_hold`
- `inventory_release_hold`
- `inventory_expire_holds`
- `current_user_role`
- `is_current_user_organiser`

---

## 3) Live Data Profile (2026-04-09 snapshot)

### 3.1 Table cardinalities
| Relation | Rows |
|---|---:|
| `price_changes` | 212 |
| `integration_events` | 171 |
| `seat_holds` | 167 |
| `payment_webhook_events` | 142 |
| `transactions` | 121 |
| `seats` | 84 |
| `refund_attempts` | 54 |
| `flash_sales` | 40 |
| `cancellation_requests` | 39 |
| `waitlist_entries` | 34 |
| `seat_categories` | 33 |
| `users` | 29 |
| `user_roles` | 23 |
| `events` | 12 |
| `inventory_event_state` | 11 |
| `mv_sales_velocity_hourly` | 4 |
| `v_waitlist_ranked` | 2 |

### 3.2 Workflow status distributions
- `events.status`: ACTIVE 7, SCHEDULED 4, CANCELLED 1
- `flash_sales.status`: ENDED 40
- `seats.status`: AVAILABLE 56, SOLD 25, PENDING_WAITLIST 3
- `seat_holds.status`: CONFIRMED 72, EXPIRED 57, RELEASED 38
- `transactions.status`: PENDING 43, SUCCEEDED 38, REFUND_SUCCEEDED 28, REFUND_FAILED 7, FAILED 3, REFUND_PENDING 2
- `waitlist_entries.status`: CANCELLED 16, EXPIRED 9, CONFIRMED 7, WAITING 2
- `cancellation_requests.status`: COMPLETED 27, CANCELLATION_IN_PROGRESS 8, PROCESSING_REFUND 2, ELIGIBLE 1, REJECTED 1
- `refund_attempts.status`: SUCCEEDED 28, FAILED 25, PENDING 1

### 3.3 Retention window indicators (created_at min/max)
| Table | Oldest | Newest |
|---|---|---|
| `seat_holds` | 2026-03-18 | 2026-04-09 |
| `transactions` | 2026-03-18 | 2026-04-09 |
| `waitlist_entries` | 2026-03-18 | 2026-04-08 |
| `cancellation_requests` | 2026-03-24 | 2026-05-31 |
| `refund_attempts` | 2026-03-24 | 2026-04-09 |
| `flash_sales` | 2026-03-24 | 2026-04-08 |
| `price_changes` | 2026-03-24 | 2026-04-08 |
| `events` | 2026-04-01 | 2026-04-04 |
| `seat_categories` | 2026-04-01 | 2026-04-04 |
| `users` | 2026-04-01 | 2026-04-08 |

Note: `cancellation_requests` includes future-dated test/seed timestamps relative to generation date.

---

## 4) Detailed Data Model and Constraints

## 4.1 Core keys and relationships

Primary keys (from OpenAPI definition metadata):
- UUID surrogate PKs on most tables (`users`, `events`, `seat_categories`, `seats`, `seat_holds`, `waitlist_entries`, `transactions`, `cancellation_requests`, `refund_attempts`, `flash_sales`, `price_changes`)
- Text PK on `payment_webhook_events.webhook_event_id`
- Partition-friendly composite PK on `integration_events(event_id, occurred_at)`
- `inventory_event_state.event_id` serves as PK and FK to `events`
- `user_roles.user_id` is marked as PK in exposed metadata (verify whether composite key also exists physically)

Foreign keys are consistently modeled across workflow chains:
- Inventory chain: `events` -> `seat_categories` -> `seats` -> `seat_holds`
- Booking/payment chain: `seat_holds` -> `transactions` -> `cancellation_requests` -> `refund_attempts`
- Waitlist chain: `waitlist_entries` links to `events`, `seat_categories`, `users`, optional `seat_holds`
- Promotion/price chain: `flash_sales` -> `price_changes`; `inventory_event_state.active_flash_sale_id`

### 4.2 Advanced and denormalized fields
- `jsonb`: `metadata`, `context`, `provider_response`, `provider_payload`, `payload`, `headers`, `config`
- `tsvector`: `events.search_vector`, `users.search_vector`
- `tstzrange`: `flash_sales.active_window`
- `text[]`: `integration_events.waitlist_emails`
- Soft delete columns: `users.deleted_at`, `events.deleted_at`, `seat_categories.deleted_at`

### 4.3 Enumerated state machines
- `event_status_t`: SCHEDULED, ACTIVE, FLASH_SALE_ACTIVE, CANCELLED, COMPLETED
- `seat_status_t`: AVAILABLE, PENDING_WAITLIST, HELD, SOLD
- `hold_status_t`: HELD, CONFIRMED, EXPIRED, RELEASED
- `hold_release_reason_t`: PAYMENT_TIMEOUT, CANCELLATION, MANUAL_RELEASE, SYSTEM_CLEANUP
- `waitlist_status_t`: WAITING, HOLD_OFFERED, CONFIRMED, EXPIRED, CANCELLED
- `transaction_status_t`: PENDING, SUCCEEDED, FAILED, REFUND_PENDING, REFUND_SUCCEEDED, REFUND_FAILED
- `refund_attempt_status_t`: PENDING, SUCCEEDED, FAILED
- `cancellation_status_t`: REQUESTED, ELIGIBLE, REJECTED, PROCESSING_REFUND, REFUND_SUCCEEDED, REFUND_FAILED, CANCELLATION_IN_PROGRESS, COMPLETED
- `flash_sale_status_t`: ACTIVE, ENDED, CANCELLED
- `price_change_reason_t`: FLASH_SALE, ESCALATION, REVERT, MANUAL_ADJUSTMENT
- `app_role_t`: fan, organiser

---

## 5) Normalization Assessment

### 5.1 1NF
Passes 1NF overall:
- Atomic scalar columns dominate operational tables.
- Repeating/flexible structures are intentionally isolated to `jsonb`/array fields.
- Stable row identity via PKs.

### 5.2 2NF
Passes 2NF for most entities due surrogate PK usage.
- Potential caveat: role modeling in `user_roles` should be verified if multi-role-per-user is expected.

### 5.3 3NF
Mostly 3NF, with intentional denormalization for performance/traceability:
- `seat_holds` and `transactions` duplicate `event_id/user_id/category_id` context to avoid expensive historical joins and preserve immutable snapshots.
- `inventory_event_state` is a compact cache/read model.
- `mv_sales_velocity_hourly` is a deliberate analytics denormalization.

### 5.4 Denormalization quality
Current denormalization choices are appropriate, but should be documented as contractual read models.

---

## 6) Key Design Review

Strengths:
- UUID surrogate keys fit distributed microservice architecture.
- FKs exist across critical workflows.
- Partition-friendly PK on `integration_events` supports growth.

Risks/gaps to verify:
1. `user_roles` key shape: exposed metadata indicates PK on `user_id`; verify if role uniqueness semantics are enforced as intended.
2. Idempotency uniqueness should be explicit for:
   - `seat_holds.idempotency_key` (nullable unique index)
   - `transactions.idempotency_key` (nullable unique index)
3. Business uniqueness candidates:
   - `events.event_code` (active rows)
   - `seat_categories(event_id, category_code)` (active rows)

---

## 7) Indexing Strategy (Evidence-Based)

## 7.1 Verified query predicates from code
Frequent predicates/sorts:
- Equality filters on UUID FKs (`event_id`, `category_id`, `user_id`, `hold_id`, `transaction_id`)
- State-driven filters (`status`)
- Time ordering (`created_at`, `updated_at`, `joined_at`, `changed_at`, `attempted_at`, `requested_at`)
- Search (`users` by `email/full_name`), potential FTS via `search_vector`

### 7.2 Recommended indexes to add/verify
Use `CONCURRENTLY` in production.

```sql
-- seat categories lookup
create unique index concurrently if not exists uq_seat_categories_event_code_active
on public.seat_categories (event_id, category_code)
where deleted_at is null;

-- seat availability checks
create index concurrently if not exists ix_seats_event_category_status
on public.seats (event_id, category_id, status);

create index concurrently if not exists ix_seats_available_only
on public.seats (event_id, category_id)
where status = 'AVAILABLE';

-- hold expiry and idempotency
create index concurrently if not exists ix_seat_holds_expiry_held
on public.seat_holds (hold_expires_at)
where status = 'HELD';

create unique index concurrently if not exists uq_seat_holds_idempotency_key
on public.seat_holds (idempotency_key)
where idempotency_key is not null;

-- waitlist queue operations
create index concurrently if not exists ix_waitlist_queue
on public.waitlist_entries (event_id, category_id, status, joined_at, waitlist_id);

create index concurrently if not exists ix_waitlist_hold_latest
on public.waitlist_entries (hold_id, updated_at desc);

create unique index concurrently if not exists uq_waitlist_active_user_event_category
on public.waitlist_entries (user_id, event_id, category_id)
where status in ('WAITING', 'HOLD_OFFERED');

-- flash sale and price history
create index concurrently if not exists ix_flash_sales_event_status_ends
on public.flash_sales (event_id, status, ends_at);

create index concurrently if not exists ix_price_changes_event_changed_at
on public.price_changes (event_id, changed_at desc);

-- transactions and payment integration
create unique index concurrently if not exists uq_transactions_idempotency_key
on public.transactions (idempotency_key)
where idempotency_key is not null;

create unique index concurrently if not exists uq_transactions_stripe_payment_intent
on public.transactions (stripe_payment_intent_id)
where stripe_payment_intent_id is not null;

create index concurrently if not exists ix_transactions_hold_created
on public.transactions (hold_id, created_at desc);

-- cancellation/refund workflows
create index concurrently if not exists ix_cancellation_requests_hold_requested
on public.cancellation_requests (hold_id, requested_at desc);

create unique index concurrently if not exists uq_refund_attempts_request_attempt
on public.refund_attempts (cancellation_request_id, attempt_no);

create index concurrently if not exists ix_refund_attempts_pending_latest
on public.refund_attempts (cancellation_request_id, status, attempted_at desc);

-- webhook processing
create index concurrently if not exists ix_payment_webhook_intent
on public.payment_webhook_events (payment_intent_id);

-- user lookup/search
create index concurrently if not exists ix_users_auth_user_id
on public.users (auth_user_id);

create unique index concurrently if not exists uq_users_email_active
on public.users (lower(email))
where deleted_at is null;

create index concurrently if not exists ix_users_search_vector
on public.users using gin (search_vector);

create index concurrently if not exists ix_events_search_vector
on public.events using gin (search_vector);
```

### 7.3 RLS index rule (Context7 + Supabase best practice)
For any column used in RLS predicates, add supporting indexes (often >100x improvement on large tables).

---

## 8) Data Types and Constraints Review

Good choices already present:
- `uuid` keys for distributed architecture
- `timestamptz` across lifecycle events
- `numeric` for monetary fields (correctly avoids float)
- enum domains for state transitions
- `jsonb` for extension points

Further constraints to consider:
- `CHECK (amount >= 0)` and `CHECK (refund_amount >= 0)`
- `CHECK (discount_percentage between 0 and 100)`
- `CHECK (escalation_percentage between 0 and 100)`
- `CHECK (ends_at > starts_at)` for `flash_sales`
- `CHECK (hold_expires_at >= created_at)` for `seat_holds`
- NOT NULL hardening after data cleanup/backfill for currently optional-but-logically-required fields

---

## 9) Relationship Patterns Review

- One-to-many: modeled correctly with FK on child side.
- Many-to-many: role assignment represented by `user_roles`.
- One-to-one style cache: `inventory_event_state` keyed by `event_id`.
- Temporal/self-referential patterns: not primary in this schema.

---

## 10) Performance and Scalability

### 10.1 Current strengths
- Partitioned outbox (`integration_events`) is the right foundation for event growth.
- Materialized analytics view (`mv_sales_velocity_hourly`) prevents heavy online aggregation.
- RPC encapsulation for hold transitions centralizes concurrency-sensitive logic.

### 10.2 Near-term optimizations
- Ensure all status+time hot paths have composite indexes.
- Add partial indexes for sparse active states (`HELD`, `WAITING`, `PENDING`).
- Monitor top slow queries with `pg_stat_statements` and Supabase advisors.

### 10.3 Medium-term partitioning candidates
As volumes rise significantly:
- `transactions` by month (`created_at`)
- `seat_holds` by month (`created_at`)
- Keep `integration_events` partition maintenance automated (create/drop/attach schedule)

---

## 11) Security and RLS Posture

Observed project notes indicate:
- RLS enabled on core tables.
- Prior advisor snapshot flagged `RLS Enabled No Policy` on multiple tables.

Actions:
1. Ensure every RLS-enabled table has explicit `SELECT/INSERT/UPDATE/DELETE` policies.
2. Validate policy predicates are index-backed.
3. Audit service-role usage boundaries (internal services only).

Reference links:
- Supabase linter lint `0008`: https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy
- Supabase RLS performance guidance (Context7-sourced): add indexes on policy-filter columns.

---

## 12) Migration Strategy (Safe and Reversible)

Recommended rollout pattern for production changes:
1. Add new columns nullable first.
2. Backfill in batches.
3. Add indexes concurrently.
4. Add constraints/NOT NULL after data is compliant.
5. Deploy app code that reads both old/new paths during transition.
6. Remove legacy columns only in a later migration window.

For your repo, tracked migrations currently include:
- `20260401100519 init_ticketblitz_core_schema`
- `20260401101813 seed_ticketblitz_scenarios_1_3`
- `20260402045843 add_missing_inventory_rpc_functions_20260402`
- `20260402082425 noop_check`
- `20260402082441 noop_revert`
- `20260402095203 fan_signup_autoconfirm_v2`

---

## 13) Open Verification SQL (To Close Remaining Blind Spots)

Run in Supabase SQL editor:

```sql
-- 1) Physical index inventory
select schemaname, tablename, indexname, indexdef
from pg_indexes
where schemaname = 'public'
order by tablename, indexname;

-- 2) Unique/check constraints
select conrelid::regclass as table_name,
       conname,
       contype,
       pg_get_constraintdef(oid) as definition
from pg_constraint
where connamespace = 'public'::regnamespace
order by conrelid::regclass::text, conname;

-- 3) RLS policies
select schemaname, tablename, policyname, permissive, roles, cmd, qual, with_check
from pg_policies
where schemaname = 'public'
order by tablename, policyname;

-- 4) Table bloat/size ranking
select relname as table_name,
       pg_size_pretty(pg_total_relation_size(oid)) as total_size
from pg_class
where relkind = 'r'
  and relnamespace = 'public'::regnamespace
order by pg_total_relation_size(oid) desc;
```

---

## 14) Schema Design Checklist

- [x] Is the schema properly normalized?
  - Mostly yes (3NF with intentional denormalization for performance and workflow snapshots).
- [x] Are all relationships defined with foreign keys?
  - Exposed metadata shows comprehensive FK coverage.
- [ ] Are appropriate indexes in place?
  - Partially unknown from OpenAPI alone; verification SQL required.
- [x] Are data types optimal?
  - Generally yes (`uuid`, `timestamptz`, `numeric`, enums, jsonb).
- [ ] Are constraints properly defined?
  - Core constraints exist, but additional CHECK/UNIQUE hardening is recommended.
- [x] Is naming consistent?
  - Strong consistency in snake_case naming and status enums.
- [x] Are migrations reversible?
  - Migration history is tracked; apply safe rollout sequencing for future changes.
- [ ] Is documentation complete?
  - This document provides baseline completeness; keep it versioned per migration.

---

## 15) Priority Action Plan

P0 (this sprint):
1. Verify current indexes, constraints, and RLS policies with SQL in section 13.
2. Add/confirm queue and workflow hot-path indexes (`waitlist_entries`, `seat_holds`, `transactions`, `refund_attempts`).
3. Add/confirm idempotency uniqueness constraints.
4. Resolve any `RLS Enabled No Policy` lints.

P1 (next sprint):
1. Enforce business uniqueness (`events.event_code`, `seat_categories(event_id, category_code)`).
2. Add FTS index verification (`events.search_vector`, `users.search_vector`).
3. Define formal retention + archival SOP for operational and financial tables.

P2 (scale readiness):
1. Partition `transactions` and `seat_holds` when volume thresholds are crossed.
2. Add automated partition lifecycle management for `integration_events` and future time-series tables.

---

## Appendix A) Full Enum Matrix

| Enum Type | Values |
|---|---|
| `event_status_t` | `SCHEDULED`, `ACTIVE`, `FLASH_SALE_ACTIVE`, `CANCELLED`, `COMPLETED` |
| `seat_status_t` | `AVAILABLE`, `PENDING_WAITLIST`, `HELD`, `SOLD` |
| `hold_status_t` | `HELD`, `CONFIRMED`, `EXPIRED`, `RELEASED` |
| `hold_release_reason_t` | `PAYMENT_TIMEOUT`, `CANCELLATION`, `MANUAL_RELEASE`, `SYSTEM_CLEANUP` |
| `waitlist_status_t` | `WAITING`, `HOLD_OFFERED`, `CONFIRMED`, `EXPIRED`, `CANCELLED` |
| `transaction_status_t` | `PENDING`, `SUCCEEDED`, `FAILED`, `REFUND_PENDING`, `REFUND_SUCCEEDED`, `REFUND_FAILED` |
| `refund_attempt_status_t` | `PENDING`, `SUCCEEDED`, `FAILED` |
| `cancellation_status_t` | `REQUESTED`, `ELIGIBLE`, `REJECTED`, `PROCESSING_REFUND`, `REFUND_SUCCEEDED`, `REFUND_FAILED`, `CANCELLATION_IN_PROGRESS`, `COMPLETED` |
| `flash_sale_status_t` | `ACTIVE`, `ENDED`, `CANCELLED` |
| `price_change_reason_t` | `FLASH_SALE`, `ESCALATION`, `REVERT`, `MANUAL_ADJUSTMENT` |
| `app_role_t` | `fan`, `organiser` |

---

## Appendix B) Full Relation Data Dictionary (Live OpenAPI)

This appendix lists all exposed relation columns from the live PostgREST OpenAPI snapshot.

### `users`
- `user_id uuid` (PK, default `gen_random_uuid()`)
- `full_name text` (required)
- `email text` (required)
- `phone text`
- `metadata jsonb` (required)
- `created_at timestamptz` (required, default `now()`)
- `updated_at timestamptz` (required, default `now()`)
- `deleted_at timestamptz`
- `search_vector tsvector`
- `auth_user_id uuid`

### `events`
- `event_id uuid` (PK, default `gen_random_uuid()`)
- `event_code text` (required)
- `name text` (required)
- `description text`
- `venue text` (required)
- `event_date timestamptz` (required)
- `booking_opens_at timestamptz`
- `booking_closes_at timestamptz`
- `total_capacity integer` (required)
- `status event_status_t` (required, default `SCHEDULED`)
- `metadata jsonb` (required)
- `created_at timestamptz` (required, default `now()`)
- `updated_at timestamptz` (required, default `now()`)
- `deleted_at timestamptz`
- `search_vector tsvector`

### `seat_categories`
- `category_id uuid` (PK, default `gen_random_uuid()`)
- `event_id uuid` (required, FK -> `events.event_id`)
- `category_code text` (required)
- `name text` (required)
- `base_price numeric` (required)
- `current_price numeric` (required)
- `currency char(3)` (required, default `SGD`)
- `total_seats integer` (required)
- `is_active boolean` (required, default `true`)
- `sort_order smallint` (required, default `100`)
- `metadata jsonb` (required)
- `created_at timestamptz` (required, default `now()`)
- `updated_at timestamptz` (required, default `now()`)
- `deleted_at timestamptz`

### `seats`
- `seat_id uuid` (PK, default `gen_random_uuid()`)
- `event_id uuid` (required, FK -> `events.event_id`)
- `category_id uuid` (required, FK -> `seat_categories.category_id`)
- `seat_number text` (required)
- `status seat_status_t` (required, default `AVAILABLE`)
- `version integer` (required, default `1`)
- `sold_at timestamptz`
- `metadata jsonb` (required)
- `created_at timestamptz` (required, default `now()`)
- `updated_at timestamptz` (required, default `now()`)

### `seat_holds`
- `hold_id uuid` (PK, default `gen_random_uuid()`)
- `seat_id uuid` (required, FK -> `seats.seat_id`)
- `event_id uuid` (required, FK -> `events.event_id`)
- `category_id uuid` (required, FK -> `seat_categories.category_id`)
- `user_id uuid` (required, FK -> `users.user_id`)
- `from_waitlist boolean` (required, default `false`)
- `hold_expires_at timestamptz` (required)
- `status hold_status_t` (required, default `HELD`)
- `release_reason hold_release_reason_t`
- `amount numeric` (required)
- `currency char(3)` (required, default `SGD`)
- `idempotency_key text`
- `correlation_id uuid` (required, default `gen_random_uuid()`)
- `confirmed_at timestamptz`
- `released_at timestamptz`
- `expired_at timestamptz`
- `metadata jsonb` (required)
- `created_at timestamptz` (required, default `now()`)
- `updated_at timestamptz` (required, default `now()`)

### `waitlist_entries`
- `waitlist_id uuid` (PK, default `gen_random_uuid()`)
- `event_id uuid` (required, FK -> `events.event_id`)
- `category_id uuid` (required, FK -> `seat_categories.category_id`)
- `user_id uuid` (required, FK -> `users.user_id`)
- `hold_id uuid` (FK -> `seat_holds.hold_id`)
- `status waitlist_status_t` (required, default `WAITING`)
- `joined_at timestamptz` (required, default `now()`)
- `offered_at timestamptz`
- `confirmed_at timestamptz`
- `expired_at timestamptz`
- `priority_score numeric` (required, default `0`)
- `source text` (required, default `PUBLIC`)
- `metadata jsonb` (required)
- `created_at timestamptz` (required, default `now()`)
- `updated_at timestamptz` (required, default `now()`)

### `transactions`
- `transaction_id uuid` (PK, default `gen_random_uuid()`)
- `hold_id uuid` (required, FK -> `seat_holds.hold_id`)
- `event_id uuid` (required, FK -> `events.event_id`)
- `user_id uuid` (required, FK -> `users.user_id`)
- `amount numeric` (required)
- `currency char(3)` (required, default `SGD`)
- `stripe_payment_intent_id text`
- `stripe_charge_id text`
- `status transaction_status_t` (required, default `PENDING`)
- `failure_reason text`
- `refund_amount numeric` (required, default `0`)
- `refund_status refund_attempt_status_t`
- `refund_requested_at timestamptz`
- `refunded_at timestamptz`
- `idempotency_key text`
- `correlation_id uuid` (required, default `gen_random_uuid()`)
- `provider_response jsonb` (required)
- `metadata jsonb` (required)
- `created_at timestamptz` (required, default `now()`)
- `updated_at timestamptz` (required, default `now()`)

### `payment_webhook_events`
- `webhook_event_id text` (PK)
- `payment_intent_id text`
- `hold_id uuid` (FK -> `seat_holds.hold_id`)
- `event_type text` (required)
- `payload jsonb` (required)
- `received_at timestamptz` (required, default `now()`)
- `processed_at timestamptz`
- `processing_status text` (required, default `RECEIVED`)
- `error_message text`

### `cancellation_requests`
- `cancellation_request_id uuid` (PK, default `gen_random_uuid()`)
- `hold_id uuid` (required, FK -> `seat_holds.hold_id`)
- `transaction_id uuid` (FK -> `transactions.transaction_id`)
- `event_id uuid` (required, FK -> `events.event_id`)
- `user_id uuid` (required, FK -> `users.user_id`)
- `requested_at timestamptz` (required, default `now()`)
- `policy_cutoff_at timestamptz` (required)
- `is_policy_eligible boolean` (required)
- `status cancellation_status_t` (required, default `REQUESTED`)
- `reason text`
- `fee_percentage numeric` (required, default `10`)
- `refund_amount numeric` (required, default `0`)
- `attempt_count integer` (required, default `0`)
- `last_attempt_at timestamptz`
- `resolved_at timestamptz`
- `metadata jsonb` (required)
- `created_at timestamptz` (required, default `now()`)
- `updated_at timestamptz` (required, default `now()`)

### `refund_attempts`
- `refund_attempt_id uuid` (PK, default `gen_random_uuid()`)
- `cancellation_request_id uuid` (required, FK -> `cancellation_requests.cancellation_request_id`)
- `transaction_id uuid` (FK -> `transactions.transaction_id`)
- `attempt_no integer` (required)
- `status refund_attempt_status_t` (required, default `PENDING`)
- `provider_reference text`
- `error_code text`
- `error_message text`
- `provider_payload jsonb` (required)
- `attempted_at timestamptz` (required, default `now()`)
- `completed_at timestamptz`
- `created_at timestamptz` (required, default `now()`)

### `flash_sales`
- `flash_sale_id uuid` (PK, default `gen_random_uuid()`)
- `event_id uuid` (required, FK -> `events.event_id`)
- `discount_percentage numeric` (required)
- `escalation_percentage numeric` (required, default `0`)
- `starts_at timestamptz` (required, default `now()`)
- `ends_at timestamptz` (required)
- `status flash_sale_status_t` (required, default `ACTIVE`)
- `launched_by_user_id uuid` (FK -> `users.user_id`)
- `config jsonb` (required)
- `ended_at timestamptz`
- `created_at timestamptz` (required, default `now()`)
- `updated_at timestamptz` (required, default `now()`)
- `active_window tstzrange`

### `price_changes`
- `change_id uuid` (PK, default `gen_random_uuid()`)
- `flash_sale_id uuid` (FK -> `flash_sales.flash_sale_id`)
- `event_id uuid` (required, FK -> `events.event_id`)
- `category_id uuid` (required, FK -> `seat_categories.category_id`)
- `reason price_change_reason_t` (required)
- `old_price numeric` (required)
- `new_price numeric` (required)
- `changed_at timestamptz` (required, default `now()`)
- `changed_by text` (required, default `SYSTEM`)
- `context jsonb` (required)
- `created_at timestamptz` (required, default `now()`)

### `inventory_event_state`
- `event_id uuid` (PK, required, FK -> `events.event_id`)
- `flash_sale_active boolean` (required, default `false`)
- `active_flash_sale_id uuid` (FK -> `flash_sales.flash_sale_id`)
- `last_sold_out_category text`
- `last_sold_out_at timestamptz`
- `metadata jsonb` (required)
- `updated_at timestamptz` (required, default `now()`)

### `integration_events` (partitioned)
- `event_id uuid` (PK part, required, default `gen_random_uuid()`)
- `occurred_at timestamptz` (PK part, required, default `now()`)
- `producer_service text` (required)
- `aggregate_type text` (required)
- `aggregate_id uuid`
- `event_name text` (required)
- `exchange_name text` (required, default `ticketblitz`)
- `routing_key text` (required)
- `payload jsonb` (required)
- `headers jsonb` (required)
- `waitlist_emails text[]` (required)
- `published boolean` (required, default `false`)
- `published_at timestamptz`
- `publish_error text`

### `user_roles`
- `user_id uuid` (required, PK in exposed metadata, FK -> `users.user_id`)
- `role app_role_t` (required)
- `assigned_at timestamptz` (required, default `now()`)
- `assigned_by uuid` (FK -> `users.user_id`)

### `v_waitlist_ranked` (view)
- `waitlist_id uuid`
- `event_id uuid` (FK -> `events.event_id`)
- `category_id uuid` (FK -> `seat_categories.category_id`)
- `user_id uuid` (FK -> `users.user_id`)
- `status waitlist_status_t`
- `joined_at timestamptz`
- `queue_position bigint`

### `mv_sales_velocity_hourly` (materialized view)
- `event_id uuid` (FK -> `events.event_id`)
- `category_id uuid` (FK -> `seat_categories.category_id`)
- `hour_bucket timestamptz`
- `successful_payment_count bigint`
- `gross_sales_amount numeric`
