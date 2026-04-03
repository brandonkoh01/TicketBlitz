import { computed, reactive, readonly } from 'vue'
import { getSupabaseClient, hasSupabaseConfig } from '@/lib/supabaseClient'

const state = reactive({
  session: null,
  user: null,
  isReady: false,
  initError: null,
})

let initPromise = null
let authSubscription = null

function setAuthSession(session) {
  state.session = session ?? null
  state.user = session?.user ?? null
}

function clearAuthSession() {
  state.session = null
  state.user = null
}

function ensureAuthListener() {
  if (!hasSupabaseConfig || authSubscription) return

  const supabase = getSupabaseClient()
  const { data } = supabase.auth.onAuthStateChange((_event, session) => {
    setAuthSession(session)
  })

  authSubscription = data.subscription
}

async function initializeAuthStore() {
  if (initPromise) return initPromise

  initPromise = (async () => {
    state.initError = null

    if (!hasSupabaseConfig) {
      clearAuthSession()
      state.isReady = true
      return
    }

    try {
      const supabase = getSupabaseClient()
      const { data, error } = await supabase.auth.getSession()

      if (error) throw error

      setAuthSession(data?.session ?? null)
      ensureAuthListener()
    } catch (error) {
      state.initError = error
      clearAuthSession()
    } finally {
      state.isReady = true
    }
  })()

  return initPromise
}

async function signOut() {
  if (!hasSupabaseConfig) {
    clearAuthSession()
    return { error: null }
  }

  try {
    const supabase = getSupabaseClient()
    const { error } = await supabase.auth.signOut()

    if (!error) {
      clearAuthSession()
    }

    return { error }
  } catch (error) {
    return { error }
  }
}

const isAuthenticated = computed(() => Boolean(state.session))

export function useAuthStore() {
  return {
    state: readonly(state),
    isAuthenticated,
    authEnabled: hasSupabaseConfig,
    initializeAuthStore,
    setAuthSession,
    clearAuthSession,
    signOut,
  }
}
