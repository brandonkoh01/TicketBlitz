<script setup>
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AuthPageFrame from '@/components/auth/AuthPageFrame.vue'
import AuthFormField from '@/components/auth/AuthFormField.vue'
import AuthPasswordField from '@/components/auth/AuthPasswordField.vue'
import { useAuth } from '@/composables/useAuth'

const router = useRouter()
const route = useRoute()
const termsAccepted = ref(false)

function resolveRedirectPath() {
  const redirect = route.query.redirect

  if (typeof redirect !== 'string') return '/'
  if (!redirect.startsWith('/')) return '/'
  if (redirect.startsWith('//')) return '/'

  return redirect
}

const form = reactive({
  fullName: '',
  email: '',
  password: '',
})

const {
  isSubmitting,
  errorMessage,
  successMessage,
  resetMessages,
  signUpFan,
} = useAuth()

async function handleSignUp() {
  const fullName = form.fullName.trim()
  const email = form.email.trim().toLowerCase()

  if (!termsAccepted.value) {
    errorMessage.value = 'You must accept the terms before account creation.'
    return
  }

  const { session, error } = await signUpFan({
    fullName,
    email,
    password: form.password,
  })

  if (error) {
    return
  }

  if (session) {
    await router.push(resolveRedirectPath())
    return
  }

  const redirectPath = resolveRedirectPath()

  if (redirectPath === '/') {
    await router.push('/sign-in')
    return
  }

  await router.push({
    name: 'sign-in',
    query: {
      redirect: redirectPath,
    },
  })
}
</script>

<template>
  <AuthPageFrame top-action-label="Already a member? Sign In" top-action-to="/sign-in">
    <template #left>
      <div>
        <span class="inline-block border-2 border-black bg-black px-2 py-1 text-[9px] font-black uppercase tracking-[0.2em] text-white">
          001. System Access
        </span>
      </div>

      <h1 class="mt-7 text-[clamp(3.4rem,12vw,8rem)] font-black uppercase leading-[0.8] tracking-[-0.07em]">
        00.
        <br>
        Join
      </h1>

      <p class="mt-7 max-w-xl text-base font-bold uppercase leading-tight tracking-[0.03em] md:text-2xl md:tracking-tight">
        Initialize your global ticketing profile.
      </p>

      <div class="mt-16 hidden border-t-4 border-black pt-8 md:block">
        <div class="grid grid-cols-1 gap-5 lg:grid-cols-3">
          <article>
            <p class="text-[10px] font-black uppercase tracking-[0.14em]">01. Precision</p>
            <p class="mt-2 text-[11px] font-bold uppercase leading-tight text-black/60">
              Verified access to global arenas and stadiums.
            </p>
          </article>
          <article>
            <p class="text-[10px] font-black uppercase tracking-[0.14em]">02. Velocity</p>
            <p class="mt-2 text-[11px] font-bold uppercase leading-tight text-black/60">
              Instant digital delivery via decentralized vault.
            </p>
          </article>
          <article>
            <p class="text-[10px] font-black uppercase tracking-[0.14em]">03. Architecture</p>
            <p class="mt-2 text-[11px] font-bold uppercase leading-tight text-black/60">
              Engineered for high-volume seating logistics.
            </p>
          </article>
        </div>
      </div>
    </template>

    <template #right>
      <form class="mx-auto max-w-md space-y-8" @submit.prevent="handleSignUp">
        <AuthFormField
          id="sign-up-name"
          v-model="form.fullName"
          label="Full Name"
          placeholder="Enter Identity"
          autocomplete="name"
          required
          @input="resetMessages"
        />

        <AuthFormField
          id="sign-up-email"
          v-model="form.email"
          type="email"
          label="Email Address"
          placeholder="user@network.com"
          autocomplete="email"
          required
          @input="resetMessages"
        />

        <AuthPasswordField
          id="sign-up-password"
          v-model="form.password"
          label="Secure Password"
          placeholder="••••••••"
          autocomplete="new-password"
          required
          @input="resetMessages"
        />

        <label class="flex items-start gap-3">
          <input
            v-model="termsAccepted"
            type="checkbox"
            required
            class="mt-0.5 h-6 w-6 border-4 border-black bg-transparent accent-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2"
            @change="resetMessages"
          >
          <span class="text-[10px] font-medium uppercase leading-tight tracking-[0.08em]">
            I acknowledge the
            <a href="#" class="font-black underline">terms of service</a>
            and understand all ticket transactions are final and architecturally secured.
          </span>
        </label>

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
          class="inline-flex h-16 w-full items-center justify-center border-4 border-black bg-[var(--swiss-accent)] text-lg font-black uppercase tracking-[0.08em] transition duration-150 ease-linear hover:bg-black hover:text-[var(--swiss-accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {{ isSubmitting ? 'Creating Account' : 'Create Account' }}
        </button>
      </form>

      <div class="mx-auto mt-12 max-w-md border-t-4 border-black pt-7">
        <div class="flex items-center gap-3 text-[10px] font-black uppercase tracking-[0.12em] text-black/45">
          <UiMaterialIcon name="lock" class="text-sm" />
          <span>Encryption Active: AES-256 Bit Architecture</span>
        </div>
      </div>
    </template>
  </AuthPageFrame>
</template>
