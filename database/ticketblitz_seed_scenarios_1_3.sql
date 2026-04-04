-- TicketBlitz seed data for Scenarios 1-3
-- Users requested: Brandon, Boone, Ian, Mik, Shirin

begin;

set search_path = public, extensions;

-- 1) Users
insert into public.users (user_id, full_name, email, phone, metadata)
values
  ('00000000-0000-0000-0000-000000000001', 'Brandon', 'brandon@ticketblitz.com', '+6591110001', '{"role":"fan"}'::jsonb),
  ('00000000-0000-0000-0000-000000000002', 'Boone',   'boone@ticketblitz.com',   '+6591110002', '{"role":"fan"}'::jsonb),
  ('00000000-0000-0000-0000-000000000003', 'Ian',     'ian@ticketblitz.com',     '+6591110003', '{"role":"fan"}'::jsonb),
  ('00000000-0000-0000-0000-000000000004', 'Mik',     'mik@ticketblitz.com',     '+6591110004', '{"role":"organiser"}'::jsonb),
  ('00000000-0000-0000-0000-000000000005', 'Shirin',  'shirin@ticketblitz.com',  '+6591110005', '{"role":"fan"}'::jsonb)
on conflict (user_id) do update
set
  full_name = excluded.full_name,
  email = excluded.email,
  phone = excluded.phone,
  metadata = excluded.metadata,
  deleted_at = null;

insert into public.user_roles (user_id, role)
select
  user_id,
  case
    when lower(coalesce(metadata->>'role', 'fan')) = 'organiser' then 'organiser'::public.app_role_t
    else 'fan'::public.app_role_t
  end
from public.users
where user_id in (
  '00000000-0000-0000-0000-000000000001',
  '00000000-0000-0000-0000-000000000002',
  '00000000-0000-0000-0000-000000000003',
  '00000000-0000-0000-0000-000000000004',
  '00000000-0000-0000-0000-000000000005'
)
on conflict (user_id) do update
set role = excluded.role,
    assigned_at = now();

-- 2) Event
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
)
values (
  '10000000-0000-0000-0000-000000000301',
  'EVT-301',
  'Coldplay Live 2026',
  'Flash-sale seeded event for scenarios 1 to 3',
  'National Stadium Singapore',
  '2026-06-01 20:00:00+08',
  '2026-03-15 09:00:00+08',
  '2026-06-01 19:00:00+08',
  8,
  'ACTIVE',
  '{"seed":"scenario_1_3"}'::jsonb
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
  deleted_at = null;

-- 3) Seat categories
insert into public.seat_categories (
  category_id,
  event_id,
  category_code,
  name,
  base_price,
  current_price,
  currency,
  total_seats,
  is_active,
  sort_order,
  metadata
)
values
  ('20000000-0000-0000-0000-000000000101', '10000000-0000-0000-0000-000000000301', 'CAT1', 'Category 1', 288.00, 144.00, 'SGD', 4, true, 10, '{"tier":"premium"}'::jsonb),
  ('20000000-0000-0000-0000-000000000102', '10000000-0000-0000-0000-000000000301', 'CAT2', 'Category 2', 168.00, 168.00, 'SGD', 2, true, 20, '{"tier":"standard"}'::jsonb),
  ('20000000-0000-0000-0000-000000000103', '10000000-0000-0000-0000-000000000301', 'PEN',  'Pen',        388.00, 388.00, 'SGD', 2, true, 30, '{"tier":"pit"}'::jsonb)
on conflict (category_id) do update
set
  event_id = excluded.event_id,
  category_code = excluded.category_code,
  name = excluded.name,
  base_price = excluded.base_price,
  current_price = excluded.current_price,
  currency = excluded.currency,
  total_seats = excluded.total_seats,
  is_active = excluded.is_active,
  sort_order = excluded.sort_order,
  metadata = excluded.metadata,
  deleted_at = null;

