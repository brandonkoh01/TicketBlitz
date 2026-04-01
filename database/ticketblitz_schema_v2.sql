-- TicketBlitz foundational schema for all microservices except E-Ticket Service.
-- Target: Supabase Postgres (public schema)
-- Date: 2026-04-01

begin;

set search_path = public, extensions;

create extension if not exists pgcrypto with schema extensions;
create extension if not exists btree_gist with schema extensions;

do $$
begin
  if not exists (select 1 from pg_type where typname = 'currency_code_t') then
    create domain currency_code_t as char(3)
      check (value ~ '^[A-Z]{3}$');
  end if;

  if not exists (select 1 from pg_type where typname = 'money_amount_t') then
    create domain money_amount_t as numeric(12,2)
      check (value >= 0);
  end if;

  if not exists (select 1 from pg_type where typname = 'percentage_t') then
    create domain percentage_t as numeric(5,2)
      check (value >= 0 and value <= 100);
  end if;
end
$$;

do $$
begin
  if not exists (select 1 from pg_type where typname = 'event_status_t') then
    create type event_status_t as enum (
      'SCHEDULED',
      'ACTIVE',
      'FLASH_SALE_ACTIVE',
      'CANCELLED',
      'COMPLETED'
    );
  end if;

  if not exists (select 1 from pg_type where typname = 'seat_status_t') then
    create type seat_status_t as enum (
      'AVAILABLE',
      'PENDING_WAITLIST',
      'HELD',
      'SOLD'
    );
  end if;

  if not exists (select 1 from pg_type where typname = 'hold_status_t') then
    create type hold_status_t as enum (
      'HELD',
      'CONFIRMED',
      'EXPIRED',
      'RELEASED'
    );
  end if;

  if not exists (select 1 from pg_type where typname = 'hold_release_reason_t') then
    create type hold_release_reason_t as enum (
      'PAYMENT_TIMEOUT',
      'CANCELLATION',
      'MANUAL_RELEASE',
      'SYSTEM_CLEANUP'
    );
  end if;

  if not exists (select 1 from pg_type where typname = 'waitlist_status_t') then
    create type waitlist_status_t as enum (
      'WAITING',
      'HOLD_OFFERED',
      'CONFIRMED',
      'EXPIRED',
      'CANCELLED'
    );
  end if;

  if not exists (select 1 from pg_type where typname = 'transaction_status_t') then
    create type transaction_status_t as enum (
      'PENDING',
      'SUCCEEDED',
      'FAILED',
      'REFUND_PENDING',
      'REFUND_SUCCEEDED',
      'REFUND_FAILED'
    );
  end if;

  if not exists (select 1 from pg_type where typname = 'refund_attempt_status_t') then
    create type refund_attempt_status_t as enum (
      'PENDING',
      'SUCCEEDED',
      'FAILED'
    );
  end if;

  if not exists (select 1 from pg_type where typname = 'flash_sale_status_t') then
    create type flash_sale_status_t as enum (
      'ACTIVE',
      'ENDED',
      'CANCELLED'
    );
  end if;

  if not exists (select 1 from pg_type where typname = 'price_change_reason_t') then
    create type price_change_reason_t as enum (
      'FLASH_SALE',
      'ESCALATION',
      'REVERT',
      'MANUAL_ADJUSTMENT'
    );
  end if;

  if not exists (select 1 from pg_type where typname = 'cancellation_status_t') then
    create type cancellation_status_t as enum (
      'REQUESTED',
      'ELIGIBLE',
      'REJECTED',
      'PROCESSING_REFUND',
      'REFUND_SUCCEEDED',
      'REFUND_FAILED',
      'CANCELLATION_IN_PROGRESS',
      'COMPLETED'
    );
  end if;
end
$$;

create or replace function set_row_updated_at()
returns trigger
language plpgsql
set search_path = public, extensions
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create or replace function bump_seat_version()
returns trigger
language plpgsql
set search_path = public, extensions
as $$
begin
  if (new.status is distinct from old.status)
     or (new.category_id is distinct from old.category_id)
     or (new.seat_number is distinct from old.seat_number)
     or (new.metadata is distinct from old.metadata) then
    new.version = old.version + 1;
  end if;
  return new;
end;
$$;

create or replace function notify_ticketblitz_event()
returns trigger
language plpgsql
set search_path = public, extensions
as $$
begin
  perform pg_notify(
    'ticketblitz_events',
    json_build_object(
      'event_id', new.event_id,
      'event_name', new.event_name,
      'routing_key', new.routing_key,
      'occurred_at', new.occurred_at
    )::text
  );
  return new;
