<script setup>
import { reactive } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthPageFrame from '@/components/auth/AuthPageFrame.vue'
import AuthFormField from '@/components/auth/AuthFormField.vue'
import AuthPasswordField from '@/components/auth/AuthPasswordField.vue'
import { useAuth } from '@/composables/useAuth'

const router = useRouter()
const route = useRoute()

function resolveRedirectPath() {
  const redirect = route.query.redirect

  if (typeof redirect !== 'string') return '/'
  if (!redirect.startsWith('/')) return '/'
  if (redirect.startsWith('//')) return '/'

  return redirect
}

const form = reactive({
  email: '',
  password: '',
})

const {
  isSubmitting,
  errorMessage,
  successMessage,
  resetMessages,
  signInWithEmail,
} = useAuth()

async function handleSignIn() {
  const email = form.email.trim().toLowerCase()
  const password = form.password

  const { session, error } = await signInWithEmail({ email, password })

  if (error || !session) {
    return
  }

  successMessage.value = 'Access granted. Redirecting to TicketBlitz.'
  await router.push(resolveRedirectPath())
}
</script>

<template>
  <AuthPageFrame top-action-label="Need an account? Sign Up" top-action-to="/sign-up">
    <template #left>
      <div class="mb-7">
        <span class="inline-block border-2 border-black bg-black px-2 py-1 text-[9px] font-black uppercase tracking-[0.2em] text-white">
          System Status: Active
        </span>
      </div>

      <h1 class="text-[clamp(3.4rem,12vw,8rem)] font-black uppercase leading-[0.82] tracking-[-0.07em]">
        00.
        <br>
        Access
      </h1>

      <p class="mt-7 max-w-md text-base font-bold uppercase leading-tight tracking-[0.03em] md:text-2xl md:tracking-tight">
        Secure entry to the global ticketing infrastructure.
      </p>

      <div class="mt-12 max-w-sm space-y-4">
        <div class="flex items-center gap-4">
          <span class="border-b-2 border-black text-xs font-black uppercase tracking-[0.2em]">01</span>
          <span class="text-[11px] font-black uppercase tracking-[0.16em]">Authentication Protocol</span>
        </div>
        <div class="flex items-center gap-4 text-black/45">
          <span class="text-xs font-black uppercase tracking-[0.2em]">02</span>
          <span class="text-[11px] font-black uppercase tracking-[0.16em]">Encrypted Validation</span>
        </div>
        <div class="flex items-center gap-4 text-black/45">
          <span class="text-xs font-black uppercase tracking-[0.2em]">03</span>
          <span class="text-[11px] font-black uppercase tracking-[0.16em]">Session Establishment</span>
        </div>
      </div>
    </template>

    <template #right>
      <div class="relative border-4 border-black bg-white p-6 md:p-8">
        <div class="mb-8 flex items-end justify-between gap-4">
          <h2 class="text-2xl font-black uppercase tracking-[-0.03em] md:text-3xl">User Login</h2>
          <p class="text-[9px] font-bold uppercase tracking-[0.16em] text-black/45">Ref ID: TB_772</p>
        </div>

        <form class="space-y-7" @submit.prevent="handleSignIn">
          <AuthFormField
            id="sign-in-email"
            v-model="form.email"
            label="Email Address"
            type="email"
            placeholder="user@infrastructure.net"
            autocomplete="email"
            required
            @input="resetMessages"
          />

          <div class="space-y-2">

            <AuthPasswordField
              id="sign-in-password"
              v-model="form.password"
              label="Password"
              placeholder="••••••••••••"
              autocomplete="current-password"
              required
              @input="resetMessages"
            />
          </div>

          <p
            v-if="errorMessage"
            role="alert"
            class="border-2 border-black bg-black px-3 py-2 text-xs font-black uppercase tracking-[0.14em] text-white"
          >
            {{ errorMessage }}
          </p>

          <p
            v-if="successMessage"
            role="status"
            class="border-2 border-black bg-[var(--swiss-accent)] px-3 py-2 text-xs font-black uppercase tracking-[0.14em]"
          >
            {{ successMessage }}
          </p>

          <button
            type="submit"
            :disabled="isSubmitting"
            class="inline-flex h-16 w-full items-center justify-center gap-2 border-4 border-black bg-[var(--swiss-accent)] text-base font-black uppercase tracking-[0.08em] transition duration-150 ease-linear hover:bg-black hover:text-[var(--swiss-accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
          >
            <span>{{ isSubmitting ? 'Signing In' : 'Sign In' }}</span>
            <span class="text-lg">→</span>
          </button>

          <div class="pt-2 text-center">
            <p class="text-[10px] font-black uppercase tracking-[0.14em] text-black/45">Don't have an account?</p>
            <RouterLink
              to="/sign-up"
              class="mt-2 inline-block text-[11px] font-black uppercase tracking-[0.16em] underline decoration-2 transition duration-150 ease-linear hover:text-[var(--swiss-accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2"
            >
              Sign Up
            </RouterLink>
          </div>
        </form>
      </div>

      <div class="mt-5 flex flex-wrap items-center justify-between gap-4 px-1">
        <div class="flex items-center gap-4">
          <span class="text-[9px] font-bold uppercase tracking-[0.16em] text-black/45">V.2.4.0</span>
          <span class="text-[9px] font-bold uppercase tracking-[0.16em] text-black/45">Node: FRA-1</span>
        </div>

        <div class="flex items-center gap-1">
          <span class="h-1.5 w-1.5 bg-[var(--swiss-accent)]" />
          <span class="text-[9px] font-black uppercase tracking-[0.16em]">Network Optimal</span>
        </div>
      </div>
    </template>
  </AuthPageFrame>
</template>
