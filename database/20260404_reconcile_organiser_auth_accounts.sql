-- TicketBlitz data reconciliation: provision auth identities for organiser profiles
-- Date: 2026-04-04
-- Purpose: ensure organiser profiles in public.users are login-capable in Supabase Auth.
--
-- Demo credentials set by this script:
--   organiser@ticketblitz.com -> organiser123
--   brandon@ticketblitz.com -> brandon123
--   mik@ticketblitz.com -> mik123
--   any other organiser profile -> organiser123

begin;

do $$
declare
  r record;
  v_auth_id uuid;
  v_password text;
  v_now timestamptz := now();
begin
  for r in
    select
      u.user_id,
      lower(u.email) as email,
      coalesce(nullif(btrim(u.full_name), ''), split_part(lower(u.email), '@', 1)) as full_name
    from public.users u
    where u.deleted_at is null
      and lower(coalesce(u.metadata->>'role', 'fan')) = 'organiser'
      and u.email is not null
  loop
    v_password := case r.email
      when 'organiser@ticketblitz.com' then 'organiser123'
      when 'brandon@ticketblitz.com' then 'brandon123'
      when 'mik@ticketblitz.com' then 'mik123'
      else 'organiser123'
    end;

    select au.id
    into v_auth_id
    from auth.users au
    where lower(au.email) = r.email
    limit 1;

    if v_auth_id is null then
      v_auth_id := r.user_id;

      insert into auth.users (
        instance_id,
        id,
        aud,
        role,
        email,
        encrypted_password,
        email_confirmed_at,
        confirmation_token,
        recovery_token,
        email_change_token_new,
        email_change_token_current,
        phone_change_token,
        reauthentication_token,
        email_change,
        phone_change,
        raw_app_meta_data,
        raw_user_meta_data,
        is_sso_user,
        is_anonymous,
        created_at,
        updated_at
      )
      values (
        '00000000-0000-0000-0000-000000000000'::uuid,
        v_auth_id,
        'authenticated',
        'authenticated',
        r.email,
        extensions.crypt(v_password, extensions.gen_salt('bf', 10)),
        v_now,
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        '',
        jsonb_build_object(
          'provider', 'email',
          'providers', jsonb_build_array('email'),
          'role', 'organiser'
        ),
        jsonb_build_object(
          'sub', v_auth_id::text,
          'email', r.email,
          'full_name', r.full_name,
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
        instance_id = coalesce(instance_id, '00000000-0000-0000-0000-000000000000'::uuid),
        aud = 'authenticated',
        role = 'authenticated',
        email = r.email,
        encrypted_password = extensions.crypt(v_password, extensions.gen_salt('bf', 10)),
        email_confirmed_at = coalesce(email_confirmed_at, v_now),
        confirmation_token = coalesce(confirmation_token, ''),
        recovery_token = coalesce(recovery_token, ''),
        email_change_token_new = coalesce(email_change_token_new, ''),
        email_change_token_current = coalesce(email_change_token_current, ''),
        phone_change_token = coalesce(phone_change_token, ''),
        reauthentication_token = coalesce(reauthentication_token, ''),
        email_change = coalesce(email_change, ''),
        phone_change = coalesce(phone_change, ''),
        raw_app_meta_data = jsonb_build_object(
          'provider', 'email',
          'providers', jsonb_build_array('email'),
          'role', 'organiser'
        ),
        raw_user_meta_data = jsonb_build_object(
          'sub', v_auth_id::text,
          'email', r.email,
          'full_name', r.full_name,
          'role', 'organiser',
          'email_verified', true,
          'phone_verified', false
        ),
        is_sso_user = false,
        is_anonymous = false,
        deleted_at = null,
        updated_at = v_now
      where id = v_auth_id;
    end if;

    insert into auth.identities (
      id,
      user_id,
      identity_data,
      provider,
      provider_id,
      created_at,
      updated_at,
      last_sign_in_at
    )
    values (
      gen_random_uuid(),
      v_auth_id,
      jsonb_build_object(
        'sub', v_auth_id::text,
        'email', r.email,
        'full_name', r.full_name,
        'role', 'organiser',
        'email_verified', true,
        'phone_verified', false
      ),
      'email',
      v_auth_id::text,
      v_now,
      v_now,
      v_now
    )
    on conflict (provider_id, provider) do update
    set
      user_id = excluded.user_id,
      identity_data = excluded.identity_data,
      updated_at = excluded.updated_at,
      last_sign_in_at = excluded.last_sign_in_at;

    update public.users
    set
      auth_user_id = v_auth_id,
      full_name = r.full_name,
      email = r.email,
      metadata = jsonb_set(coalesce(metadata, '{}'::jsonb), '{role}', to_jsonb('organiser'::text), true),
      deleted_at = null,
      updated_at = v_now
    where user_id = r.user_id;

    insert into public.user_roles (user_id, role)
    values (r.user_id, 'organiser'::public.app_role_t)
    on conflict (user_id) do update
    set role = excluded.role,
        assigned_at = v_now;
  end loop;
end $$;

commit;
