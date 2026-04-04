# TicketBlitz Login and Sign-Up Manual Test Suite

Date: 2026-04-02  
Project: TicketBlitz  
Environment: Browser-based manual testing against Supabase project `cpxcpvcfbohvpiubbujg`

## 1) Project Context Analysis (Setup.md and Scenarios.md)

This suite is based on a detailed read of `docs/Setup.md` and `docs/Scenarios.md` plus current frontend/auth implementation.

### Key context from setup
- TicketBlitz is a microservices platform fronted by Kong, with Supabase as the core database/auth backbone.
- Two browser UIs exist: fan-facing and organiser-facing, and both depend on valid authentication state for protected flows.
- The platform relies on strict service boundaries and role-aware behavior (fan vs organiser) across scenarios.

### Key context from scenarios
- Scenario flows repeatedly assume authenticated user identity before purchase, waitlist progression, cancellation, and organiser operations.
- Authentication correctness is therefore a critical path dependency for all Scenario 1-3 browser journeys.
- Roles are business-significant in scenario documentation (fan, organiser), so sign-up metadata and post-login routing behavior matter.

### Why this matters for this suite
This suite prioritizes browser-verifiable auth behavior that can block or invalidate scenario demos:
1. Can users sign up and log in reliably?
2. Are protected routes guarded correctly?
3. Are redirect and error-handling paths safe and predictable?
4. Does runtime behavior match live Supabase configuration and data reality?

---

## 2) Implementation Under Test

Primary frontend files:
- `frontend/src/composables/useAuth.js`
- `frontend/src/pages/SignInPage.vue`
- `frontend/src/pages/SignUpPage.vue`
- `frontend/src/router/index.js`
- `frontend/src/stores/authStore.js`
- `frontend/src/lib/supabaseClient.js`

Referenced test intent from code tests:
- `frontend/src/composables/useAuth.test.js`
- `frontend/src/router/index.test.js`

---

## 3) Live Supabase Context Snapshot (Project `cpxcpvcfbohvpiubbujg`)

SQL and metadata inspection used to generate realistic test inputs:

1. `auth.users` currently has 1 row.
2. `public.users` currently has 6 active rows (seeded team profiles).
3. Current mismatch: `auth.users` count != `public.users` count.
4. Trigger exists on `auth.users`:
   - `trg_auth_users_autoconfirm_fan` -> `autoconfirm_fan_auth_signup()`.
  - `trg_auth_users_sync_public_profile` -> `sync_public_user_from_auth()`.
5. Trigger function logic intends to auto-confirm fan email signups.
6. Observed latest auth row still has `email_confirmed_at = null` and `confirmed_at = null`.
7. `public.users` now has `auth_user_id` mapping to `auth.users(id)` for identity linking.
8. Roles are normalized in `public.user_roles` (single role per user), while `public.users.metadata.role` is retained for backward compatibility.
9. `public.users` has constraints:
   - `full_name` length 1..100
   - email must include `@`

Implication for testing:
- Treat sign-up as branchy: it may auto-authenticate immediately or may require confirmation.
- Seeded `public.users` emails are not guaranteed valid login accounts unless corresponding `auth.users` accounts exist.

---

## 4) Expected Login and Sign-Up Flow

## 4.1 Sign-Up expected flow
1. User opens `/sign-up`.
2. User fills full name, email, password, and accepts terms checkbox.
3. Frontend local validation runs:
   - full name trimmed length must be 1..100
   - email must contain `@` and not start with `@`
4. Frontend calls Supabase `auth.signUp` with:
   - email normalized to lowercase
   - metadata `full_name` and `role: fan`
   - `emailRedirectTo` set to `/sign-in`
5. Branch A (session returned):
   - session saved
   - success path redirects to safe internal target (`redirect` query or `/`)
6. Branch B (no session returned):
   - frontend immediately attempts `signInWithPassword` fallback
   - B1: fallback success -> authenticated redirect
   - B2: fallback error -> remain on sign-up and show error message

## 4.2 Login expected flow
1. User opens `/sign-in`.
2. User submits email and password.
3. Frontend normalizes email (trim + lowercase).
4. Frontend calls `signInWithPassword`.
5. On success:
   - auth session stored
   - success message shown
   - redirect to safe internal path from query, or `/`
6. On failure:
   - stay on sign-in
   - display Supabase/auth error message

## 4.3 Route/redirect guard expected flow
1. Unauthenticated user accessing protected routes (`/organiser-dashboard`, `/ticket-purchase`, `/my-tickets`) is redirected to `/sign-in?redirect=<original-path>`.
2. Authenticated user accessing guest-only routes (`/sign-in`, `/sign-up`) is redirected away.
3. Redirect normalization blocks unsafe values (`https://...`, `//...`) and falls back to the authenticated user's role-home route (`/my-tickets` for fans, `/organiser-dashboard` for organisers).

