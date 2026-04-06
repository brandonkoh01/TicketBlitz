-- TicketBlitz payment-service manual Swagger fixture setup
-- Target project: cpxcpvcfbohvpiubbujg
-- Run in Supabase SQL editor before executing manual payment Swagger tests.

begin;

-- ---------------------------------------------------------------------------
-- 0) Clean up deterministic manual fixture rows
-- ---------------------------------------------------------------------------

delete from public.refund_attempts
where refund_attempt_id in (
  '91b10000-0000-0000-0000-000000000001',
  '91b10000-0000-0000-0000-000000000002'
);

delete from public.cancellation_requests
where cancellation_request_id in (
  '9b100000-0000-0000-0000-000000000001',
  '9b100000-0000-0000-0000-000000000002'
);

delete from public.transactions
where transaction_id in (
  '7b100000-0000-0000-0000-000000000001',
  '7b100000-0000-0000-0000-000000000002',
  '7b100000-0000-0000-0000-000000000003',
  '7b100000-0000-0000-0000-000000000004',
  '7b100000-0000-0000-0000-000000000005',
  '7b100000-0000-0000-0000-000000000006'
);

delete from public.seat_holds
where hold_id in (
  '4b100000-0000-0000-0000-000000000001',
  '4b100000-0000-0000-0000-000000000002',
  '4b100000-0000-0000-0000-000000000003',
  '4b100000-0000-0000-0000-000000000004',
  '4b100000-0000-0000-0000-000000000005',
  '4b100000-0000-0000-0000-000000000006',
  '4b100000-0000-0000-0000-000000000007',
  '4b100000-0000-0000-0000-000000000008'
);

delete from public.seats
where seat_id in (
  '30000000-0000-0000-0000-000000000041',
  '30000000-0000-0000-0000-000000000042',
  '30000000-0000-0000-0000-000000000043'
);

delete from public.events
where event_id = '10000000-0000-0000-0000-000000000901';

-- ---------------------------------------------------------------------------
-- 1) Event fixture for outside-policy refund tests
-- ---------------------------------------------------------------------------

insert into public.events (
  event_id,
  event_code,
  name,
  description,
  venue,
  event_date,
  booking_opens_at,
  booking_closes_at,
  total_capacity,
  status,
  metadata
) values (
  '10000000-0000-0000-0000-000000000901',
  'EVT-901-POLICY-FIXTURE',
  'Payment Policy Boundary Fixture Event',
  'Fixture event for refund policy lockout test cases.',
  'TicketBlitz Test Venue',
  now() + interval '12 hours',
  now() - interval '7 days',
  now() + interval '10 hours',
  1,
  'ACTIVE',
  '{"fixture":"manual_swagger_suite"}'::jsonb
)
on conflict (event_id) do update
set
  event_code = excluded.event_code,
  name = excluded.name,
  description = excluded.description,
  venue = excluded.venue,
  event_date = excluded.event_date,
  booking_opens_at = excluded.booking_opens_at,
  booking_closes_at = excluded.booking_closes_at,
  total_capacity = excluded.total_capacity,
  status = excluded.status,
  metadata = excluded.metadata,
  updated_at = now();

-- ---------------------------------------------------------------------------
-- 1.5) Dedicated seats for HELD fixtures
-- ---------------------------------------------------------------------------
-- These seats avoid collisions with pre-existing HELD rows enforced by
-- seat_holds_active_seat_uk (unique seat_id for status='HELD').
insert into public.seats (
  seat_id,
  event_id,
  category_id,
  seat_number,
  status,
  version,
  metadata,
  created_at,
  updated_at
) values
(
  '30000000-0000-0000-0000-000000000041',
  '10000000-0000-0000-0000-000000000301',
  '20000000-0000-0000-0000-000000000103',
  'Z-041',
  'AVAILABLE',
  1,
  '{"fixture":"manual_swagger_suite"}'::jsonb,
  now(),
  now()
),
(
  '30000000-0000-0000-0000-000000000042',
  '10000000-0000-0000-0000-000000000301',
  '20000000-0000-0000-0000-000000000101',
  'Z-042',
  'AVAILABLE',
  1,
  '{"fixture":"manual_swagger_suite"}'::jsonb,
  now(),
  now()
),
(
  '30000000-0000-0000-0000-000000000043',
  '10000000-0000-0000-0000-000000000301',
  '20000000-0000-0000-0000-000000000101',
  'Z-043',
  'AVAILABLE',
  1,
  '{"fixture":"manual_swagger_suite"}'::jsonb,
  now(),
  now()
)
on conflict (seat_id) do update
set
  event_id = excluded.event_id,
  category_id = excluded.category_id,
  seat_number = excluded.seat_number,
  status = excluded.status,
  metadata = excluded.metadata,
  updated_at = now();