end;
$$;

create table if not exists users (
  user_id uuid primary key default gen_random_uuid(),
  full_name text not null
    check (length(btrim(full_name)) between 1 and 100),
  email text not null
    check (position('@' in email) > 1),
  phone text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  search_vector tsvector generated always as (
    setweight(to_tsvector('simple', coalesce(full_name, '')), 'A')
    || setweight(to_tsvector('simple', coalesce(email, '')), 'B')
  ) stored
);

create table if not exists events (
  event_id uuid primary key default gen_random_uuid(),
  event_code text not null,
  name text not null
    check (length(btrim(name)) between 1 and 200),
  description text,
  venue text not null
    check (length(btrim(venue)) between 1 and 200),
  event_date timestamptz not null,
  booking_opens_at timestamptz,
  booking_closes_at timestamptz,
  total_capacity integer not null
    check (total_capacity > 0),
  status event_status_t not null default 'SCHEDULED',
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  search_vector tsvector generated always as (
    setweight(to_tsvector('english', coalesce(name, '')), 'A')
    || setweight(to_tsvector('english', coalesce(description, '')), 'B')
    || setweight(to_tsvector('english', coalesce(venue, '')), 'C')
  ) stored,
  constraint events_event_code_uk unique (event_code),
  constraint events_booking_window_chk check (
    booking_opens_at is null
    or booking_closes_at is null
    or booking_opens_at < booking_closes_at
  )
);

create table if not exists seat_categories (
  category_id uuid primary key default gen_random_uuid(),
  event_id uuid not null references events(event_id) on delete cascade,
  category_code text not null
    check (length(btrim(category_code)) between 1 and 30),
  name text not null
    check (length(btrim(name)) between 1 and 100),
  base_price money_amount_t not null,
  current_price money_amount_t not null,
  currency currency_code_t not null default 'SGD',
  total_seats integer not null
    check (total_seats > 0),
  is_active boolean not null default true,
  sort_order smallint not null default 100,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  deleted_at timestamptz,
  constraint seat_categories_event_code_uk unique (event_id, category_code)
);

create table if not exists seats (
  seat_id uuid primary key default gen_random_uuid(),
  event_id uuid not null references events(event_id) on delete restrict,
  category_id uuid not null references seat_categories(category_id) on delete restrict,
  seat_number text not null
    check (length(btrim(seat_number)) between 1 and 20),
  status seat_status_t not null default 'AVAILABLE',
  version integer not null default 1
    check (version > 0),
  sold_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint seats_event_seat_uk unique (event_id, seat_number),
  constraint seats_sold_at_chk check (sold_at is null or status = 'SOLD')
);

create table if not exists seat_holds (
  hold_id uuid primary key default gen_random_uuid(),
  seat_id uuid not null references seats(seat_id) on delete restrict,
  event_id uuid not null references events(event_id) on delete restrict,
  category_id uuid not null references seat_categories(category_id) on delete restrict,
  user_id uuid not null references users(user_id) on delete restrict,
  from_waitlist boolean not null default false,
  hold_expires_at timestamptz not null,
  status hold_status_t not null default 'HELD',
  release_reason hold_release_reason_t,
  amount money_amount_t not null,
  currency currency_code_t not null default 'SGD',
  idempotency_key text,
  correlation_id uuid not null default gen_random_uuid(),
  confirmed_at timestamptz,
  released_at timestamptz,
  expired_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint seat_holds_hold_expiry_chk check (hold_expires_at > created_at),
  constraint seat_holds_idempotency_uk unique (idempotency_key),
  constraint seat_holds_status_timestamps_chk check (
    (status <> 'CONFIRMED' or confirmed_at is not null)
    and (status <> 'RELEASED' or released_at is not null)
    and (status <> 'EXPIRED' or expired_at is not null)
  )
);

create table if not exists waitlist_entries (
  waitlist_id uuid primary key default gen_random_uuid(),
  event_id uuid not null references events(event_id) on delete restrict,
  category_id uuid not null references seat_categories(category_id) on delete restrict,
  user_id uuid not null references users(user_id) on delete restrict,
  hold_id uuid references seat_holds(hold_id) on delete set null,
  status waitlist_status_t not null default 'WAITING',
  joined_at timestamptz not null default now(),
  offered_at timestamptz,
  confirmed_at timestamptz,
  expired_at timestamptz,
  priority_score numeric(12,4) not null default 0,
  source text not null default 'PUBLIC'
    check (length(btrim(source)) > 0),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint waitlist_entries_status_timestamps_chk check (
    (status <> 'HOLD_OFFERED' or offered_at is not null)
    and (status <> 'CONFIRMED' or confirmed_at is not null)
    and (status <> 'EXPIRED' or expired_at is not null)
  )
);

