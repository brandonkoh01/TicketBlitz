-- TicketBlitz organiser auth/profile seed
-- Ensures organiser@ticketblitz.com exists in auth.users + auth.identities + public.users
-- Credentials for test/demo use only:
--   email: organiser@ticketblitz.com
--   password: organiser123

begin;

do $$
declare
  v_user_id uuid;
  v_now timestamptz := now();
begin
  select u.id
  into v_user_id
  from auth.users u
  where lower(u.email) = 'organiser@ticketblitz.com'
  limit 1;

  if v_user_id is null then
    v_user_id := gen_random_uuid();

    insert into auth.users (
      id,
      aud,
      role,
      email,
      encrypted_password,
      email_confirmed_at,
      raw_app_meta_data,
      raw_user_meta_data,
      is_sso_user,
      is_anonymous,
      created_at,
      updated_at
    )
    values (
      v_user_id,
      'authenticated',
      'authenticated',
      'organiser@ticketblitz.com',
      extensions.crypt('organiser123', extensions.gen_salt('bf', 10)),
      v_now,
      jsonb_build_object('provider', 'email', 'providers', jsonb_build_array('email')),
      jsonb_build_object(
        'sub', v_user_id::text,
        'email', 'organiser@ticketblitz.com',
        'full_name', 'TicketBlitz Organiser',
        'role', 'organiser',
        'email_verified', true,
        'phone_verified', false
      ),
      false,
      false,
      v_now,
      v_now
    );
  else
    update auth.users
    set
      aud = 'authenticated',
      role = 'authenticated',
      email = 'organiser@ticketblitz.com',
      encrypted_password = extensions.crypt('organiser123', extensions.gen_salt('bf', 10)),
      email_confirmed_at = coalesce(email_confirmed_at, v_now),
      raw_app_meta_data = jsonb_build_object('provider', 'email', 'providers', jsonb_build_array('email')),
      raw_user_meta_data = jsonb_build_object(
        'sub', v_user_id::text,
        'email', 'organiser@ticketblitz.com',
        'full_name', 'TicketBlitz Organiser',
        'role', 'organiser',
        'email_verified', true,
        'phone_verified', false
      ),
      is_sso_user = false,
      is_anonymous = false,
      deleted_at = null,
      updated_at = v_now
    where id = v_user_id;
  end if;

  insert into auth.identities (
    id,
    user_id,
    identity_data,
    provider,
    provider_id,
    email,
    created_at,
    updated_at,
    last_sign_in_at
  )
  values (
    gen_random_uuid(),
    v_user_id,
    jsonb_build_object(
      'sub', v_user_id::text,
      'email', 'organiser@ticketblitz.com',
      'full_name', 'TicketBlitz Organiser',
      'role', 'organiser',
      'email_verified', true,
      'phone_verified', false
    ),
    'email',
    v_user_id::text,
    'organiser@ticketblitz.com',
    v_now,
    v_now,
    v_now
  )
  on conflict (provider_id, provider) do update
  set
    user_id = excluded.user_id,
    identity_data = excluded.identity_data,
    email = excluded.email,
    updated_at = excluded.updated_at,
    last_sign_in_at = excluded.last_sign_in_at;

  insert into public.users (user_id, full_name, email, phone, metadata)
  values (
    v_user_id,
    'TicketBlitz Organiser',
    'organiser@ticketblitz.com',
    null,
    '{"role":"organiser"}'::jsonb
  )
  on conflict (user_id) do update
  set
    full_name = excluded.full_name,
    email = excluded.email,
    phone = excluded.phone,
    metadata = excluded.metadata,
    deleted_at = null,
    updated_at = v_now;
end $$;

commit;