-- ---------------------------------------------------------------------------
-- 2) Hold fixtures
-- ---------------------------------------------------------------------------
-- H-VALID-HELD: used for payment/initiate happy path and idempotent replay.
insert into public.seat_holds (
  hold_id,
  seat_id,
  event_id,
  category_id,
  user_id,
  from_waitlist,
  hold_expires_at,
  status,
  amount,
  currency,
  idempotency_key,
  correlation_id,
  metadata,
  created_at,
  updated_at
) values (
  '4b100000-0000-0000-0000-000000000001',
  '30000000-0000-0000-0000-000000000041',
  '10000000-0000-0000-0000-000000000301',
  '20000000-0000-0000-0000-000000000103',
  '00000000-0000-0000-0000-000000000001',
  false,
  now() + interval '6 hours',
  'HELD',
  388.00,
  'SGD',
  'manual-swagger-held-01',
  gen_random_uuid(),
  '{"fixture":"manual_swagger_suite","label":"H_VALID_HELD"}'::jsonb,
  now(),
  now()
)
on conflict (hold_id) do update
set
  seat_id = excluded.seat_id,
  event_id = excluded.event_id,
  category_id = excluded.category_id,
  user_id = excluded.user_id,
  from_waitlist = excluded.from_waitlist,
  hold_expires_at = excluded.hold_expires_at,
  status = excluded.status,
  release_reason = null,
  amount = excluded.amount,
  currency = excluded.currency,
  idempotency_key = excluded.idempotency_key,
  confirmed_at = null,
  released_at = null,
  expired_at = null,
  metadata = excluded.metadata,
  updated_at = now();

-- H-EXPIRED-HELD: used for hold expired validation path.
insert into public.seat_holds (
  hold_id,
  seat_id,
  event_id,
  category_id,
  user_id,
  from_waitlist,
  hold_expires_at,
  status,
  amount,
  currency,
  idempotency_key,
  correlation_id,
  metadata,
  created_at,
  updated_at
) values (
  '4b100000-0000-0000-0000-000000000002',
  '30000000-0000-0000-0000-000000000042',
  '10000000-0000-0000-0000-000000000301',
  '20000000-0000-0000-0000-000000000101',
  '00000000-0000-0000-0000-000000000001',
  false,
  now() - interval '20 minutes',
  'HELD',
  160.00,
  'SGD',
  'manual-swagger-held-02',
  gen_random_uuid(),
  '{"fixture":"manual_swagger_suite","label":"H_EXPIRED_HELD"}'::jsonb,
  now() - interval '120 minutes',
  now()
)
on conflict (hold_id) do update
set
  hold_expires_at = excluded.hold_expires_at,
  status = excluded.status,
  amount = excluded.amount,
  updated_at = now();

-- H-HELD-SUCCEEDED: used to trigger "Payment already completed for this hold".
insert into public.seat_holds (
  hold_id,
  seat_id,
  event_id,
  category_id,
  user_id,
  from_waitlist,
  hold_expires_at,
  status,
  amount,
  currency,
  idempotency_key,
  correlation_id,
  metadata,
  created_at,
  updated_at
) values (
  '4b100000-0000-0000-0000-000000000003',
  '30000000-0000-0000-0000-000000000043',
  '10000000-0000-0000-0000-000000000301',
  '20000000-0000-0000-0000-000000000101',
  '00000000-0000-0000-0000-000000000002',
  false,
  now() + interval '6 hours',
  'HELD',
  144.00,
  'SGD',
  'manual-swagger-held-03',
  gen_random_uuid(),
  '{"fixture":"manual_swagger_suite","label":"H_HELD_SUCCEEDED"}'::jsonb,
  now(),
  now()
)
on conflict (hold_id) do update
set
  hold_expires_at = excluded.hold_expires_at,
  status = excluded.status,
  amount = excluded.amount,
  updated_at = now();

