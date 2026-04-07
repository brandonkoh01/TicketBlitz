<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useWaitlistTracking } from '@/composables/useWaitlistTracking'

const route = useRoute()
const router = useRouter()

const waitlistID = computed(() => String(route.params.waitlistID || '').trim())

const { waitlist, errorMessage, start } = useWaitlistTracking(waitlistID.value, {
  onOffer: (payload) => {
    if (payload?.holdID) {
      router.replace({
        name: 'waitlist-confirm',
        params: { holdID: payload.holdID },
      })
    }
  },
})

onMounted(() => {
  start()
})
</script>

<template>
  <main class="min-h-screen bg-[var(--swiss-bg)] text-[var(--swiss-fg)]">
    <section class="border-b-4 border-black bg-white">
      <div class="mx-auto max-w-[1800px] px-6 py-8 md:px-10 md:py-10">
        <SectionLabel index="" label="Waitlist Status" />
        <h1 class="mt-8 text-[clamp(2.4rem,7vw,5.8rem)] font-black uppercase leading-[0.9] tracking-[-0.04em]">
          You are waitlisted.
        </h1>
      </div>
    </section>

    <section class="swiss-grid-pattern border-b-4 border-black bg-[var(--swiss-muted)]">
      <div class="mx-auto max-w-[1800px] px-6 py-10 md:px-10 md:py-14">
        <article class="border-4 border-black bg-white p-6 md:p-8">
          <div class="grid gap-4 md:grid-cols-2">
            <div class="border-2 border-black bg-white p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/75">Waitlist ID</p>
              <p class="mt-2 break-all text-base font-black uppercase tracking-[0.08em] md:text-lg">{{ waitlistID }}</p>
            </div>

            <div class="border-2 border-black bg-black p-4 text-white">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-white/70">Current Status</p>
              <p class="mt-2 text-base font-black uppercase tracking-[0.08em] md:text-lg">{{ waitlist?.status || 'WAITLISTED' }}</p>
            </div>

            <div class="border-2 border-black bg-[var(--swiss-accent)] p-4 text-black">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/70">Queue Position</p>
              <p class="mt-2 text-base font-black uppercase tracking-[0.08em] md:text-lg">
                {{ waitlist?.position ?? 'N/A' }}
              </p>
            </div>

            <div class="border-2 border-black bg-white p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/75">Seat Category</p>
              <p class="mt-2 text-base font-black uppercase tracking-[0.08em] md:text-lg">{{ waitlist?.seatCategory || 'N/A' }}</p>
            </div>
          </div>

          <p
            v-if="errorMessage"
            class="mt-5 border-2 border-black bg-black px-4 py-3 text-xs font-black uppercase tracking-[0.14em] text-white"
          >
            {{ errorMessage }}
          </p>

          <p class="mt-5 text-xs font-black uppercase tracking-[0.14em] text-black/65">
            Polling every 5 seconds. You will be redirected automatically when a hold is offered.
          </p>

          <div class="mt-6">
            <RouterLink
              to="/ticket-purchase"
              class="inline-flex h-12 items-center justify-center border-2 border-black bg-white px-4 text-xs font-black uppercase tracking-[0.2em] transition duration-150 ease-out hover:bg-black hover:text-white"
            >
              Back To Purchase
            </RouterLink>
          </div>
        </article>
      </div>
    </section>
  </main>
</template>
