import { afterEach, describe, expect, it, vi } from 'vitest'

async function loadUseAuth({ hasConfig = true, supabaseMock } = {}) {
  vi.resetModules()

  const setAuthSession = vi.fn()

  vi.doMock('@/stores/authStore', () => ({
    useAuthStore: () => ({
      setAuthSession,
    }),
  }))

  vi.doMock('@/lib/supabaseClient', () => ({
    hasSupabaseConfig: hasConfig,
    getSupabaseClient: () => supabaseMock,
  }))

  const { useAuth } = await import('./useAuth.js')

  return {
    useAuth,
    setAuthSession,
  }
}

afterEach(() => {
  vi.restoreAllMocks()
  vi.resetModules()
})

describe('useAuth', () => {
  it('validates full name before calling Supabase signUp', async () => {
    const supabaseMock = {
      auth: {
        signUp: vi.fn(),
        signInWithPassword: vi.fn(),
      },
    }

    const { useAuth } = await loadUseAuth({ supabaseMock })
    const auth = useAuth()

    const result = await auth.signUpFan({
      fullName: '   ',
      email: 'fan@example.com',
      password: 'password-123',
    })

    expect(result.error).toBeInstanceOf(Error)
    expect(auth.errorMessage.value).toContain('Full name')
    expect(supabaseMock.auth.signUp).not.toHaveBeenCalled()
  })

  it('returns fallback sign-in error instead of reporting success', async () => {
    const signInError = { message: 'Invalid login credentials' }

    const supabaseMock = {
      auth: {
        signUp: vi.fn().mockResolvedValue({
          data: {
            session: null,
            user: { id: 'user-1' },
          },
          error: null,
        }),
        signInWithPassword: vi.fn().mockResolvedValue({
          data: {
            session: null,
            user: null,
          },
          error: signInError,
        }),
      },
    }

    const { useAuth } = await loadUseAuth({ supabaseMock })
    const auth = useAuth()

    const result = await auth.signUpFan({
      fullName: 'Ticket Blitz Fan',
      email: 'fan@example.com',
      password: 'password-123',
    })

    expect(result.error).toBe(signInError)
    expect(auth.successMessage.value).toBe('')
    expect(auth.errorMessage.value).toBe('Email or password is wrong.')
  })

  it('maps duplicate sign-up errors to a friendly duplicate-account message', async () => {
    const signUpError = { message: 'User already registered' }

    const supabaseMock = {
      auth: {
        signUp: vi.fn().mockResolvedValue({
          data: {
            session: null,
            user: null,
          },
          error: signUpError,
        }),
        signInWithPassword: vi.fn(),
      },
    }

    const { useAuth } = await loadUseAuth({ supabaseMock })
    const auth = useAuth()

    const result = await auth.signUpFan({
      fullName: 'Ticket Blitz Fan',
      email: 'fan@example.com',
      password: 'password-123',
    })

    expect(result.error).toBe(signUpError)
    expect(auth.errorMessage.value).toBe('A user with the same email already exists. Please log in instead.')
    expect(auth.successMessage.value).toBe('')
  })

  it('treats obfuscated duplicate sign-up responses as duplicate accounts', async () => {
    const existingUser = {
      id: 'existing-user-1',
      email: 'fan@example.com',
      identities: [],
    }

    const supabaseMock = {
      auth: {
        signUp: vi.fn().mockResolvedValue({
          data: {
            session: null,
            user: existingUser,
          },
          error: null,
        }),
        signInWithPassword: vi.fn(),
      },
    }

    const { useAuth } = await loadUseAuth({ supabaseMock })
    const auth = useAuth()

    const result = await auth.signUpFan({
      fullName: 'Ticket Blitz Fan',
      email: 'fan@example.com',
      password: 'password-123',
    })

    expect(supabaseMock.auth.signInWithPassword).not.toHaveBeenCalled()
    expect(result.session).toBeNull()
    expect(result.user).toEqual(existingUser)
    expect(result.error).toBeInstanceOf(Error)
    expect(result.error.message).toContain('already registered')
    expect(auth.errorMessage.value).toBe('A user with the same email already exists. Please log in instead.')
    expect(auth.successMessage.value).toBe('')
  })

  it('passes emailRedirectTo when signing up', async () => {
    const supabaseMock = {
      auth: {
        signUp: vi.fn().mockResolvedValue({
          data: {
            session: { access_token: 'token', user: { id: 'user-2' } },
            user: { id: 'user-2' },
          },
          error: null,
        }),
        signInWithPassword: vi.fn(),
      },
    }

    const { useAuth } = await loadUseAuth({ supabaseMock })
    const auth = useAuth()

    await auth.signUpFan({
      fullName: 'Ticket Blitz Fan',
      email: 'fan@example.com',
      password: 'password-123',
    })

    const signUpPayload = supabaseMock.auth.signUp.mock.calls[0][0]

    expect(signUpPayload.options.emailRedirectTo).toContain('/sign-in')
  })
})