-- 4) Seats
insert into public.seats (
  seat_id,
  event_id,
  category_id,
  seat_number,
  status,
  sold_at,
  metadata
)
values
  ('30000000-0000-0000-0000-000000000010', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000101', 'D10', 'SOLD',             '2026-03-18 15:30:00+08', '{"seed_path":"S1A"}'::jsonb),
  ('30000000-0000-0000-0000-000000000011', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000101', 'D11', 'SOLD',             '2026-03-18 15:32:00+08', '{"seed_path":"baseline"}'::jsonb),
  ('30000000-0000-0000-0000-000000000012', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000101', 'D12', 'SOLD',             '2026-03-18 15:40:00+08', '{"seed_path":"S1C"}'::jsonb),
  ('30000000-0000-0000-0000-000000000013', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000101', 'D13', 'PENDING_WAITLIST', null,                       '{"seed_path":"S1D"}'::jsonb),
  ('30000000-0000-0000-0000-000000000020', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000102', 'C20', 'SOLD',             '2026-03-20 10:00:00+08', '{"seed_path":"S3D"}'::jsonb),
  ('30000000-0000-0000-0000-000000000021', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000102', 'C21', 'SOLD',             '2026-03-19 11:00:00+08', '{"seed_path":"S3A"}'::jsonb),
  ('30000000-0000-0000-0000-000000000031', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000103', 'P01', 'AVAILABLE',        null,                       '{"seed_path":"available"}'::jsonb),
  ('30000000-0000-0000-0000-000000000032', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000103', 'P02', 'SOLD',             '2026-03-22 14:00:00+08', '{"seed_path":"S3C"}'::jsonb)
on conflict (seat_id) do update
set
  event_id = excluded.event_id,
  category_id = excluded.category_id,
  seat_number = excluded.seat_number,
  status = excluded.status,
  sold_at = excluded.sold_at,
  metadata = excluded.metadata;

-- 5) Seat holds for S1/S3 paths
insert into public.seat_holds (
  hold_id,
  seat_id,
  event_id,
  category_id,
  user_id,
  from_waitlist,
  hold_expires_at,
  status,
  release_reason,
  amount,
  currency,
  idempotency_key,
  correlation_id,
  confirmed_at,
  released_at,
  expired_at,
  metadata,
  created_at
)
values
  (
    '40000000-0000-0000-0000-000000000001',
    '30000000-0000-0000-0000-000000000010',
    '10000000-0000-0000-0000-000000000301',
    '20000000-0000-0000-0000-000000000101',
    '00000000-0000-0000-0000-000000000001',
    false,
    '2026-03-18 15:10:00+08',
    'CONFIRMED',
    null,
    160.00,
    'SGD',
    'seed-hold-h1',
    '51000000-0000-0000-0000-000000000001',
    '2026-03-18 15:06:00+08',
    null,
    null,
    '{"scenario":"1A"}'::jsonb,
    '2026-03-18 15:00:00+08'
  ),
  (
    '40000000-0000-0000-0000-000000000002',
    '30000000-0000-0000-0000-000000000012',
    '10000000-0000-0000-0000-000000000301',
    '20000000-0000-0000-0000-000000000101',
    '00000000-0000-0000-0000-000000000002',
    true,
    '2026-03-18 15:20:00+08',
    'CONFIRMED',
    null,
    160.00,
    'SGD',
    'seed-hold-h2',
    '51000000-0000-0000-0000-000000000002',
    '2026-03-18 15:16:00+08',
    null,
    null,
    '{"scenario":"1C"}'::jsonb,
    '2026-03-18 15:10:00+08'
  ),
  (
    '40000000-0000-0000-0000-000000000003',
    '30000000-0000-0000-0000-000000000013',
    '10000000-0000-0000-0000-000000000301',
    '20000000-0000-0000-0000-000000000101',
    '00000000-0000-0000-0000-000000000001',
    true,
    '2026-03-18 15:30:00+08',
    'EXPIRED',
    'PAYMENT_TIMEOUT',
    160.00,
    'SGD',
    'seed-hold-h3',
    '51000000-0000-0000-0000-000000000003',
    null,
    null,
    '2026-03-18 15:31:00+08',
    '{"scenario":"1D"}'::jsonb,
    '2026-03-18 15:20:00+08'
  ),
  (
    '40000000-0000-0000-0000-000000000004',
    '30000000-0000-0000-0000-000000000021',
    '10000000-0000-0000-0000-000000000301',
    '20000000-0000-0000-0000-000000000102',
    '00000000-0000-0000-0000-000000000005',
    false,
    '2026-03-19 12:00:00+08',
    'CONFIRMED',
    null,
    168.00,
    'SGD',
    'seed-hold-h4',
    '51000000-0000-0000-0000-000000000004',
    '2026-03-19 11:10:00+08',
    null,
    null,
    '{"scenario":"3A"}'::jsonb,
    '2026-03-19 11:00:00+08'
  ),
  (
    '40000000-0000-0000-0000-000000000005',
    '30000000-0000-0000-0000-000000000032',
    '10000000-0000-0000-0000-000000000301',
    '20000000-0000-0000-0000-000000000103',
    '00000000-0000-0000-0000-000000000004',
    false,
    '2026-03-22 14:20:00+08',
    'CONFIRMED',
    null,
    388.00,
    'SGD',
    'seed-hold-h5',
    '51000000-0000-0000-0000-000000000005',
    '2026-03-22 14:05:00+08',
    null,
    null,
    '{"scenario":"3C"}'::jsonb,
    '2026-03-22 14:00:00+08'
  ),
  (
    '40000000-0000-0000-0000-000000000006',
    '30000000-0000-0000-0000-000000000020',
    '10000000-0000-0000-0000-000000000301',
    '20000000-0000-0000-0000-000000000102',
    '00000000-0000-0000-0000-000000000003',
    false,
    '2026-03-20 10:20:00+08',
    'CONFIRMED',
    null,
    168.00,
    'SGD',
    'seed-hold-h6',
    '51000000-0000-0000-0000-000000000006',
    '2026-03-20 10:05:00+08',
    null,
    null,
    '{"scenario":"3D"}'::jsonb,
    '2026-03-20 10:00:00+08'
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
  release_reason = excluded.release_reason,
  amount = excluded.amount,
  currency = excluded.currency,
  idempotency_key = excluded.idempotency_key,
  correlation_id = excluded.correlation_id,
  confirmed_at = excluded.confirmed_at,
  released_at = excluded.released_at,
  expired_at = excluded.expired_at,
  metadata = excluded.metadata,
  created_at = excluded.created_at;

-- 6) Waitlist entries
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
  metadata,
  created_at
)
values
  (
    '60000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000301',
    '20000000-0000-0000-0000-000000000101',
    '00000000-0000-0000-0000-000000000003',
    null,
    'WAITING',
    '2026-03-18 15:07:00+08',
    null,
    null,
    null,
    10,
    'PUBLIC',
    '{"scenario":"1B"}'::jsonb,
    '2026-03-18 15:07:00+08'
  ),
  (
    '60000000-0000-0000-0000-000000000002',
    '10000000-0000-0000-0000-000000000301',
    '20000000-0000-0000-0000-000000000101',
    '00000000-0000-0000-0000-000000000002',
    '40000000-0000-0000-0000-000000000002',
    'CONFIRMED',
    '2026-03-18 15:08:00+08',
    '2026-03-18 15:12:00+08',
    '2026-03-18 15:16:00+08',
    null,
    20,
    'PUBLIC',
    '{"scenario":"1C"}'::jsonb,
    '2026-03-18 15:08:00+08'
  ),
  (
    '60000000-0000-0000-0000-000000000003',
    '10000000-0000-0000-0000-000000000301',
    '20000000-0000-0000-0000-000000000101',
    '00000000-0000-0000-0000-000000000001',
    '40000000-0000-0000-0000-000000000003',
    'EXPIRED',
    '2026-03-18 15:09:00+08',
    '2026-03-18 15:20:00+08',
    null,
    '2026-03-18 15:31:00+08',
    30,
    'PUBLIC',
    '{"scenario":"1D"}'::jsonb,
    '2026-03-18 15:09:00+08'
  ),
  (
    '60000000-0000-0000-0000-000000000004',
    '10000000-0000-0000-0000-000000000301',
    '20000000-0000-0000-0000-000000000103',
    '00000000-0000-0000-0000-000000000005',
    null,
    'WAITING',
    '2026-03-23 09:00:00+08',
    null,
    null,
    null,
    40,
    'PUBLIC',
    '{"scenario":"3_waitlist_pen"}'::jsonb,
    '2026-03-23 09:00:00+08'
  )
on conflict (waitlist_id) do update
set
  event_id = excluded.event_id,
  category_id = excluded.category_id,
  user_id = excluded.user_id,
  hold_id = excluded.hold_id,
  status = excluded.status,
  joined_at = excluded.joined_at,
  offered_at = excluded.offered_at,
  confirmed_at = excluded.confirmed_at,
  expired_at = excluded.expired_at,
  priority_score = excluded.priority_score,
  source = excluded.source,
  metadata = excluded.metadata,
  created_at = excluded.created_at;

-- 7) Transactions
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
  created_at
)
values
  (
    '70000000-0000-0000-0000-000000000001',
    '40000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000301',
    '00000000-0000-0000-0000-000000000001',
    160.00,
    'SGD',
    'pi_seed_001',
    'ch_seed_001',
    'SUCCEEDED',
    null,
    0,
    null,
    null,
    null,
    'seed-txn-t1',
    '72000000-0000-0000-0000-000000000001',
    '{"provider":"stripe","event":"payment_intent.succeeded"}'::jsonb,
    '{"scenario":"1A"}'::jsonb,
    '2026-03-18 15:05:30+08'
  ),
  (
    '70000000-0000-0000-0000-000000000002',
    '40000000-0000-0000-0000-000000000002',
    '10000000-0000-0000-0000-000000000301',
    '00000000-0000-0000-0000-000000000002',
    160.00,
    'SGD',
    'pi_seed_002',
    'ch_seed_002',
    'SUCCEEDED',
    null,
    0,
    null,
    null,
    null,
    'seed-txn-t2',
    '72000000-0000-0000-0000-000000000002',
    '{"provider":"stripe","event":"payment_intent.succeeded"}'::jsonb,
    '{"scenario":"1C"}'::jsonb,
    '2026-03-18 15:15:30+08'
  ),
  (
    '70000000-0000-0000-0000-000000000003',
    '40000000-0000-0000-0000-000000000004',
    '10000000-0000-0000-0000-000000000301',
    '00000000-0000-0000-0000-000000000005',
    168.00,
    'SGD',
    'pi_seed_003',
    'ch_seed_003',
    'REFUND_SUCCEEDED',
    null,
    151.20,
    'SUCCEEDED',
    '2026-03-24 09:00:00+08',
    '2026-03-24 09:05:00+08',
    'seed-txn-t3',
    '72000000-0000-0000-0000-000000000003',
    '{"provider":"stripe","event":"refund.succeeded"}'::jsonb,
    '{"scenario":"3A"}'::jsonb,
    '2026-03-19 11:05:00+08'
  ),
  (
    '70000000-0000-0000-0000-000000000004',
    '40000000-0000-0000-0000-000000000005',
    '10000000-0000-0000-0000-000000000301',
    '00000000-0000-0000-0000-000000000004',
    388.00,
    'SGD',
    'pi_seed_004',
    'ch_seed_004',
    'REFUND_FAILED',
    'Stripe timeout after retries',
    349.20,
    'FAILED',
    '2026-03-25 10:00:00+08',
    null,
    'seed-txn-t4',
    '72000000-0000-0000-0000-000000000004',
    '{"provider":"stripe","event":"refund.failed"}'::jsonb,
    '{"scenario":"3C"}'::jsonb,
    '2026-03-22 14:04:00+08'
  ),
  (
    '70000000-0000-0000-0000-000000000005',
    '40000000-0000-0000-0000-000000000006',
    '10000000-0000-0000-0000-000000000301',
    '00000000-0000-0000-0000-000000000003',
    168.00,
    'SGD',
    'pi_seed_005',
    'ch_seed_005',
    'REFUND_SUCCEEDED',
    null,
    151.20,
    'SUCCEEDED',
    '2026-03-26 16:00:00+08',
    '2026-03-26 16:02:00+08',
    'seed-txn-t5',
    '72000000-0000-0000-0000-000000000005',
    '{"provider":"stripe","event":"refund.succeeded"}'::jsonb,
    '{"scenario":"3D"}'::jsonb,
    '2026-03-20 10:03:00+08'
  )
on conflict (transaction_id) do update
set
  hold_id = excluded.hold_id,
  event_id = excluded.event_id,
  user_id = excluded.user_id,
  amount = excluded.amount,
  currency = excluded.currency,
  stripe_payment_intent_id = excluded.stripe_payment_intent_id,
  stripe_charge_id = excluded.stripe_charge_id,
  status = excluded.status,
  failure_reason = excluded.failure_reason,
  refund_amount = excluded.refund_amount,
  refund_status = excluded.refund_status,
  refund_requested_at = excluded.refund_requested_at,
  refunded_at = excluded.refunded_at,
  idempotency_key = excluded.idempotency_key,
  correlation_id = excluded.correlation_id,
  provider_response = excluded.provider_response,
  metadata = excluded.metadata,
  created_at = excluded.created_at;

-- 8) Webhook events
insert into public.payment_webhook_events (
  webhook_event_id,
  payment_intent_id,
  hold_id,
  event_type,
  payload,
  received_at,
  processed_at,
  processing_status,
  error_message
)
values
  (
    'evt_seed_001',
    'pi_seed_001',
    '40000000-0000-0000-0000-000000000001',
    'payment_intent.succeeded',
    '{"id":"evt_seed_001","type":"payment_intent.succeeded"}'::jsonb,
    '2026-03-18 15:05:35+08',
    '2026-03-18 15:05:36+08',
    'PROCESSED',
    null
  ),
  (
    'evt_seed_002',
    'pi_seed_002',
    '40000000-0000-0000-0000-000000000002',
    'payment_intent.succeeded',
    '{"id":"evt_seed_002","type":"payment_intent.succeeded"}'::jsonb,
    '2026-03-18 15:15:35+08',
    '2026-03-18 15:15:36+08',
    'PROCESSED',
    null
  ),
  (
    'evt_seed_003',
    'pi_seed_004',
    '40000000-0000-0000-0000-000000000005',
    'payment_intent.payment_failed',
    '{"id":"evt_seed_003","type":"payment_intent.payment_failed"}'::jsonb,
    '2026-03-25 10:00:05+08',
    '2026-03-25 10:00:06+08',
    'FAILED',
    'Provider timeout'
  )
on conflict (webhook_event_id) do update
set
  payment_intent_id = excluded.payment_intent_id,
  hold_id = excluded.hold_id,
  event_type = excluded.event_type,
  payload = excluded.payload,
  received_at = excluded.received_at,
  processed_at = excluded.processed_at,
  processing_status = excluded.processing_status,
  error_message = excluded.error_message;

-- 9) Flash sale lifecycle seed
insert into public.flash_sales (
  flash_sale_id,
  event_id,
  discount_percentage,
  escalation_percentage,
  starts_at,
  ends_at,
  status,
  launched_by_user_id,
  config,
  ended_at,
  created_at
)
values (
  '80000000-0000-0000-0000-000000000001',
  '10000000-0000-0000-0000-000000000301',
  50.00,
  20.00,
  '2026-03-24 14:54:00+08',
  '2026-03-24 16:54:00+08',
  'ENDED',
  '00000000-0000-0000-0000-000000000004',
  '{"durationMinutes":120,"reason":"scenario2_seed"}'::jsonb,
  '2026-03-24 15:30:00+08',
  '2026-03-24 14:54:00+08'
)
on conflict (flash_sale_id) do update
set
  event_id = excluded.event_id,
  discount_percentage = excluded.discount_percentage,
  escalation_percentage = excluded.escalation_percentage,
  starts_at = excluded.starts_at,
  ends_at = excluded.ends_at,
  status = excluded.status,
  launched_by_user_id = excluded.launched_by_user_id,
  config = excluded.config,
  ended_at = excluded.ended_at,
  created_at = excluded.created_at;

insert into public.price_changes (
  change_id,
  flash_sale_id,
  event_id,
  category_id,
  reason,
  old_price,
  new_price,
  changed_at,
  changed_by,
  context,
  created_at
)
values
  ('81000000-0000-0000-0000-000000000001', '80000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000101', 'FLASH_SALE', 288.00, 144.00, '2026-03-24 14:54:05+08', 'FlashSaleOrchestrator', '{"category":"CAT1"}'::jsonb, '2026-03-24 14:54:05+08'),
  ('81000000-0000-0000-0000-000000000002', '80000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000102', 'FLASH_SALE', 168.00,  84.00, '2026-03-24 14:54:05+08', 'FlashSaleOrchestrator', '{"category":"CAT2"}'::jsonb, '2026-03-24 14:54:05+08'),
  ('81000000-0000-0000-0000-000000000003', '80000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000103', 'FLASH_SALE', 388.00, 194.00, '2026-03-24 14:54:05+08', 'FlashSaleOrchestrator', '{"category":"PEN"}'::jsonb,  '2026-03-24 14:54:05+08'),
  ('81000000-0000-0000-0000-000000000004', '80000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000102', 'ESCALATION',  84.00, 100.80, '2026-03-24 15:10:00+08', 'PricingOrchestrator',   '{"soldOutCategory":"CAT1"}'::jsonb, '2026-03-24 15:10:00+08'),
  ('81000000-0000-0000-0000-000000000005', '80000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000103', 'ESCALATION', 194.00, 232.80, '2026-03-24 15:10:00+08', 'PricingOrchestrator',   '{"soldOutCategory":"CAT1"}'::jsonb, '2026-03-24 15:10:00+08'),
  ('81000000-0000-0000-0000-000000000006', '80000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000102', 'REVERT',     100.80, 168.00, '2026-03-24 15:30:00+08', 'FlashSaleOrchestrator', '{"endFlashSale":true}'::jsonb,      '2026-03-24 15:30:00+08'),
  ('81000000-0000-0000-0000-000000000007', '80000000-0000-0000-0000-000000000001', '10000000-0000-0000-0000-000000000301', '20000000-0000-0000-0000-000000000103', 'REVERT',     232.80, 388.00, '2026-03-24 15:30:00+08', 'FlashSaleOrchestrator', '{"endFlashSale":true}'::jsonb,      '2026-03-24 15:30:00+08')
on conflict (change_id) do update
set
  flash_sale_id = excluded.flash_sale_id,
  event_id = excluded.event_id,
  category_id = excluded.category_id,
  reason = excluded.reason,
  old_price = excluded.old_price,
  new_price = excluded.new_price,
  changed_at = excluded.changed_at,
  changed_by = excluded.changed_by,
  context = excluded.context,
  created_at = excluded.created_at;

insert into public.inventory_event_state (
  event_id,
  flash_sale_active,
  active_flash_sale_id,
  last_sold_out_category,
  last_sold_out_at,
  metadata,
  updated_at
)
values (
  '10000000-0000-0000-0000-000000000301',
  false,
  null,
  'CAT1',
  '2026-03-24 15:10:00+08',
  '{"flashSale":"ended"}'::jsonb,
  '2026-03-24 15:30:00+08'
)
on conflict (event_id) do update
set
  flash_sale_active = excluded.flash_sale_active,
  active_flash_sale_id = excluded.active_flash_sale_id,
  last_sold_out_category = excluded.last_sold_out_category,
  last_sold_out_at = excluded.last_sold_out_at,
  metadata = excluded.metadata,
  updated_at = excluded.updated_at;

-- 10) Scenario 3 cancellation requests
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
  created_at
)
values
  (
    '90000000-0000-0000-0000-000000000001',
    '40000000-0000-0000-0000-000000000004',
    '70000000-0000-0000-0000-000000000003',
    '10000000-0000-0000-0000-000000000301',
    '00000000-0000-0000-0000-000000000005',
    '2026-03-24 09:00:00+08',
    '2026-05-30 20:00:00+08',
    true,
    'COMPLETED',
    'Successful refund and ticket reallocation',
    10.00,
    151.20,
    1,
    '2026-03-24 09:04:00+08',
    '2026-03-24 09:05:00+08',
    '{"scenario":"3A"}'::jsonb,
    '2026-03-24 09:00:00+08'
  ),
  (
    '90000000-0000-0000-0000-000000000002',
    '40000000-0000-0000-0000-000000000001',
    '70000000-0000-0000-0000-000000000001',
    '10000000-0000-0000-0000-000000000301',
    '00000000-0000-0000-0000-000000000001',
    '2026-05-31 21:00:00+08',
    '2026-05-30 20:00:00+08',
    false,
    'REJECTED',
    'Within 48-hour cancellation lockout',
    10.00,
    0,
    0,
    null,
    '2026-05-31 21:00:30+08',
    '{"scenario":"3B"}'::jsonb,
    '2026-05-31 21:00:00+08'
  ),
  (
    '90000000-0000-0000-0000-000000000003',
    '40000000-0000-0000-0000-000000000005',
    '70000000-0000-0000-0000-000000000004',
    '10000000-0000-0000-0000-000000000301',
    '00000000-0000-0000-0000-000000000004',
    '2026-03-25 10:00:00+08',
    '2026-05-30 20:00:00+08',
    true,
    'CANCELLATION_IN_PROGRESS',
    'Refund failed after retries; saga compensation applied',
    10.00,
    349.20,
    3,
    '2026-03-25 10:10:00+08',
    null,
    '{"scenario":"3C"}'::jsonb,
    '2026-03-25 10:00:00+08'
  ),
  (
    '90000000-0000-0000-0000-000000000004',
    '40000000-0000-0000-0000-000000000006',
    '70000000-0000-0000-0000-000000000005',
    '10000000-0000-0000-0000-000000000301',
    '00000000-0000-0000-0000-000000000003',
    '2026-03-26 16:00:00+08',
    '2026-05-30 20:00:00+08',
    true,
    'COMPLETED',
    'No one on waitlist; ticket returned to general inventory',
    10.00,
    151.20,
    1,
    '2026-03-26 16:01:00+08',
    '2026-03-26 16:02:00+08',
    '{"scenario":"3D"}'::jsonb,
    '2026-03-26 16:00:00+08'
  )
