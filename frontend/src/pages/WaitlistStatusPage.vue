<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useApiClient } from '@/composables/useApiClient'
import { useWaitlistTracking } from '@/composables/useWaitlistTracking'
import { useScenarioFlowStore } from '@/stores/scenarioFlowStore'

const route = useRoute()
const router = useRouter()
const api = useApiClient()
const flowStore = useScenarioFlowStore()

const waitlistID = computed(() => String(route.params.waitlistID || '').trim())
const isLeaving = ref(false)
const leaveError = ref('')
const isLeaveModalOpen = ref(false)

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

async function handleLeaveWaitlist() {
  if (isLeaving.value || isLeaveModalOpen.value) return

  isLeaveModalOpen.value = true
}

function closeLeaveModal() {
  if (isLeaving.value) return
  isLeaveModalOpen.value = false
}

function normalizeContextValue(value) {
  return typeof value === 'string' ? value.trim() : ''
}

function buildTicketPurchaseQuery() {
  const liveEventID = normalizeContextValue(waitlist.value?.eventID)
  const liveSeatCategory = normalizeContextValue(waitlist.value?.seatCategory)
  const storedEventID = normalizeContextValue(flowStore.state.waitlist?.eventID)
  const storedSeatCategory = normalizeContextValue(flowStore.state.waitlist?.seatCategory)

  const eventID = liveEventID || storedEventID
  const seatCategory = liveSeatCategory || storedSeatCategory

  const query = {}
  if (eventID) {
    query.eventID = eventID
  }
  if (seatCategory) {
    query.seatCategory = seatCategory
  }

  return Object.keys(query).length > 0 ? query : null
}

async function confirmLeaveWaitlist() {
  if (isLeaving.value) return

  leaveError.value = ''
  isLeaving.value = true

  try {
    await api.del(`/waitlist/leave/${waitlistID.value}`)
    isLeaveModalOpen.value = false

    const query = buildTicketPurchaseQuery()
    await router.replace(
      query
        ? {
            name: 'ticket-purchase',
            query,
          }
        : { name: 'ticket-purchase' }
    )
  } catch (error) {
    leaveError.value = error?.message || 'Unable to leave waitlist right now.'
  } finally {
    isLeaving.value = false
  }
}
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
            v-if="leaveError || errorMessage"
            class="mt-5 border-2 border-black bg-black px-4 py-3 text-xs font-black uppercase tracking-[0.14em] text-white"
          >
            {{ leaveError || errorMessage }}
          </p>

          <p class="mt-5 text-xs font-black uppercase tracking-[0.14em] text-black/65">
            Polling every 5 seconds. You will be redirected automatically when a hold is offered.
          </p>

          <div class="mt-6">
            <UiButton
              as="button"
              variant="secondary"
              :disabled="isLeaving"
              class="h-12 min-w-[14rem]"
              @click="handleLeaveWaitlist"
            >
              {{ isLeaving ? 'Leaving...' : 'Leave Waitlist' }}
            </UiButton>
          </div>
        </article>
      </div>
    </section>

    <section
      v-if="isLeaveModalOpen"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/55 px-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby="leave-waitlist-title"
      aria-describedby="leave-waitlist-description"
    >
      <article class="w-full max-w-xl border-4 border-black bg-white p-6 shadow-[10px_10px_0_0_#000] md:p-8">
        <p class="text-[10px] font-black uppercase tracking-[0.2em] text-black/70">Confirm Action</p>
        <h2
          id="leave-waitlist-title"
          class="mt-3 text-[clamp(1.6rem,4vw,2.3rem)] font-black uppercase leading-[0.95] tracking-[-0.03em]"
        >
          Leave waitlist queue?
        </h2>
        <p
          id="leave-waitlist-description"
          class="mt-4 border-2 border-black bg-[var(--swiss-muted)] px-4 py-3 text-xs font-black uppercase tracking-[0.14em] text-black/75"
        >
          This action cannot be undone.
        </p>

        <div class="mt-6 flex flex-col gap-3 sm:flex-row sm:justify-end">
          <UiButton
            as="button"
            variant="secondary"
            class="h-12 min-w-[10rem]"
            :disabled="isLeaving"
            @click="closeLeaveModal"
          >
            Cancel
          </UiButton>
          <UiButton
            as="button"
            class="h-12 min-w-[12rem]"
            :disabled="isLeaving"
            @click="confirmLeaveWaitlist"
          >
            {{ isLeaving ? 'Leaving...' : 'Yes, Leave Waitlist' }}
          </UiButton>
        </div>
      </article>
    </section>
  </main>
</template>