---

## 5) Test Data Inputs

Use these values consistently in manual tests.

### Reusable dynamic inputs
- `NEW_EMAIL_1`: `qa.auth.1.<timestamp>@ticketblitz.com`
- `NEW_EMAIL_2`: `qa.auth.2.<timestamp>@ticketblitz.com`
- `VALID_PASSWORD`: `TicketBlitz#2026!`
- `WRONG_PASSWORD`: `WrongPass#2026!`
- `LONG_NAME_101`: any 101-character name string

### Useful existing data points
- `SEEDED_PUBLIC_EMAIL`: `brandon@ticketblitz.com` (present in `public.users`)
- `CURRENT_AUTH_EMAIL`: `user@ticketblitz.com` (present in `auth.users`)
- `ORGANISER_AUTH_EMAIL`: `organiser@ticketblitz.com` (role: organiser)
- `ORGANISER_AUTH_PASSWORD`: `organiser123`
- `BRANDON_AUTH_EMAIL`: `brandon@ticketblitz.com` (role: organiser)
- `BRANDON_AUTH_PASSWORD`: `brandon123`
- `MIK_AUTH_EMAIL`: `mik@ticketblitz.com` (role: organiser)
- `MIK_AUTH_PASSWORD`: `mik123`

Note: Public profile rows imply login only when linked to `auth.users` (`public.users.auth_user_id` is not null).

---

## 6) Manual Browser Test Cases

Each case includes explicit input and expected output.

### TC-AUTH-001 - Protected route redirect for guest
- Priority: High
- Preconditions: Logged out (or fresh incognito session)
- Test input: Direct URL `/my-tickets`
- Steps:
  1. Open browser to `/my-tickets`.
- Expected output:
  1. You are redirected to `/sign-in?redirect=/my-tickets`.
  2. Sign-in form is visible.

### TC-AUTH-002 - Protected organiser route redirect for guest
- Priority: High
- Preconditions: Logged out
- Test input: Direct URL `/organiser-dashboard`
- Steps:
  1. Open `/organiser-dashboard`.
- Expected output:
  1. Redirected to `/sign-in?redirect=/organiser-dashboard`.

### TC-AUTH-003 - Block unsafe external redirect
- Priority: High
- Preconditions: Logged in
- Test input: URL `/sign-in?redirect=https://evil.example`
- Steps:
  1. Visit `/sign-in?redirect=https://evil.example` while authenticated.
- Expected output:
  1. Redirect target is normalized.
  2. Final location is role-home (`/my-tickets` for fans, `/organiser-dashboard` for organisers), not an external URL.

### TC-AUTH-004 - Guest-only route blocked when authenticated
- Priority: Medium
- Preconditions: Logged in
- Test input: URL `/sign-up?redirect=/my-tickets`
- Steps:
  1. Visit `/sign-up?redirect=/my-tickets`.
- Expected output:
  1. You are redirected away from guest page.
  2. Final location is `/my-tickets`.

### TC-AUTH-005 - Terms checkbox required on sign-up
- Priority: High
- Preconditions: On `/sign-up`
- Test input:
  - full name: `QA User`
  - email: `NEW_EMAIL_1`
  - password: `VALID_PASSWORD`
  - terms: unchecked
- Steps:
  1. Fill fields.
  2. Leave terms unchecked.
  3. Click `Create Account`.
- Expected output:
  1. Error message shown: `You must accept the terms before account creation.`
  2. No redirect occurs.
  3. No account is created.

### TC-AUTH-006 - Reject whitespace-only full name
- Priority: High
- Preconditions: On `/sign-up`, terms checked
- Test input:
  - full name: `   `
  - email: `NEW_EMAIL_1`
  - password: `VALID_PASSWORD`
- Steps:
  1. Submit form.
- Expected output:
  1. Error message includes `Full name must be between 1 and 100 characters.`
  2. No sign-up API success path.

### TC-AUTH-007 - Reject full name > 100 chars
- Priority: High
- Preconditions: On `/sign-up`, terms checked
- Test input:
  - full name: `LONG_NAME_101`
  - email: `NEW_EMAIL_1`
  - password: `VALID_PASSWORD`
- Steps:
  1. Submit form.
- Expected output:
  1. Error message includes `Full name must be between 1 and 100 characters.`

### TC-AUTH-008 - Reject invalid email missing @
- Priority: High
- Preconditions: On `/sign-up`, terms checked
- Test input:
  - full name: `QA User`
  - email: `qa.ticketblitz.com`
  - password: `VALID_PASSWORD`
- Steps:
  1. Submit form.
- Expected output:
  1. Error message: `Please provide a valid email address.`