-- Supporting CONFIRMED holds for refund-status fixtures.
insert into public.seat_holds (
  hold_id,
  seat_id,
  event_id,
  category_id,
  user_id,
  from_waitlist,
  hold_expires_at,
  status,
  amount,
  currency,
  idempotency_key,
  correlation_id,
  confirmed_at,
  metadata,
  created_at,
  updated_at
) values
(
  '4b100000-0000-0000-0000-000000000004',
  '30000000-0000-0000-0000-000000000010',
  '10000000-0000-0000-0000-000000000301',
  '20000000-0000-0000-0000-000000000101',
  '00000000-0000-0000-0000-000000000002',
  false,
  now() - interval '1 day' + interval '10 minutes',
  'CONFIRMED',
  160.00,
  'SGD',
  'manual-swagger-held-04',
  gen_random_uuid(),
  now() - interval '1 day' + interval '11 minutes',
  '{"fixture":"manual_swagger_suite","label":"H_FAILED_STATUS"}'::jsonb,
  now() - interval '1 day',
  now()
),
(
  '4b100000-0000-0000-0000-000000000005',
  '30000000-0000-0000-0000-000000000020',
  '10000000-0000-0000-0000-000000000301',
  '20000000-0000-0000-0000-000000000102',
  '00000000-0000-0000-0000-000000000003',
  false,
  now() - interval '2 days' + interval '10 minutes',
  'CONFIRMED',
  168.00,
  'SGD',
  'manual-swagger-held-05',
  gen_random_uuid(),
  now() - interval '2 days' + interval '11 minutes',
  '{"fixture":"manual_swagger_suite","label":"H_PENDING_RECENT"}'::jsonb,
  now() - interval '2 days',
  now()
),
(
  '4b100000-0000-0000-0000-000000000006',
  '30000000-0000-0000-0000-000000000021',
  '10000000-0000-0000-0000-000000000301',
  '20000000-0000-0000-0000-000000000102',
  '00000000-0000-0000-0000-000000000005',
  false,
  now() - interval '3 days' + interval '10 minutes',
  'CONFIRMED',
  168.00,
  'SGD',
  'manual-swagger-held-06',
  gen_random_uuid(),
  now() - interval '3 days' + interval '11 minutes',
  '{"fixture":"manual_swagger_suite","label":"H_PENDING_STALE"}'::jsonb,
  now() - interval '3 days',
  now()
),
(
  '4b100000-0000-0000-0000-000000000007',
  '30000000-0000-0000-0000-000000000032',
  '10000000-0000-0000-0000-000000000301',
  '20000000-0000-0000-0000-000000000103',
  '00000000-0000-0000-0000-000000000004',
  false,
  now() - interval '4 days' + interval '10 minutes',
  'CONFIRMED',
  388.00,
  'SGD',
  'manual-swagger-held-07',
  gen_random_uuid(),
  now() - interval '4 days' + interval '11 minutes',
  '{"fixture":"manual_swagger_suite","label":"H_MISSING_PI"}'::jsonb,
  now() - interval '4 days',
  now()
),
(
  '4b100000-0000-0000-0000-000000000008',
  '30000000-0000-0000-0000-000000000012',
  '10000000-0000-0000-0000-000000000901',
  '20000000-0000-0000-0000-000000000101',
  '00000000-0000-0000-0000-000000000001',
  false,
  now() - interval '5 days' + interval '10 minutes',
  'CONFIRMED',
  388.00,
  'SGD',
  'manual-swagger-held-08',
  gen_random_uuid(),
  now() - interval '5 days' + interval '11 minutes',
  '{"fixture":"manual_swagger_suite","label":"H_POLICY_OUTSIDE"}'::jsonb,
  now() - interval '5 days',
  now()
)
on conflict (hold_id) do update
set
  status = excluded.status,
  amount = excluded.amount,
  confirmed_at = excluded.confirmed_at,
  hold_expires_at = excluded.hold_expires_at,
  updated_at = now();

-- ---------------------------------------------------------------------------
-- 3) Transaction fixtures
-- ---------------------------------------------------------------------------