create table if not exists transactions (
  transaction_id uuid primary key default gen_random_uuid(),
  hold_id uuid not null references seat_holds(hold_id) on delete restrict,
  event_id uuid not null references events(event_id) on delete restrict,
  user_id uuid not null references users(user_id) on delete restrict,
  amount money_amount_t not null,
  currency currency_code_t not null default 'SGD',
  stripe_payment_intent_id text,
  stripe_charge_id text,
  status transaction_status_t not null default 'PENDING',
  failure_reason text,
  refund_amount money_amount_t not null default 0,
  refund_status refund_attempt_status_t,
  refund_requested_at timestamptz,
  refunded_at timestamptz,
  idempotency_key text,
  correlation_id uuid not null default gen_random_uuid(),
  provider_response jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint transactions_idempotency_uk unique (idempotency_key),
  constraint transactions_stripe_pi_uk unique (stripe_payment_intent_id),
  constraint transactions_refund_amount_chk check (refund_amount <= amount)
);

create table if not exists payment_webhook_events (
  webhook_event_id text primary key,
  payment_intent_id text,
  hold_id uuid references seat_holds(hold_id) on delete set null,
  event_type text not null,
  payload jsonb not null,
  received_at timestamptz not null default now(),
  processed_at timestamptz,
  processing_status text not null default 'RECEIVED'
    check (processing_status in ('RECEIVED', 'PROCESSED', 'IGNORED', 'FAILED')),
  error_message text
);

create table if not exists flash_sales (
  flash_sale_id uuid primary key default gen_random_uuid(),
  event_id uuid not null references events(event_id) on delete restrict,
  discount_percentage percentage_t not null,
  escalation_percentage percentage_t not null default 0,
  starts_at timestamptz not null default now(),
  ends_at timestamptz not null,
  status flash_sale_status_t not null default 'ACTIVE',
  launched_by_user_id uuid references users(user_id) on delete set null,
  config jsonb not null default '{}'::jsonb,
  ended_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  active_window tstzrange generated always as (tstzrange(starts_at, ends_at, '[)')) stored,
  constraint flash_sales_time_window_chk check (starts_at < ends_at),
  constraint flash_sales_ended_at_chk check (status <> 'ENDED' or ended_at is not null)
);