on conflict (cancellation_request_id) do update
set
  hold_id = excluded.hold_id,
  transaction_id = excluded.transaction_id,
  event_id = excluded.event_id,
  user_id = excluded.user_id,
  requested_at = excluded.requested_at,
  policy_cutoff_at = excluded.policy_cutoff_at,
  is_policy_eligible = excluded.is_policy_eligible,
  status = excluded.status,
  reason = excluded.reason,
  fee_percentage = excluded.fee_percentage,
  refund_amount = excluded.refund_amount,
  attempt_count = excluded.attempt_count,
  last_attempt_at = excluded.last_attempt_at,
  resolved_at = excluded.resolved_at,
  metadata = excluded.metadata,
  created_at = excluded.created_at;

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
)
values
  (
    '91000000-0000-0000-0000-000000000001',
    '90000000-0000-0000-0000-000000000001',
    '70000000-0000-0000-0000-000000000003',
    1,
    'SUCCEEDED',
    're_seed_001',
    null,
    null,
    '{"provider":"stripe"}'::jsonb,
    '2026-03-24 09:04:00+08',
    '2026-03-24 09:05:00+08',
    '2026-03-24 09:04:00+08'
  ),
  (
    '91000000-0000-0000-0000-000000000002',
    '90000000-0000-0000-0000-000000000003',
    '70000000-0000-0000-0000-000000000004',
    1,
    'FAILED',
    're_seed_002',
    'TIMEOUT',
    'Stripe timeout on attempt 1',
    '{"provider":"stripe","attempt":1}'::jsonb,
    '2026-03-25 10:02:00+08',
    '2026-03-25 10:02:15+08',
    '2026-03-25 10:02:00+08'
  ),
  (
    '91000000-0000-0000-0000-000000000003',
    '90000000-0000-0000-0000-000000000003',
    '70000000-0000-0000-0000-000000000004',
    2,
    'FAILED',
    're_seed_003',
    'TIMEOUT',
    'Stripe timeout on attempt 2',
    '{"provider":"stripe","attempt":2}'::jsonb,
    '2026-03-25 10:05:00+08',
    '2026-03-25 10:05:15+08',
    '2026-03-25 10:05:00+08'
  ),
  (
    '91000000-0000-0000-0000-000000000004',
    '90000000-0000-0000-0000-000000000003',
    '70000000-0000-0000-0000-000000000004',
    3,
    'FAILED',
    're_seed_004',
    'TIMEOUT',
    'Stripe timeout on attempt 3',
    '{"provider":"stripe","attempt":3}'::jsonb,
    '2026-03-25 10:10:00+08',
    '2026-03-25 10:10:15+08',
    '2026-03-25 10:10:00+08'
  ),
  (
    '91000000-0000-0000-0000-000000000005',
    '90000000-0000-0000-0000-000000000004',
    '70000000-0000-0000-0000-000000000005',
    1,
    'SUCCEEDED',
    're_seed_005',
    null,
    null,
    '{"provider":"stripe"}'::jsonb,
    '2026-03-26 16:01:00+08',
    '2026-03-26 16:02:00+08',
    '2026-03-26 16:01:00+08'
  )
