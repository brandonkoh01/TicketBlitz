<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useScenarioReservation } from '@/composables/useScenarioReservation'

const route = useRoute()
const router = useRouter()
const reservationApi = useScenarioReservation()

const holdID = computed(() => String(route.params.holdID || '').trim())
const detail = ref(null)
const localError = ref('')
const isSubmitting = ref(false)

const canPay = computed(() => detail.value?.uiStatus === 'WAITLIST_OFFERED')

async function loadDetails() {
  localError.value = ''

  try {
    detail.value = await reservationApi.fetchWaitlistConfirm(holdID.value)

    if (detail.value?.uiStatus === 'CONFIRMED') {
      router.replace({
        name: 'booking-result',
        params: { holdID: holdID.value },
        query: { status: 'CONFIRMED' },
      })
      return
    }

    if (detail.value?.uiStatus === 'EXPIRED') {
      router.replace({
        name: 'booking-result',
        params: { holdID: holdID.value },
        query: { status: 'EXPIRED' },
      })
      return
    }

    if (detail.value?.uiStatus === 'WAITLIST_PENDING' && detail.value?.waitlist?.waitlistID) {
      router.replace({
        name: 'waitlist-status',
        params: { waitlistID: detail.value.waitlist.waitlistID },
      })
      return
    }

    if (detail.value?.uiStatus === 'PAID_PROCESSING' || detail.value?.uiStatus === 'PROCESSING') {
      router.replace({
        name: 'booking-pending',
        params: { holdID: holdID.value },
      })
    }
  } catch (error) {
    localError.value = error?.message || 'Unable to load waitlist confirmation details.'
  }
}

async function continuePayment() {
  localError.value = ''
  isSubmitting.value = true

  try {
    const response = await reservationApi.reserveConfirm({ holdID: holdID.value })

    if (response?.status === 'PAYMENT_PENDING') {
      router.push({
        name: 'booking-pending',
        params: { holdID: holdID.value },
      })
      return
    }

    if (response?.status === 'CONFIRMED') {
      router.push({
        name: 'booking-result',
        params: { holdID: holdID.value },
        query: { status: 'CONFIRMED' },
      })
      return
    }

    localError.value = 'Unexpected response while preparing payment.'
  } catch (error) {
    localError.value = error?.message || 'Unable to continue payment for waitlist offer.'
  } finally {
    isSubmitting.value = false
  }
}

onMounted(() => {
  loadDetails()
})
</script>

<template>
  <main class="min-h-screen bg-[var(--swiss-bg)] text-[var(--swiss-fg)]">
    <section class="border-b-4 border-black bg-white">
      <div class="mx-auto max-w-[1800px] px-6 py-8 md:px-10 md:py-10">
        <SectionLabel index="14." label="Waitlist Offer" />
        <h1 class="mt-8 text-[clamp(2.4rem,7vw,5.8rem)] font-black uppercase leading-[0.9] tracking-[-0.04em]">
          Confirm
          <br>
          Waitlist Hold
        </h1>
      </div>
    </section>

    <section class="border-b-4 border-black bg-[var(--swiss-muted)]">
      <div class="mx-auto max-w-[1800px] px-6 py-10 md:px-10 md:py-14">
        <article class="border-4 border-black bg-white p-6 md:p-8">
          <div class="grid gap-4 md:grid-cols-2">
            <div class="border-2 border-black bg-[var(--swiss-muted)] p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60">UI Status</p>
              <p class="mt-2 text-sm font-black uppercase tracking-[0.08em]">{{ detail?.uiStatus || 'LOADING' }}</p>
            </div>

            <div class="border-2 border-black bg-[var(--swiss-muted)] p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60">Hold Expiry</p>
              <p class="mt-2 text-sm font-black uppercase tracking-[0.08em]">{{ detail?.hold?.holdExpiry || 'N/A' }}</p>
            </div>

            <div class="border-2 border-black bg-[var(--swiss-muted)] p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60">Seat Category</p>
              <p class="mt-2 text-sm font-black uppercase tracking-[0.08em]">{{ detail?.hold?.seatCategory || 'N/A' }}</p>
            </div>

            <div class="border-2 border-black bg-[var(--swiss-muted)] p-4">
              <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/60">Amount</p>
              <p class="mt-2 text-sm font-black uppercase tracking-[0.08em]">
                {{ detail?.hold?.currency || 'SGD' }} {{ detail?.hold?.amount || 'N/A' }}
              </p>
            </div>
          </div>

          <p
            v-if="localError || reservationApi.errorMessage"
            class="mt-5 border-2 border-black bg-black px-4 py-3 text-xs font-black uppercase tracking-[0.14em] text-white"
          >
            {{ localError || reservationApi.errorMessage }}
          </p>

          <div class="mt-8 flex flex-col gap-3 sm:flex-row">
            <button
              type="button"
              class="inline-flex h-12 items-center justify-center border-2 border-black bg-black px-4 text-xs font-black uppercase tracking-[0.2em] text-white transition duration-150 ease-out hover:bg-[var(--swiss-accent)] hover:text-black disabled:cursor-not-allowed disabled:opacity-50"
              :disabled="!canPay || isSubmitting"
              @click="continuePayment"
            >
              {{ isSubmitting ? 'Preparing Payment' : 'Continue To Payment' }}
            </button>

            <RouterLink
              :to="{ name: 'booking-result', params: { holdID }, query: { status: detail?.uiStatus || 'PROCESSING' } }"
              class="inline-flex h-12 items-center justify-center border-2 border-black bg-white px-4 text-xs font-black uppercase tracking-[0.2em] transition duration-150 ease-out hover:bg-black hover:text-white"
            >
              View Status
            </RouterLink>
          </div>
        </article>
      </div>
    </section>
  </main>
</template>