create table if not exists price_changes (
  change_id uuid primary key default gen_random_uuid(),
  flash_sale_id uuid references flash_sales(flash_sale_id) on delete set null,
  event_id uuid not null references events(event_id) on delete restrict,
  category_id uuid not null references seat_categories(category_id) on delete restrict,
  reason price_change_reason_t not null,
  old_price money_amount_t not null,
  new_price money_amount_t not null,
  changed_at timestamptz not null default now(),
  changed_by text not null default 'SYSTEM'
    check (length(btrim(changed_by)) > 0),
  context jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

create table if not exists inventory_event_state (
  event_id uuid primary key references events(event_id) on delete cascade,
  flash_sale_active boolean not null default false,
  active_flash_sale_id uuid references flash_sales(flash_sale_id) on delete set null,
  last_sold_out_category text,
  last_sold_out_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now(),
  constraint inventory_event_state_flash_sale_chk check (
    (flash_sale_active and active_flash_sale_id is not null)
    or ((not flash_sale_active) and active_flash_sale_id is null)
  )
);

create table if not exists cancellation_requests (
  cancellation_request_id uuid primary key default gen_random_uuid(),
  hold_id uuid not null references seat_holds(hold_id) on delete restrict,
  transaction_id uuid references transactions(transaction_id) on delete set null,
  event_id uuid not null references events(event_id) on delete restrict,
  user_id uuid not null references users(user_id) on delete restrict,
  requested_at timestamptz not null default now(),
  policy_cutoff_at timestamptz not null,
  is_policy_eligible boolean not null,
  status cancellation_status_t not null default 'REQUESTED',
  reason text,
  fee_percentage percentage_t not null default 10,
  refund_amount money_amount_t not null default 0,
  attempt_count integer not null default 0
    check (attempt_count >= 0),
  last_attempt_at timestamptz,
  resolved_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint cancellation_requests_resolved_chk check (
    status not in ('COMPLETED', 'REJECTED') or resolved_at is not null
  )
);

create table if not exists refund_attempts (
  refund_attempt_id uuid primary key default gen_random_uuid(),
  cancellation_request_id uuid not null references cancellation_requests(cancellation_request_id) on delete cascade,
  transaction_id uuid references transactions(transaction_id) on delete set null,
  attempt_no integer not null
    check (attempt_no > 0),
  status refund_attempt_status_t not null default 'PENDING',
  provider_reference text,
  error_code text,
  error_message text,
  provider_payload jsonb not null default '{}'::jsonb,
  attempted_at timestamptz not null default now(),
  completed_at timestamptz,
  created_at timestamptz not null default now(),
  constraint refund_attempts_attempt_uk unique (cancellation_request_id, attempt_no)
);

create table if not exists integration_events (
  event_id uuid not null default gen_random_uuid(),
  occurred_at timestamptz not null default now(),
  producer_service text not null
    check (length(btrim(producer_service)) > 0),
  aggregate_type text not null
    check (length(btrim(aggregate_type)) > 0),
  aggregate_id uuid,
  event_name text not null
    check (length(btrim(event_name)) > 0),
  exchange_name text not null default 'ticketblitz',
  routing_key text not null,
  payload jsonb not null,
  headers jsonb not null default '{}'::jsonb,
  waitlist_emails text[] not null default '{}'::text[],
  published boolean not null default false,
  published_at timestamptz,
  publish_error text,
  primary key (occurred_at, event_id)
) partition by range (occurred_at);

create table if not exists integration_events_2026_04
  partition of integration_events
  for values from ('2026-04-01 00:00:00+00') to ('2026-05-01 00:00:00+00');

create table if not exists integration_events_2026_05
  partition of integration_events
  for values from ('2026-05-01 00:00:00+00') to ('2026-06-01 00:00:00+00');

create table if not exists integration_events_default
  partition of integration_events
  default;

create or replace view v_waitlist_ranked as
select
  waitlist_id,
  event_id,
  category_id,
  user_id,
  status,
  joined_at,
  row_number() over (
    partition by event_id, category_id
    order by joined_at, waitlist_id
  ) as queue_position
from waitlist_entries
where status = 'WAITING';

create materialized view if not exists mv_sales_velocity_hourly as
select
  t.event_id,
  sh.category_id,
  date_trunc('hour', t.created_at) as hour_bucket,
  count(*) filter (
    where t.status in (
      'SUCCEEDED',
      'REFUND_PENDING',
      'REFUND_SUCCEEDED',
      'REFUND_FAILED'
    )
  ) as successful_payment_count,
  coalesce(sum(t.amount) filter (
    where t.status in (
      'SUCCEEDED',
      'REFUND_PENDING',
      'REFUND_SUCCEEDED',
      'REFUND_FAILED'
    )
  ), 0)::numeric(12,2) as gross_sales_amount
from transactions t
join seat_holds sh on sh.hold_id = t.hold_id
group by t.event_id, sh.category_id, date_trunc('hour', t.created_at)
with no data;

create unique index if not exists mv_sales_velocity_hourly_uk
  on mv_sales_velocity_hourly (event_id, category_id, hour_bucket);

create unique index if not exists users_email_active_uk
  on users (lower(email))
  where deleted_at is null;

create index if not exists users_search_vector_gin
  on users using gin (search_vector);

create index if not exists events_status_event_date_idx
  on events (status, event_date);

create index if not exists events_search_vector_gin
  on events using gin (search_vector);

create index if not exists seat_categories_event_active_idx
  on seat_categories (event_id, is_active, sort_order);

create index if not exists seats_event_category_status_idx
  on seats (event_id, category_id, status);

create index if not exists seats_category_id_idx
  on seats (category_id);

create index if not exists seats_status_idx
  on seats (status);

create unique index if not exists seat_holds_active_seat_uk
  on seat_holds (seat_id)
  where status = 'HELD';

create index if not exists seat_holds_event_status_expiry_idx
  on seat_holds (event_id, status, hold_expires_at);

create index if not exists seat_holds_category_id_idx
  on seat_holds (category_id);

create index if not exists seat_holds_user_status_created_idx
  on seat_holds (user_id, status, created_at desc);

create index if not exists waitlist_entries_next_idx
  on waitlist_entries (event_id, category_id, status, joined_at);

create index if not exists waitlist_entries_by_hold_idx
  on waitlist_entries (hold_id)
  where hold_id is not null;

create index if not exists waitlist_entries_category_id_idx
  on waitlist_entries (category_id);

create index if not exists waitlist_entries_user_id_idx
  on waitlist_entries (user_id);

create unique index if not exists waitlist_entries_active_user_uk
  on waitlist_entries (event_id, category_id, user_id)
  where status in ('WAITING', 'HOLD_OFFERED');

create index if not exists transactions_hold_status_created_idx
  on transactions (hold_id, status, created_at desc);

create index if not exists transactions_event_user_created_idx
  on transactions (event_id, user_id, created_at desc);

create index if not exists transactions_user_id_idx
  on transactions (user_id);

create index if not exists transactions_created_brin
  on transactions using brin (created_at);

create index if not exists transactions_provider_response_gin
  on transactions using gin (provider_response jsonb_path_ops);

create index if not exists transactions_pending_refund_idx
  on transactions (created_at)
  where refund_status = 'PENDING';

create index if not exists payment_webhook_events_intent_received_idx
  on payment_webhook_events (payment_intent_id, received_at desc);

create index if not exists payment_webhook_events_payload_gin
  on payment_webhook_events using gin (payload jsonb_path_ops);

create unique index if not exists flash_sales_active_event_uk
  on flash_sales (event_id)
  where status = 'ACTIVE';

create index if not exists flash_sales_event_status_time_idx
  on flash_sales (event_id, status, starts_at desc);

create index if not exists flash_sales_launched_by_user_id_idx
  on flash_sales (launched_by_user_id);

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'flash_sales_no_overlap_excl') then
    alter table flash_sales
      add constraint flash_sales_no_overlap_excl
      exclude using gist (
        event_id with =,
        active_window with &&
      )
      where (status = 'ACTIVE');
  end if;
