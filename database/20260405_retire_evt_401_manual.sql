-- TicketBlitz safe cleanup: soft-retire EVT-401-MANUAL while preserving history.

begin;

set search_path = public, extensions;

update public.events
set
  status = 'CANCELLED',
  deleted_at = coalesce(deleted_at, now()),
  metadata = jsonb_set(
    coalesce(metadata, '{}'::jsonb),
    '{retired_reason}',
    to_jsonb('manual_policy_boundary_cleanup'::text),
    true
  ),
  updated_at = now()
where event_id = '10000000-0000-0000-0000-000000000401'::uuid;

commit;
