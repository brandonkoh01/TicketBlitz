<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApiClient } from '@/composables/useApiClient'
import { useScenarioFlowStore } from '@/stores/scenarioFlowStore'

const route = useRoute()
const router = useRouter()
const api = useApiClient()
const flowStore = useScenarioFlowStore()

const holdID = computed(() => String(route.params.holdID || '').trim())
const resolved = ref(null)
const localError = ref('')

const displayStatus = computed(() => {
  const fallback = String(route.query.status || '').toUpperCase()
  return resolved.value?.uiStatus || fallback || 'PROCESSING'
})

const statusCopy = computed(() => {
  if (displayStatus.value === 'CONFIRMED') {
    return {
      heading: 'Booking Confirmed',
      message: 'Your payment was successful and your booking is confirmed.',
    }
  }

  if (displayStatus.value === 'FAILED_PAYMENT') {
    return {
      heading: 'Payment Failed',
      message: 'Payment did not complete. You can retry while your hold is active.',
    }
  }

  if (displayStatus.value === 'EXPIRED') {
    return {
      heading: 'Hold Expired',
      message: 'The payment window has expired for this hold.',
    }
  }

  return {
    heading: 'Booking Processing',
    message: 'Your booking is still processing. Return to pending view for live updates.',
  }
})

async function fetchStatus() {
  localError.value = ''

  try {
    resolved.value = await api.get(`/booking-status/${holdID.value}`, { includeUserHeader: false })

    if (resolved.value?.uiStatus === 'CONFIRMED') {
      flowStore.upsertConfirmedTicket({
        holdID: holdID.value,
        ticketID: resolved.value?.ticketID || null,
        seatNumber: resolved.value?.seatNumber || null,
        eventName: flowStore.state.reservation?.eventName || null,
        status: resolved.value?.uiStatus,
        updatedAt: resolved.value?.updatedAt || new Date().toISOString(),
      })
    }
  } catch (error) {
    localError.value = error?.message || 'Unable to load booking result.'
  }
}

onMounted(() => {
  fetchStatus()
})
</script>

<template>
  <main class="min-h-screen bg-[var(--swiss-bg)] text-[var(--swiss-fg)]">
    <section class="border-b-4 border-black bg-white">
      <div class="mx-auto max-w-[1800px] px-6 py-8 md:px-10 md:py-10">
        <SectionLabel index="12." label="Booking Result" />
        <h1 class="mt-8 text-[clamp(2.4rem,7vw,5.8rem)] font-black uppercase leading-[0.9] tracking-[-0.04em]">
          {{ statusCopy.heading }}
        </h1>
        <p class="mt-5 max-w-3xl text-sm uppercase leading-relaxed tracking-[0.04em] md:text-base">
          {{ statusCopy.message }}
        </p>
      </div>
    </section>

    <section class="border-b-4 border-black bg-[var(--swiss-muted)]">
      <div class="mx-auto max-w-[1800px] px-6 py-10 md:px-10 md:py-14">
        <article class="border-4 border-black bg-white p-6 md:p-8">
          <div class="grid gap-4 md:grid-cols-2">
            <div class="border-2 border-black bg-[var(--swiss-muted)] p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60">Hold ID</p>
              <p class="mt-2 break-all text-sm font-black uppercase tracking-[0.08em]">{{ holdID }}</p>
            </div>

            <div class="border-2 border-black bg-[var(--swiss-muted)] p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60">Status</p>
              <p class="mt-2 text-sm font-black uppercase tracking-[0.08em]">{{ displayStatus }}</p>
            </div>

            <div class="border-2 border-black bg-[var(--swiss-muted)] p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60">Ticket ID</p>
              <p class="mt-2 text-sm font-black uppercase tracking-[0.08em]">{{ resolved?.ticketID || 'N/A' }}</p>
            </div>

            <div class="border-2 border-black bg-[var(--swiss-muted)] p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60">Seat Number</p>
              <p class="mt-2 text-sm font-black uppercase tracking-[0.08em]">{{ resolved?.seatNumber || 'N/A' }}</p>
            </div>
          </div>

          <p
            v-if="localError"
            class="mt-5 border-2 border-black bg-black px-4 py-3 text-xs font-black uppercase tracking-[0.14em] text-white"
          >
            {{ localError }}
          </p>

          <div class="mt-8 flex flex-col gap-3 sm:flex-row">
            <RouterLink
              :to="{ name: 'booking-pending', params: { holdID } }"
              class="inline-flex h-12 items-center justify-center border-2 border-black bg-white px-4 text-xs font-black uppercase tracking-[0.2em] transition duration-150 ease-out hover:bg-black hover:text-white"
            >
              View Pending Status
            </RouterLink>

            <RouterLink
              to="/my-tickets"
              class="inline-flex h-12 items-center justify-center border-2 border-black bg-black px-4 text-xs font-black uppercase tracking-[0.2em] text-white transition duration-150 ease-out hover:bg-[var(--swiss-accent)] hover:text-black"
            >
              Go To My Tickets
            </RouterLink>
          </div>
        </article>
      </div>
    </section>
  </main>
</template>