end
$$;

create index if not exists price_changes_event_category_changed_idx
  on price_changes (event_id, category_id, changed_at desc);

create index if not exists price_changes_flash_sale_reason_changed_idx
  on price_changes (flash_sale_id, reason, changed_at desc);

create index if not exists price_changes_category_id_idx
  on price_changes (category_id);

create index if not exists price_changes_changed_brin
  on price_changes using brin (changed_at);

create index if not exists price_changes_context_gin
  on price_changes using gin (context jsonb_path_ops);

create index if not exists cancellation_requests_event_status_requested_idx
  on cancellation_requests (event_id, status, requested_at desc);

create index if not exists cancellation_requests_transaction_id_idx
  on cancellation_requests (transaction_id);

create index if not exists cancellation_requests_user_id_idx
  on cancellation_requests (user_id);

create unique index if not exists cancellation_requests_active_hold_uk
  on cancellation_requests (hold_id)
  where status in (
    'REQUESTED',
    'ELIGIBLE',
    'PROCESSING_REFUND',
    'REFUND_FAILED',
    'CANCELLATION_IN_PROGRESS'
  );

create index if not exists refund_attempts_request_attempted_idx
  on refund_attempts (cancellation_request_id, attempted_at desc);

create index if not exists refund_attempts_status_attempted_idx
  on refund_attempts (status, attempted_at desc);

create index if not exists refund_attempts_transaction_id_idx
  on refund_attempts (transaction_id);

create index if not exists refund_attempts_payload_gin
  on refund_attempts using gin (provider_payload jsonb_path_ops);

create index if not exists integration_events_published_occurred_idx
  on integration_events (published, occurred_at);

create index if not exists integration_events_occurred_brin
  on integration_events using brin (occurred_at);

create index if not exists integration_events_payload_gin
  on integration_events using gin (payload jsonb_path_ops);

create index if not exists integration_events_headers_gin
  on integration_events using gin (headers jsonb_path_ops);

create index if not exists integration_events_waitlist_emails_gin
  on integration_events using gin (waitlist_emails);

create index if not exists inventory_event_state_active_flash_sale_id_idx
  on inventory_event_state (active_flash_sale_id);

create index if not exists payment_webhook_events_hold_id_idx
  on payment_webhook_events (hold_id);

drop trigger if exists trg_users_set_updated_at on users;
create trigger trg_users_set_updated_at
before update on users
for each row
execute function set_row_updated_at();

