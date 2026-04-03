import { computed, reactive, readonly } from 'vue'
import { getSupabaseClient, hasSupabaseConfig } from '@/lib/supabaseClient'

const FAN_ROLE = 'fan'
const ORGANISER_ROLE = 'organiser'
const SUPPORTED_ROLES = new Set([FAN_ROLE, ORGANISER_ROLE])

function normalizeRole(role) {
  if (typeof role !== 'string') return FAN_ROLE

  const normalized = role.trim().toLowerCase()
  return SUPPORTED_ROLES.has(normalized) ? normalized : FAN_ROLE
}

function getUserRole(user) {
  return normalizeRole(user?.user_metadata?.role)
}

function getRoleHomePath(role) {
  return role === ORGANISER_ROLE ? '/organiser-dashboard' : '/my-tickets'
}

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
const currentRole = computed(() => getUserRole(state.user))
const isFan = computed(() => currentRole.value === FAN_ROLE)
const isOrganiser = computed(() => currentRole.value === ORGANISER_ROLE)
const roleHomePath = computed(() => getRoleHomePath(currentRole.value))

export function useAuthStore() {
  return {
    state: readonly(state),
    isAuthenticated,
    currentRole,
    isFan,
    isOrganiser,
    roleHomePath,
    authEnabled: hasSupabaseConfig,
    initializeAuthStore,
    setAuthSession,
    clearAuthSession,
    signOut,
  }
}
