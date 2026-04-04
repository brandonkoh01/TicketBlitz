<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/authStore'
import { useScenarioFlowStore } from '@/stores/scenarioFlowStore'
import { useScenarioReservation } from '@/composables/useScenarioReservation'
import { useBookingStatusPolling } from '@/composables/useBookingStatusPolling'
import { useHoldCountdown } from '@/composables/useHoldCountdown'
import { useStripePaymentElement } from '@/composables/useStripePaymentElement'

const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const flowStore = useScenarioFlowStore()
const reservationApi = useScenarioReservation()

const holdID = computed(() => String(route.params.holdID || '').trim())

const localError = ref('')
const localInfo = ref('')
const statusLabel = ref('PROCESSING')
const holdExpiry = ref('')
const clientSecret = ref('')
const paymentMountRef = ref(null)

const stripePayment = useStripePaymentElement()

const polling = useBookingStatusPolling(holdID.value, {
  onTerminal: (payload) => {
    const status = payload?.uiStatus || 'PROCESSING'
    if (status === 'CONFIRMED') {
      flowStore.upsertConfirmedTicket({
        holdID: holdID.value,
        ticketID: payload?.ticketID || null,
        seatNumber: payload?.seatNumber || null,
        eventName: flowStore.state.reservation?.eventName || null,
        status,
        updatedAt: payload?.updatedAt || new Date().toISOString(),
      })
    }

    router.replace({
      name: 'booking-result',
      params: { holdID: holdID.value },
      query: { status },
    })
  },
})

const countdown = useHoldCountdown(holdExpiry)

watch(
  () => polling.payload.value,
  (payload) => {
    if (!payload) return

    statusLabel.value = payload.uiStatus || 'PROCESSING'
    if (payload.holdExpiry) {
      holdExpiry.value = payload.holdExpiry
    }
  }
)

async function hydratePendingContext() {
  localError.value = ''
  localInfo.value = ''

  if (!holdID.value) {
    localError.value = 'Missing hold identifier.'
    return
  }

  const cached = flowStore.state.reservation
  if (cached?.holdID === holdID.value) {
    clientSecret.value = cached.clientSecret || ''
    holdExpiry.value = cached.holdExpiry || ''
    return
  }

  try {
    const response = await reservationApi.reserveConfirm({ holdID: holdID.value })

    if (response?.status === 'CONFIRMED') {
      router.replace({
        name: 'booking-result',
        params: { holdID: holdID.value },
        query: { status: 'CONFIRMED' },
      })
      return
    }

    clientSecret.value = response?.clientSecret || ''
    holdExpiry.value = response?.holdExpiry || ''
  } catch (error) {
    localError.value = error?.message || 'Unable to load payment context for this hold.'
  }
}

async function mountPaymentElement() {
  if (!clientSecret.value || !paymentMountRef.value) {
    return
  }

  try {
    await stripePayment.mount({
      clientSecret: clientSecret.value,
      mountNode: paymentMountRef.value,
    })
    localInfo.value = 'Payment form ready.'
  } catch (error) {
    localError.value = error?.message || 'Unable to initialize payment form.'
  }
}

async function handleConfirmPayment() {
  localError.value = ''

  try {
    const paymentIntent = await stripePayment.confirmPayment({
      returnUrl: `${window.location.origin}/booking/pending/${holdID.value}`,
    })

    if (paymentIntent?.status === 'succeeded') {
      localInfo.value = 'Payment submitted successfully. Waiting for booking confirmation...'
      await polling.pollOnce()
    }
  } catch (error) {
    localError.value = error?.message || 'Payment confirmation failed.'
  }
}

onMounted(async () => {
  if (!authStore.isAuthenticated.value) {
    return
  }

  await hydratePendingContext()
  await mountPaymentElement()
  polling.start()
})

onUnmounted(() => {
  polling.stop()
  stripePayment.unmount()
})
</script>

<template>
  <main class="min-h-screen bg-[var(--swiss-bg)] text-[var(--swiss-fg)]">
    <section class="border-b-4 border-black bg-white">
      <div class="mx-auto max-w-[1800px] px-6 py-8 md:px-10 md:py-10">
        <SectionLabel index="10." label="Booking Pending" />
        <h1 class="mt-8 text-[clamp(2.4rem,7vw,5.8rem)] font-black uppercase leading-[0.9] tracking-[-0.04em]">
          Payment
          <br>
          Processing
        </h1>
      </div>
    </section>

    <section class="border-b-4 border-black bg-[var(--swiss-muted)]">
      <div class="mx-auto grid max-w-[1800px] grid-cols-1 lg:grid-cols-12">
        <div class="swiss-grid-pattern border-b-4 border-black p-6 md:p-10 lg:col-span-7 lg:border-b-0 lg:border-r-4 lg:p-14">
          <p class="text-xs font-black uppercase tracking-[0.18em]">Hold ID</p>
          <p class="mt-2 break-all border-2 border-black bg-white px-3 py-2 text-xs font-bold tracking-[0.06em]">
            {{ holdID }}
          </p>

          <div class="mt-6 grid gap-4 md:grid-cols-3">
            <div class="border-2 border-black bg-white p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60">Current State</p>
              <p class="mt-2 text-lg font-black uppercase">{{ statusLabel }}</p>
            </div>

            <div class="border-2 border-black bg-white p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60">Hold Countdown</p>
              <p class="mt-2 text-lg font-black uppercase">{{ countdown.label }}</p>
            </div>

            <div class="border-2 border-black bg-white p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60">Polling</p>
              <p class="mt-2 text-lg font-black uppercase">{{ polling.isPolling ? 'ACTIVE' : 'PAUSED' }}</p>
            </div>
          </div>

          <p
            v-if="localError || polling.errorMessage"
            class="mt-6 border-2 border-black bg-black px-4 py-3 text-xs font-black uppercase tracking-[0.14em] text-white"
          >
            {{ localError || polling.errorMessage }}
          </p>

          <p
            v-if="localInfo"
            class="mt-6 border-2 border-black bg-[var(--swiss-accent)] px-4 py-3 text-xs font-black uppercase tracking-[0.14em]"
          >
            {{ localInfo }}
          </p>
        </div>

        <aside class="swiss-dots bg-white p-6 md:p-10 lg:col-span-5 lg:p-14">
          <SectionLabel index="11." label="Payment Element" />

          <div class="mt-6 border-4 border-black bg-[var(--swiss-muted)] p-4">
            <div ref="paymentMountRef" class="min-h-56 border-2 border-black bg-white p-4" />

            <button
              type="button"
              class="mt-4 inline-flex h-14 w-full items-center justify-center border-2 border-black bg-black px-6 text-xs font-black uppercase tracking-[0.24em] text-white transition duration-200 ease-out hover:bg-[var(--swiss-accent)] hover:text-black disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="!stripePayment.isReady || stripePayment.isSubmitting"
              @click="handleConfirmPayment"
            >
              {{ stripePayment.isSubmitting ? 'Submitting Payment' : 'Confirm Payment' }}
            </button>
          </div>

          <p class="mt-4 text-[11px] font-bold uppercase tracking-[0.15em] text-black/70">
            Keep this page open while booking status updates asynchronously.
          </p>

          <RouterLink
            :to="{ name: 'ticket-purchase' }"
            class="mt-6 inline-flex h-12 w-full items-center justify-center border-2 border-black bg-white px-4 text-xs font-black uppercase tracking-[0.2em] transition duration-150 ease-out hover:bg-black hover:text-white"
          >
            Back To Purchase
          </RouterLink>
        </aside>
      </div>
    </section>
  </main>
</template>