### TC-AUTH-009 - Backend password policy validation failure path
- Priority: Medium
- Preconditions: On `/sign-up`, terms checked
- Test input:
  - full name: `QA Password Policy`
  - email: `NEW_EMAIL_2`
  - password: `123`
- Steps:
  1. Submit form.
- Expected output:
  1. Frontend local validation passes and request is sent.
  2. Backend rejects the weak password due to password policy.
  3. Error shown from Supabase/Auth (for example `Password should be at least 6 characters`).
  4. User remains on sign-up page.

### TC-AUTH-010 - Verify sign-up payload includes redirect and role metadata
- Priority: Medium
- Preconditions: Browser DevTools network tab open
- Test input:
  - full name: `QA Metadata User`
  - email: `NEW_EMAIL_1`
  - password: `VALID_PASSWORD`
- Steps:
  1. Submit sign-up.
  2. Inspect signup request payload in network tools.
- Expected output:
  1. Payload includes metadata with `full_name` and `role: fan`.
  2. Payload includes redirect URL targeting `/sign-in`.

### TC-AUTH-011 - Sign-up success path (auto-auth branch)
- Priority: High
- Preconditions: Use a fresh email, terms checked
- Test input:
  - full name: `QA Auto Auth`
  - email: `NEW_EMAIL_1`
  - password: `VALID_PASSWORD`
  - URL: `/sign-in?redirect=/my-tickets`
- Steps:
  1. Open `/sign-in?redirect=/my-tickets`.
  2. Click `Need account?` (or top action) to navigate to `/sign-up`.
  3. Submit valid inputs.
- Expected output:
  1. If session is established (immediate or fallback sign-in), user is redirected to `/my-tickets`.
  2. Protected page is accessible without another login.

### TC-AUTH-012 - Sign-up no-session fallback error path
- Priority: High
- Preconditions: Environment where email confirmation is still required
- Test input:
  - full name: `QA Confirm Required`
  - email: `NEW_EMAIL_2`
  - password: `VALID_PASSWORD`
  - URL: `/sign-in`
- Steps:
  1. Open `/sign-in`.
  2. Click `Need account?` (or top action) to navigate to `/sign-up`.
  3. Submit sign-up.
- Expected output:
  1. If fallback sign-in fails, user remains on sign-up page.
  2. Error message from sign-in attempt is displayed.
  3. No authenticated redirect occurs.

### TC-AUTH-013 - Duplicate email sign-up
- Priority: High
- Preconditions: Account already exists for email
- Test input:
  - full name: `QA Existing`
  - email: `NEW_EMAIL_1` (already used)
  - password: `VALID_PASSWORD`
- Steps:
  1. Attempt sign-up again with same email.
- Expected output:
  1. Sign-up fails with: `A user with the same email already exists. Please log in instead.`
  2. User remains on sign-up.

### TC-AUTH-014 - Sign-in success with preserved internal redirect
- Priority: High
- Preconditions: A known valid confirmed account exists
- Test input:
  - URL: `/sign-in?redirect=/ticket-purchase`
  - email: valid account email
  - password: matching password
- Steps:
  1. Submit sign-in.
- Expected output:
  1. Success message displayed briefly.
  2. Redirect to `/ticket-purchase`.

### TC-AUTH-015 - Sign-in wrong password
- Priority: High
- Preconditions: Valid account exists
- Test input:
  - email: valid account email
  - password: `WRONG_PASSWORD`
- Steps:
  1. Submit sign-in.
- Expected output:
  1. Error message shown: `Email or password is wrong.`
  2. Stay on sign-in page.

### TC-AUTH-016 - Public-only profile email cannot login
- Priority: High
- Preconditions: On `/sign-in`
- Test input:
  - email: any email that exists only in `public.users` and has no `auth_user_id` link
  - password: any guessed value, for example `VALID_PASSWORD`
- Steps:
  1. Submit sign-in.
- Expected output:
  1. Login fails with auth error.
  2. Confirms `public.users` rows without auth identity are not equivalent to auth accounts.

### TC-AUTH-017 - Email normalization on sign-in
- Priority: Medium
- Preconditions: Valid account exists
- Test input:
  - email: `  USER@TICKETBLITZ.COM  ` (same account in uppercase + spaces)
  - password: correct password
- Steps:
  1. Submit sign-in.
- Expected output:
  1. Email is normalized by frontend.
  2. Login behavior matches lowercase trimmed equivalent.

### TC-AUTH-018 - Clear messages when user edits fields
- Priority: Medium
- Preconditions: Produce any sign-in or sign-up error first
- Test input: any keystroke in a form field
- Steps:
  1. Trigger visible error message.
  2. Type in any input field.
- Expected output:
  1. Previous error/success message clears immediately.