insert into public.transactions (
  transaction_id,
  hold_id,
  event_id,
  user_id,
  amount,
  currency,
  stripe_payment_intent_id,
  stripe_charge_id,
  status,
  failure_reason,
  refund_amount,
  refund_status,
  refund_requested_at,
  refunded_at,
  idempotency_key,
  correlation_id,
  provider_response,
  metadata,
  created_at,
  updated_at
) values
(
  '7b100000-0000-0000-0000-000000000001',
  '4b100000-0000-0000-0000-000000000003',
  '10000000-0000-0000-0000-000000000301',
  '00000000-0000-0000-0000-000000000002',
  144.00,
  'SGD',
  'pi_manual_held_succeeded_001',
  null,
  'SUCCEEDED',
  null,
  0.00,
  null,
  null,
  null,
  'manual-swagger-tx-001',
  gen_random_uuid(),
  '{"fixture":"manual_swagger_suite"}'::jsonb,
  '{"fixture":"manual_swagger_suite","label":"TX_HELD_SUCCEEDED"}'::jsonb,
  now() - interval '30 minutes',
  now()
),
(
  '7b100000-0000-0000-0000-000000000002',
  '4b100000-0000-0000-0000-000000000004',
  '10000000-0000-0000-0000-000000000301',
  '00000000-0000-0000-0000-000000000002',
  160.00,
  'SGD',
  'pi_manual_failed_status_001',
  null,
  'FAILED',
  'Synthetic failed payment fixture',
  0.00,
  null,
  null,
  null,
  'manual-swagger-tx-002',
  gen_random_uuid(),
  '{"fixture":"manual_swagger_suite"}'::jsonb,
  '{"fixture":"manual_swagger_suite","label":"TX_FAILED_STATUS"}'::jsonb,
  now() - interval '1 day',
  now()
),
(
  '7b100000-0000-0000-0000-000000000003',
  '4b100000-0000-0000-0000-000000000005',
  '10000000-0000-0000-0000-000000000301',
  '00000000-0000-0000-0000-000000000003',
  168.00,
  'SGD',
  'pi_manual_pending_recent_001',
  null,
  'REFUND_PENDING',
  null,
  0.00,
  'PENDING',
  now() - interval '1 minute',
  null,
  'manual-swagger-tx-003',
  gen_random_uuid(),
  '{"fixture":"manual_swagger_suite"}'::jsonb,
  '{"fixture":"manual_swagger_suite","label":"TX_PENDING_RECENT"}'::jsonb,
  now() - interval '2 days',
  now()
),
(
  '7b100000-0000-0000-0000-000000000004',
  '4b100000-0000-0000-0000-000000000006',
  '10000000-0000-0000-0000-000000000301',
  '00000000-0000-0000-0000-000000000005',
  168.00,
  'SGD',
  'pi_manual_pending_stale_001',
  null,
  'REFUND_PENDING',
  null,
  0.00,
  'PENDING',
  now() - interval '10 minutes',
  null,
  'manual-swagger-tx-004',
  gen_random_uuid(),
  '{"fixture":"manual_swagger_suite"}'::jsonb,
  '{"fixture":"manual_swagger_suite","label":"TX_PENDING_STALE"}'::jsonb,
  now() - interval '3 days',
  now()
),
(
  '7b100000-0000-0000-0000-000000000005',
  '4b100000-0000-0000-0000-000000000007',
  '10000000-0000-0000-0000-000000000301',
  '00000000-0000-0000-0000-000000000004',
  388.00,
  'SGD',
  null,
  null,
  'SUCCEEDED',
  null,
  0.00,
  null,
  null,
  null,
  'manual-swagger-tx-005',
  gen_random_uuid(),
  '{"fixture":"manual_swagger_suite"}'::jsonb,
  '{"fixture":"manual_swagger_suite","label":"TX_MISSING_PI"}'::jsonb,
  now() - interval '4 days',
  now()
),
(
  '7b100000-0000-0000-0000-000000000006',
  '4b100000-0000-0000-0000-000000000008',
  '10000000-0000-0000-0000-000000000901',
  '00000000-0000-0000-0000-000000000001',
  388.00,
  'SGD',
  'pi_manual_policy_outside_001',
  null,
  'SUCCEEDED',
  null,
  0.00,
  null,
  null,
  null,
  'manual-swagger-tx-006',
  gen_random_uuid(),
  '{"fixture":"manual_swagger_suite"}'::jsonb,
  '{"fixture":"manual_swagger_suite","label":"TX_POLICY_OUTSIDE"}'::jsonb,
  now() - interval '5 days',
  now()
)
on conflict (transaction_id) do update
set
  status = excluded.status,
  failure_reason = excluded.failure_reason,
  refund_status = excluded.refund_status,
  refund_requested_at = excluded.refund_requested_at,
  refund_amount = excluded.refund_amount,
  stripe_payment_intent_id = excluded.stripe_payment_intent_id,
  updated_at = now();

