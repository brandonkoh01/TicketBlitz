<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'

const props = defineProps({
  showHomeAction: {
    type: Boolean,
    default: false,
  },
})

const router = useRouter()
const authStore = useAuthStore()
const isSigningOut = ref(false)
const statusMessage = ref('')

const userLabel = computed(() => {
  const user = authStore.state.user
  const fullName = user?.user_metadata?.full_name

  if (typeof fullName === 'string' && fullName.trim()) {
    return fullName.trim()
  }

  const email = user?.email

  if (typeof email === 'string' && email.includes('@')) {
    return email.split('@')[0]
  }

  return 'Member'
})

const userRoleLabel = computed(() => {
  const role = authStore.state.user?.user_metadata?.role

  if (typeof role === 'string' && role.trim()) {
    return role.trim()
  }

  return 'Verified User'
})

async function handleSignOut() {
  if (isSigningOut.value) return

  isSigningOut.value = true
  statusMessage.value = ''

  const { error } = await authStore.signOut()

  if (error) {
    statusMessage.value = 'Unable to sign out. Please try again.'
    isSigningOut.value = false
    return
  }

  statusMessage.value = 'Signed out. Redirecting to home.'
  isSigningOut.value = false

  await router.push({ name: 'home' })
}
</script>

<template>
  <div class="flex items-center gap-2">
    <div class="hidden min-h-11 border-2 border-black bg-[var(--swiss-muted)] px-3 py-2 text-right sm:flex sm:flex-col sm:justify-center">
      <p class="text-[9px] font-black uppercase tracking-[0.16em] text-black/55">{{ userRoleLabel }}</p>
      <p class="max-w-[11rem] truncate text-[11px] font-black uppercase tracking-[0.14em]">{{ userLabel }}</p>
    </div>

    <RouterLink
      v-if="props.showHomeAction"
      to="/"
      class="inline-flex min-h-11 items-center justify-center border-2 border-black bg-white px-4 text-[11px] font-black uppercase tracking-[0.16em] transition duration-150 ease-linear hover:bg-black hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2"
    >
      Home
    </RouterLink>

    <button
      type="button"
      :disabled="isSigningOut"
      class="inline-flex min-h-11 items-center justify-center border-2 border-black bg-black px-4 text-[11px] font-black uppercase tracking-[0.16em] text-white transition duration-150 ease-linear hover:bg-[var(--swiss-accent)] hover:text-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-65"
      @click="handleSignOut"
    >
      {{ isSigningOut ? 'Signing Out' : 'Logout' }}
    </button>

    <p aria-live="polite" class="sr-only" role="status">{{ statusMessage }}</p>
  </div>
</template>