on conflict (refund_attempt_id) do update
set
  cancellation_request_id = excluded.cancellation_request_id,
  transaction_id = excluded.transaction_id,
  attempt_no = excluded.attempt_no,
  status = excluded.status,
  provider_reference = excluded.provider_reference,
  error_code = excluded.error_code,
  error_message = excluded.error_message,
  provider_payload = excluded.provider_payload,
  attempted_at = excluded.attempted_at,
  completed_at = excluded.completed_at,
  created_at = excluded.created_at;

-- 11) Integration/outbox events for AMQP choreography
insert into public.integration_events (
  event_id,
  occurred_at,
  producer_service,
  aggregate_type,
  aggregate_id,
  event_name,
  exchange_name,
  routing_key,
  payload,
  headers,
  waitlist_emails,
  published,
  published_at,
  publish_error
)
values
  (
    'a0000000-0000-0000-0000-000000000001',
    '2026-04-01 09:00:00+08',
    'payment-service',
    'booking',
    '40000000-0000-0000-0000-000000000001',
    'booking.confirmed',
    'ticketblitz',
    'booking.confirmed',
    '{"holdID":"40000000-0000-0000-0000-000000000001","userID":"00000000-0000-0000-0000-000000000001"}'::jsonb,
    '{"correlationID":"51000000-0000-0000-0000-000000000001"}'::jsonb,
    '{}'::text[],
    true,
    '2026-04-01 09:00:01+08',
    null
  ),
  (
    'a0000000-0000-0000-0000-000000000002',
    '2026-04-01 09:00:05+08',
    'inventory-service',
    'seat',
    '30000000-0000-0000-0000-000000000013',
    'seat.released',
    'ticketblitz',
    'seat.released',
    '{"eventID":"10000000-0000-0000-0000-000000000301","seatCategory":"CAT1","reason":"PAYMENT_TIMEOUT"}'::jsonb,
    '{}'::jsonb,
    '{}'::text[],
    true,
    '2026-04-01 09:00:06+08',
    null
  ),
  (
    'a0000000-0000-0000-0000-000000000003',
    '2026-04-01 09:01:00+08',
    'flash-sale-orchestrator',
    'pricing',
    '80000000-0000-0000-0000-000000000001',
    'price.broadcast',
    'ticketblitz.price',
    'price.broadcast',
    '{"type":"FLASH_SALE_LAUNCHED","eventID":"10000000-0000-0000-0000-000000000301"}'::jsonb,
    '{}'::jsonb,
    array['ian@ticketblitz.com','shirin@ticketblitz.com']::text[],
    true,
    '2026-04-01 09:01:01+08',
    null
  ),
  (
    'a0000000-0000-0000-0000-000000000004',
    '2026-04-01 09:02:00+08',
    'inventory-service',
    'category',
    '20000000-0000-0000-0000-000000000101',
    'category.sold_out',
    'ticketblitz',
    'category.sold_out',
    '{"eventID":"10000000-0000-0000-0000-000000000301","category":"CAT1"}'::jsonb,
    '{}'::jsonb,
    '{}'::text[],
    true,
    '2026-04-01 09:02:01+08',
    null
  ),
  (
    'a0000000-0000-0000-0000-000000000005',
    '2026-04-01 09:03:00+08',
    'cancellation-orchestrator',
    'refund',
    '90000000-0000-0000-0000-000000000003',
    'refund.error',
    'ticketblitz',
    'notification.send',
    '{"type":"REFUND_ERROR","userID":"00000000-0000-0000-0000-000000000004"}'::jsonb,
    '{}'::jsonb,
    array['mik@ticketblitz.com']::text[],
    false,
    null,
    'retry pending'
  )
on conflict (occurred_at, event_id) do update
set
  producer_service = excluded.producer_service,
  aggregate_type = excluded.aggregate_type,
  aggregate_id = excluded.aggregate_id,
  event_name = excluded.event_name,
  exchange_name = excluded.exchange_name,
  routing_key = excluded.routing_key,
  payload = excluded.payload,
  headers = excluded.headers,
  waitlist_emails = excluded.waitlist_emails,
  published = excluded.published,
  published_at = excluded.published_at,
  publish_error = excluded.publish_error;

refresh materialized view public.mv_sales_velocity_hourly;

commit;