drop trigger if exists trg_events_set_updated_at on events;
create trigger trg_events_set_updated_at
before update on events
for each row
execute function set_row_updated_at();

drop trigger if exists trg_seat_categories_set_updated_at on seat_categories;
create trigger trg_seat_categories_set_updated_at
before update on seat_categories
for each row
execute function set_row_updated_at();

drop trigger if exists trg_seats_set_updated_at on seats;
create trigger trg_seats_set_updated_at
before update on seats
for each row
execute function set_row_updated_at();

drop trigger if exists trg_seats_bump_version on seats;
create trigger trg_seats_bump_version
before update on seats
for each row
execute function bump_seat_version();

drop trigger if exists trg_seat_holds_set_updated_at on seat_holds;
create trigger trg_seat_holds_set_updated_at
before update on seat_holds
for each row
execute function set_row_updated_at();

drop trigger if exists trg_waitlist_entries_set_updated_at on waitlist_entries;
create trigger trg_waitlist_entries_set_updated_at
before update on waitlist_entries
for each row
execute function set_row_updated_at();

drop trigger if exists trg_transactions_set_updated_at on transactions;
create trigger trg_transactions_set_updated_at
before update on transactions
for each row
execute function set_row_updated_at();

drop trigger if exists trg_flash_sales_set_updated_at on flash_sales;
create trigger trg_flash_sales_set_updated_at
before update on flash_sales
for each row
execute function set_row_updated_at();

drop trigger if exists trg_inventory_event_state_set_updated_at on inventory_event_state;
create trigger trg_inventory_event_state_set_updated_at
before update on inventory_event_state
for each row
execute function set_row_updated_at();

drop trigger if exists trg_cancellation_requests_set_updated_at on cancellation_requests;
create trigger trg_cancellation_requests_set_updated_at
before update on cancellation_requests
for each row
execute function set_row_updated_at();

drop trigger if exists trg_integration_events_notify on integration_events;
create trigger trg_integration_events_notify
after insert on integration_events
for each row
execute function notify_ticketblitz_event();

alter table users enable row level security;
alter table events enable row level security;
alter table seat_categories enable row level security;
alter table seats enable row level security;
alter table seat_holds enable row level security;
alter table waitlist_entries enable row level security;
alter table transactions enable row level security;
alter table payment_webhook_events enable row level security;
alter table flash_sales enable row level security;
alter table price_changes enable row level security;
alter table inventory_event_state enable row level security;
alter table cancellation_requests enable row level security;
alter table refund_attempts enable row level security;
alter table integration_events enable row level security;
alter table integration_events_2026_04 enable row level security;
alter table integration_events_2026_05 enable row level security;
alter table integration_events_default enable row level security;

revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;

alter table seat_holds set (
  autovacuum_vacuum_scale_factor = 0.02,
  autovacuum_analyze_scale_factor = 0.01,
  autovacuum_vacuum_threshold = 500,
  autovacuum_analyze_threshold = 250
);

alter table waitlist_entries set (
  autovacuum_vacuum_scale_factor = 0.02,
  autovacuum_analyze_scale_factor = 0.01,
  autovacuum_vacuum_threshold = 500,
  autovacuum_analyze_threshold = 250
);

alter table transactions set (
  autovacuum_vacuum_scale_factor = 0.02,
  autovacuum_analyze_scale_factor = 0.01,
  autovacuum_vacuum_threshold = 500,
  autovacuum_analyze_threshold = 250
);

alter table cancellation_requests set (
  autovacuum_vacuum_scale_factor = 0.02,
  autovacuum_analyze_scale_factor = 0.01,
  autovacuum_vacuum_threshold = 250,
  autovacuum_analyze_threshold = 100
);

alter table refund_attempts set (
  autovacuum_vacuum_scale_factor = 0.02,
  autovacuum_analyze_scale_factor = 0.01,
  autovacuum_vacuum_threshold = 250,
  autovacuum_analyze_threshold = 100
);

alter table integration_events_default set (
  autovacuum_vacuum_scale_factor = 0.02,
  autovacuum_analyze_scale_factor = 0.01,
  autovacuum_vacuum_threshold = 500,
  autovacuum_analyze_threshold = 250
);

comment on table integration_events is
  'Partitioned outbox/event-log table for AMQP integration and replay-safe publishing.';

comment on materialized view mv_sales_velocity_hourly is
  'Hourly sales rollup used by Organiser Dashboard analytics; refresh on schedule.';

commit;
