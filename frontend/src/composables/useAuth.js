import { ref } from 'vue'
import { getSupabaseClient, hasSupabaseConfig } from '@/lib/supabaseClient'
import { useAuthStore } from '@/stores/authStore'

const FULL_NAME_MIN_LENGTH = 1
const FULL_NAME_MAX_LENGTH = 100

function normalizeErrorMessage(error) {
  const fallbackMessage = 'Authentication failed. Please try again.'

  if (!error) return fallbackMessage

  const message = typeof error === 'string' ? error : error.message
  if (!message) return fallbackMessage

  const normalizedMessage = message.toLowerCase()

  if (
    normalizedMessage.includes('already registered') ||
    normalizedMessage.includes('already exists') ||
    normalizedMessage.includes('already been registered')
  ) {
    return 'A user with the same email already exists. Please log in instead.'
  }

  if (
    normalizedMessage.includes('invalid login credentials') ||
    normalizedMessage.includes('invalid email or password')
  ) {
    return 'Email or password is wrong.'
  }

  return message
}

function buildSignInRedirectUrl() {
  if (typeof window === 'undefined' || !window.location?.origin) {
    return undefined
  }

  return new URL('/sign-in', window.location.origin).toString()
}

function validateSignUpInput({ fullName, email }) {
  const trimmedFullName = fullName.trim()

  if (trimmedFullName.length < FULL_NAME_MIN_LENGTH || trimmedFullName.length > FULL_NAME_MAX_LENGTH) {
    return `Full name must be between ${FULL_NAME_MIN_LENGTH} and ${FULL_NAME_MAX_LENGTH} characters.`
  }

  if (!email || email.startsWith('@') || !email.includes('@')) {
    return 'Please provide a valid email address.'
  }

  return null
}

function isObfuscatedDuplicateSignUpResponse({ signUpData, normalizedEmail }) {
  const user = signUpData?.user

  if (signUpData?.session || !user) {
    return false
  }

  const userEmail = typeof user.email === 'string' ? user.email.trim().toLowerCase() : ''

  if (!userEmail || userEmail !== normalizedEmail) {
    return false
  }

  return Array.isArray(user.identities) && user.identities.length === 0
}

export function useAuth() {
  const authStore = useAuthStore()
  const isSubmitting = ref(false)
  const errorMessage = ref('')
  const successMessage = ref('')

  function resetMessages() {
    errorMessage.value = ''
    successMessage.value = ''
  }

  async function signInWithEmail({ email, password }) {
    resetMessages()

    if (!hasSupabaseConfig) {
      errorMessage.value = 'Missing Supabase configuration for authentication.'
      return { session: null, user: null, error: new Error(errorMessage.value) }
    }

    isSubmitting.value = true

    try {
      const supabase = getSupabaseClient()
      const { data, error } = await supabase.auth.signInWithPassword({ email, password })

      if (error) {
        errorMessage.value = normalizeErrorMessage(error)
      } else {
        authStore.setAuthSession(data?.session ?? null)
      }

      return {
        session: data?.session ?? null,
        user: data?.user ?? null,
        error,
      }
    } catch (error) {
      errorMessage.value = normalizeErrorMessage(error)
      return { session: null, user: null, error }
    } finally {
      isSubmitting.value = false
    }
  }

  async function signUpFan({ fullName, email, password }) {
    resetMessages()

    if (!hasSupabaseConfig) {
      errorMessage.value = 'Missing Supabase configuration for authentication.'
      return {
        session: null,
        user: null,
        error: new Error(errorMessage.value),
      }
    }

    const normalizedFullName = fullName.trim()
    const normalizedEmail = email.trim().toLowerCase()
    const validationMessage = validateSignUpInput({
      fullName: normalizedFullName,
      email: normalizedEmail,
    })

    if (validationMessage) {
      errorMessage.value = validationMessage
      return {
        session: null,
        user: null,
        error: new Error(validationMessage),
      }
    }

    isSubmitting.value = true

    try {
      const supabase = getSupabaseClient()
      const emailRedirectTo = buildSignInRedirectUrl()
      const { data, error } = await supabase.auth.signUp({
        email: normalizedEmail,
        password,
        options: {
          ...(emailRedirectTo ? { emailRedirectTo } : {}),
          data: {
            full_name: normalizedFullName,
            role: 'fan',
          },
        },
      })

      if (error) {
        errorMessage.value = normalizeErrorMessage(error)
        return {
          session: null,
          user: null,
          error,
        }
      }

      if (data?.session) {
        authStore.setAuthSession(data.session)
        successMessage.value = 'Account created and authenticated.'
        return {
          session: data.session,
          user: data.user,
          error: null,
        }
      }

      if (isObfuscatedDuplicateSignUpResponse({ signUpData: data, normalizedEmail })) {
        const duplicateSignUpError = new Error('User already registered')
        errorMessage.value = normalizeErrorMessage(duplicateSignUpError)
        return {
          session: null,
          user: data?.user ?? null,
          error: duplicateSignUpError,
        }
      }

      // The project has fan auto-confirm configured, but some auth settings can still return no session.
      const signInResult = await supabase.auth.signInWithPassword({
        email: normalizedEmail,
        password,
      })

      if (signInResult.error) {
        errorMessage.value = normalizeErrorMessage(signInResult.error)
        return {
          session: null,
          user: data?.user ?? null,
          error: signInResult.error,
        }
      }

      successMessage.value = 'Account created and authenticated.'
      authStore.setAuthSession(signInResult.data?.session ?? null)
      return {
        session: signInResult.data?.session ?? null,
        user: signInResult.data?.user ?? data?.user ?? null,
        error: null,
      }
    } catch (error) {
      errorMessage.value = normalizeErrorMessage(error)
      return {
        session: null,
        user: null,
        error,
      }
    } finally {
      isSubmitting.value = false
    }
  }

  return {
    isSubmitting,
    errorMessage,
    successMessage,
    resetMessages,
    signInWithEmail,
    signUpFan,
  }
}
