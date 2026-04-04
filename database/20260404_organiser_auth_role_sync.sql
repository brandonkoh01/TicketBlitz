-- TicketBlitz migration: organiser auth + normalized role model
-- Date: 2026-04-04
-- Note: apply this in a write-enabled Supabase SQL context.

begin;

alter table public.users
  add column if not exists auth_user_id uuid references auth.users(id) on delete set null;

create unique index if not exists users_auth_user_id_uk
  on public.users (auth_user_id)
  where auth_user_id is not null;

do $$
begin
  if not exists (select 1 from pg_type where typname = 'app_role_t') then
    create type public.app_role_t as enum ('fan', 'organiser');
  end if;
end $$;

create table if not exists public.user_roles (
  user_id uuid primary key references public.users(user_id) on delete cascade,
  role public.app_role_t not null,
  assigned_at timestamptz not null default now(),
  assigned_by uuid references public.users(user_id) on delete set null
);

create index if not exists user_roles_role_user_id_idx
  on public.user_roles (role, user_id);

create or replace function public.sync_public_user_from_auth()
returns trigger
language plpgsql
security definer
set search_path = public, auth, extensions
as $$
declare
  v_email text;
  v_full_name text;
  v_role text;
begin
  if new.email is null then
    return new;
  end if;

  v_email := lower(new.email);
  v_full_name := nullif(btrim(coalesce(new.raw_user_meta_data->>'full_name', '')), '');
  if v_full_name is null then
    v_full_name := split_part(v_email, '@', 1);
  end if;

  v_role := lower(coalesce(new.raw_app_meta_data->>'role', new.raw_user_meta_data->>'role', 'fan'));
  if v_role not in ('fan', 'organiser') then
    v_role := 'fan';
  end if;

  update public.users
  set
    full_name = coalesce(v_full_name, full_name),
    email = v_email,
    auth_user_id = new.id,
    metadata = jsonb_set(coalesce(metadata, '{}'::jsonb), '{role}', to_jsonb(v_role), true),
    deleted_at = null,
    updated_at = now()
  where auth_user_id = new.id;

  if not found then
    update public.users
    set
      full_name = coalesce(v_full_name, full_name),
      auth_user_id = new.id,
      metadata = jsonb_set(coalesce(metadata, '{}'::jsonb), '{role}', to_jsonb(v_role), true),
      deleted_at = null,
      updated_at = now()
    where lower(email) = v_email
      and deleted_at is null;
  end if;

  if not found then
    insert into public.users (user_id, auth_user_id, full_name, email, metadata)
    values (new.id, new.id, v_full_name, v_email, jsonb_build_object('role', v_role))
    on conflict (user_id) do update
    set
      auth_user_id = excluded.auth_user_id,
      full_name = excluded.full_name,
      email = excluded.email,
      metadata = excluded.metadata,
      deleted_at = null,
      updated_at = now();
  end if;

  insert into public.user_roles (user_id, role)
  select u.user_id, v_role::public.app_role_t
  from public.users u
  where u.auth_user_id = new.id
  on conflict (user_id) do update
  set role = excluded.role,
      assigned_at = now();

  return new;
end;
$$;

drop trigger if exists trg_auth_users_sync_public_profile on auth.users;
create trigger trg_auth_users_sync_public_profile
after insert or update of email, raw_user_meta_data, raw_app_meta_data
on auth.users
for each row
execute function public.sync_public_user_from_auth();

update public.users pu
set
  auth_user_id = au.id,
  updated_at = now()
from auth.users au
where pu.auth_user_id is null
  and pu.deleted_at is null
  and lower(pu.email) = lower(au.email);

insert into public.user_roles (user_id, role)
select
  u.user_id,
  (
    case
      when lower(coalesce(au.raw_app_meta_data->>'role', u.metadata->>'role', 'fan')) = 'organiser'
      then 'organiser'::public.app_role_t
      else 'fan'::public.app_role_t
    end
  ) as role
from public.users u
left join auth.users au on au.id = u.auth_user_id
where u.deleted_at is null
on conflict (user_id) do update
set role = excluded.role,
    assigned_at = now();

create or replace function public.current_user_role()
returns text
language sql
stable
security definer
set search_path = public
as $$
  select coalesce(
    (
      select ur.role::text
      from public.user_roles ur
      join public.users u on u.user_id = ur.user_id
      where u.auth_user_id = (select auth.uid())
        and u.deleted_at is null
      limit 1
    ),
    'fan'
  );
$$;

create or replace function public.is_current_user_organiser()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select public.current_user_role() = 'organiser';
$$;

alter table public.user_roles enable row level security;

drop policy if exists users_select_self on public.users;
create policy users_select_self
on public.users
for select
to authenticated
using ((select auth.uid()) = auth_user_id);

drop policy if exists users_update_self on public.users;
create policy users_update_self
on public.users
for update
to authenticated
using ((select auth.uid()) = auth_user_id)
with check ((select auth.uid()) = auth_user_id);

drop policy if exists user_roles_select_self on public.user_roles;
create policy user_roles_select_self
on public.user_roles
for select
to authenticated
using (
  exists (
    select 1
    from public.users u
    where u.user_id = user_roles.user_id
      and u.auth_user_id = (select auth.uid())
  )
);

grant select, update on table public.users to authenticated;
grant select on table public.user_roles to authenticated;
revoke all on function public.current_user_role() from public;
revoke all on function public.is_current_user_organiser() from public;
grant execute on function public.current_user_role() to authenticated;
grant execute on function public.is_current_user_organiser() to authenticated;

revoke all on table public.user_roles from anon;

commit;
