<script setup>
import { computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useWaitlistTracking } from '@/composables/useWaitlistTracking'

const route = useRoute()
const router = useRouter()

const waitlistID = computed(() => String(route.params.waitlistID || '').trim())

const tracking = useWaitlistTracking(waitlistID.value, {
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
  tracking.start()
})
</script>

<template>
  <main class="min-h-screen bg-[var(--swiss-bg)] text-[var(--swiss-fg)]">
    <section class="border-b-4 border-black bg-white">
      <div class="mx-auto max-w-[1800px] px-6 py-8 md:px-10 md:py-10">
        <SectionLabel index="13." label="Waitlist Status" />
        <h1 class="mt-8 text-[clamp(2.4rem,7vw,5.8rem)] font-black uppercase leading-[0.9] tracking-[-0.04em]">
          Waitlist
          <br>
          Monitoring
        </h1>
      </div>
    </section>

    <section class="border-b-4 border-black bg-[var(--swiss-muted)]">
      <div class="mx-auto max-w-[1800px] px-6 py-10 md:px-10 md:py-14">
        <article class="border-4 border-black bg-white p-6 md:p-8">
          <div class="grid gap-4 md:grid-cols-2">
            <div class="border-2 border-black bg-[var(--swiss-muted)] p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60">Waitlist ID</p>
              <p class="mt-2 break-all text-sm font-black uppercase tracking-[0.08em]">{{ waitlistID }}</p>
            </div>

            <div class="border-2 border-black bg-[var(--swiss-muted)] p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60">Current Status</p>
              <p class="mt-2 text-sm font-black uppercase tracking-[0.08em]">{{ tracking.waitlist?.status || 'LOADING' }}</p>
            </div>

            <div class="border-2 border-black bg-[var(--swiss-muted)] p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60">Queue Position</p>
              <p class="mt-2 text-sm font-black uppercase tracking-[0.08em]">
                {{ tracking.waitlist?.position ?? 'N/A' }}
              </p>
            </div>

            <div class="border-2 border-black bg-[var(--swiss-muted)] p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60">Seat Category</p>
              <p class="mt-2 text-sm font-black uppercase tracking-[0.08em]">{{ tracking.waitlist?.seatCategory || 'N/A' }}</p>
            </div>
          </div>

          <p
            v-if="tracking.errorMessage"
            class="mt-5 border-2 border-black bg-black px-4 py-3 text-xs font-black uppercase tracking-[0.14em] text-white"
          >
            {{ tracking.errorMessage }}
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