### TC-AUTH-019 - Loading state and disabled submit
- Priority: Medium
- Preconditions: Network available
- Test input: valid sign-in or sign-up request
- Steps:
  1. Click submit.
  2. Observe button while request is in-flight.
- Expected output:
  1. Submit button disabled during request.
  2. Button label changes to loading text (`Signing In` or `Creating Account`).
  3. Button returns to normal after completion.

### TC-AUTH-020 - Session persistence across refresh
- Priority: Medium
- Preconditions: Logged in
- Test input: browser refresh on protected route
- Steps:
  1. Log in.
  2. Navigate to `/my-tickets`.
  3. Refresh the browser.
- Expected output:
  1. Session is restored.
  2. User remains authenticated and stays on protected page.

### TC-AUTH-021 - Missing Supabase config behavior
- Priority: Medium
- Preconditions: Temporarily remove `VITE_SUPABASE_URL` or `VITE_SUPABASE_ANON_KEY`, restart frontend
- Test input:
  - attempt sign-in and protected-route access
- Steps:
  1. Open protected route as guest.
  2. Attempt sign-in.
- Expected output:
  1. Protected route still redirects to sign-in.
  2. Sign-in shows `Missing Supabase configuration for authentication.`
  3. No successful auth session is created.

### TC-AUTH-022 - Sign-up password visibility toggle
- Priority: Low
- Preconditions: On `/sign-up`
- Test input: any password value
- Steps:
  1. Enter password.
  2. Click `View`.
  3. Click `Hide`.
- Expected output:
  1. Password input toggles between masked and plain text.
  2. No value loss while toggling.

### TC-AUTH-023 - Fan blocked from organiser dashboard
- Priority: High
- Preconditions: Logged in as a fan account
- Test input: Direct URL `/organiser-dashboard`
- Steps:
  1. Navigate to `/organiser-dashboard`.
- Expected output:
  1. Access to organiser dashboard is denied.
  2. User is redirected to `/my-tickets`.

### TC-AUTH-024 - Organiser blocked from fan dashboard
- Priority: High
- Preconditions: Logged in as organiser (`ORGANISER_AUTH_EMAIL` / `ORGANISER_AUTH_PASSWORD`)
- Test input: Direct URL `/my-tickets`
- Steps:
  1. Navigate to `/my-tickets`.
- Expected output:
  1. Access to fan dashboard is denied.
  2. User is redirected to `/organiser-dashboard`.

### TC-AUTH-025 - Organiser account dashboard access
- Priority: High
- Preconditions: Organiser account exists in auth + linked public user profile
- Test input:
  - URL: `/sign-in`
  - email: `ORGANISER_AUTH_EMAIL`
  - password: `ORGANISER_AUTH_PASSWORD`
- Steps:
  1. Sign in with organiser credentials.
  2. Navigate to `/organiser-dashboard`.
- Expected output:
  1. Sign-in succeeds.
  2. Organiser dashboard is accessible.
  3. Session role indicator displays organiser role.

### TC-AUTH-026 - Additional organiser demo accounts can login
- Priority: High
- Preconditions: Organiser reconciliation seed has run successfully
- Test input:
  - Account A:
    - email: `BRANDON_AUTH_EMAIL`
    - password: `BRANDON_AUTH_PASSWORD`
  - Account B:
    - email: `MIK_AUTH_EMAIL`
    - password: `MIK_AUTH_PASSWORD`
- Steps:
  1. Sign in with Account A and verify redirect target.
  2. Sign out.
  3. Sign in with Account B and verify redirect target.
- Expected output:
  1. Both logins succeed.
  2. Both accounts are routed to `/organiser-dashboard`.
  3. Access to `/my-tickets` is denied for both accounts.

---

## 7) Optional SQL Assertions (Post-Test Validation)

Use these checks when you want stronger evidence beyond browser UI:

1. Verify auth user created:
   - `select id, email, email_confirmed_at, confirmed_at, raw_user_meta_data from auth.users where lower(email) = lower('<new-email>');`
2. Verify no automatic public user row was created (current observed behavior):
   - `select user_id, email from public.users where lower(email) = lower('<new-email>');`
3. Verify auth/public counts for drift awareness:
   - `select (select count(*) from auth.users) as auth_users_count, (select count(*) from public.users where deleted_at is null) as public_users_active_count;`

---

## 8) Coverage Summary

This manual suite covers:
1. Happy paths for login and sign-up.
2. Local validation edge cases.
3. Backend error handling and fallback branches.
4. Security-sensitive redirect normalization.
5. Protected route guard behavior including strict fan/organiser dashboard isolation.
6. UX state behavior (loading and message reset).
7. Environment misconfiguration behavior.
8. Live Supabase data realities that affect demo reliability.