-- ---------------------------------------------------------------------------
-- 4) Cancellation and refund-attempt fixtures for REFUND_PENDING edge tests
-- ---------------------------------------------------------------------------

insert into public.cancellation_requests (
  cancellation_request_id,
  hold_id,
  transaction_id,
  event_id,
  user_id,
  requested_at,
  policy_cutoff_at,
  is_policy_eligible,
  status,
  reason,
  fee_percentage,
  refund_amount,
  attempt_count,
  last_attempt_at,
  resolved_at,
  metadata,
  created_at,
  updated_at
) values
(
  '9b100000-0000-0000-0000-000000000001',
  '4b100000-0000-0000-0000-000000000005',
  '7b100000-0000-0000-0000-000000000003',
  '10000000-0000-0000-0000-000000000301',
  '00000000-0000-0000-0000-000000000003',
  now() - interval '2 minutes',
  now() + interval '30 days',
  true,
  'PROCESSING_REFUND',
  'Recent pending refund fixture',
  10.00,
  151.20,
  1,
  now() - interval '1 minute',
  null,
  '{"fixture":"manual_swagger_suite","label":"CR_PENDING_RECENT"}'::jsonb,
  now() - interval '2 minutes',
  now()
),
(
  '9b100000-0000-0000-0000-000000000002',
  '4b100000-0000-0000-0000-000000000006',
  '7b100000-0000-0000-0000-000000000004',
  '10000000-0000-0000-0000-000000000301',
  '00000000-0000-0000-0000-000000000005',
  now() - interval '12 minutes',
  now() + interval '30 days',
  true,
  'PROCESSING_REFUND',
  'Stale pending refund fixture',
  10.00,
  151.20,
  1,
  now() - interval '10 minutes',
  null,
  '{"fixture":"manual_swagger_suite","label":"CR_PENDING_STALE"}'::jsonb,
  now() - interval '12 minutes',
  now()
)
on conflict (cancellation_request_id) do update
set
  status = excluded.status,
  attempt_count = excluded.attempt_count,
  last_attempt_at = excluded.last_attempt_at,
  resolved_at = excluded.resolved_at,
  updated_at = now();

insert into public.refund_attempts (
  refund_attempt_id,
  cancellation_request_id,
  transaction_id,
  attempt_no,
  status,
  provider_reference,
  error_code,
  error_message,
  provider_payload,
  attempted_at,
  completed_at,
  created_at
) values
(
  '91b10000-0000-0000-0000-000000000001',
  '9b100000-0000-0000-0000-000000000001',
  '7b100000-0000-0000-0000-000000000003',
  1,
  'PENDING',
  null,
  null,
  null,
  '{"fixture":"manual_swagger_suite","label":"RA_PENDING_RECENT"}'::jsonb,
  now() - interval '1 minute',
  null,
  now() - interval '1 minute'
),
(
  '91b10000-0000-0000-0000-000000000002',
  '9b100000-0000-0000-0000-000000000002',
  '7b100000-0000-0000-0000-000000000004',
  1,
  'PENDING',
  null,
  null,
  null,
  '{"fixture":"manual_swagger_suite","label":"RA_PENDING_STALE"}'::jsonb,
  now() - interval '10 minutes',
  null,
  now() - interval '10 minutes'
)
on conflict (refund_attempt_id) do update
set
  status = excluded.status,
  attempted_at = excluded.attempted_at,
  completed_at = excluded.completed_at;

commit;

-- ---------------------------------------------------------------------------
-- Quick verification snippets
-- ---------------------------------------------------------------------------
-- select hold_id, status, hold_expires_at, amount from public.seat_holds
-- where hold_id like '4b100000-%' order by hold_id;
--
-- select transaction_id, hold_id, status, refund_status, stripe_payment_intent_id
-- from public.transactions where transaction_id like '7b100000-%' order by transaction_id;
--
-- select cancellation_request_id, transaction_id, status, attempt_count, last_attempt_at
-- from public.cancellation_requests where cancellation_request_id like '9b100000-%'
-- order by cancellation_request_id;
--
-- select refund_attempt_id, cancellation_request_id, attempt_no, status, attempted_at, completed_at
-- from public.refund_attempts where refund_attempt_id like '91b10000-%'
-- order by refund_attempt_id;