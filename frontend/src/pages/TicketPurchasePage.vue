<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useRoleNavigation } from '@/composables/useRoleNavigation'
import { useApiClient } from '@/composables/useApiClient'
import { useScenarioReservation } from '@/composables/useScenarioReservation'

const route = useRoute()
const router = useRouter()
const { primaryNavItems: navItems } = useRoleNavigation()
const api = useApiClient()
const reservation = useScenarioReservation()

const events = ref([])
const categories = ref([])

const selectedEventID = ref('')
const selectedSeatCategory = ref('')

const loadingEvents = ref(false)
const loadingCategories = ref(false)
const submitting = ref(false)
const localError = ref('')

const selectedEvent = computed(() => events.value.find((event) => event.event_id === selectedEventID.value) || null)
const selectedCategory = computed(
  () => categories.value.find((category) => category.category_code === selectedSeatCategory.value) || null
)

function getQueryValue(value) {
  if (Array.isArray(value)) {
    return typeof value[0] === 'string' ? value[0].trim() : ''
  }

  return typeof value === 'string' ? value.trim() : ''
}

function applyEventPrefill() {
  const requestedEventID = getQueryValue(route.query.eventID)
  if (!requestedEventID || events.value.length === 0) return false

  const hasMatch = events.value.some((event) => event.event_id === requestedEventID)
  if (!hasMatch) return false

  if (selectedEventID.value !== requestedEventID) {
    selectedEventID.value = requestedEventID
  }

  return true
}

function applyCategoryPrefill() {
  const requestedCategoryCode = getQueryValue(route.query.seatCategory)
  if (!requestedCategoryCode || categories.value.length === 0) return false

  const requestedUpper = requestedCategoryCode.toUpperCase()
  const matchedCategory = categories.value.find(
    (category) =>
      typeof category.category_code === 'string' && category.category_code.toUpperCase() === requestedUpper
  )

  if (!matchedCategory) return false

  if (selectedSeatCategory.value !== matchedCategory.category_code) {
    selectedSeatCategory.value = matchedCategory.category_code
  }

  return true
}

async function loadEvents() {
  loadingEvents.value = true
  localError.value = ''

  try {
    const payload = await api.get('/events', { includeUserHeader: false })
    events.value = payload?.events || []

    const hasAppliedPrefill = applyEventPrefill()
    if (!hasAppliedPrefill && !selectedEventID.value && events.value.length > 0) {
      selectedEventID.value = events.value[0].event_id
    }
  } catch (error) {
    localError.value = error?.message || 'Unable to load events.'
  } finally {
    loadingEvents.value = false
  }
}

async function loadCategories(eventID) {
  if (!eventID) return

  loadingCategories.value = true
  localError.value = ''

  try {
    const payload = await api.get(`/event/${eventID}/categories`, { includeUserHeader: false })
    categories.value = payload?.categories || []

    const hasAppliedPrefill = applyCategoryPrefill()
    if (!hasAppliedPrefill && !categories.value.some((category) => category.category_code === selectedSeatCategory.value)) {
      selectedSeatCategory.value = categories.value[0]?.category_code || ''
    }
  } catch (error) {
    localError.value = error?.message || 'Unable to load categories.'
    categories.value = []
    selectedSeatCategory.value = ''
  } finally {
    loadingCategories.value = false
  }
}

watch(selectedEventID, (eventID) => {
  loadCategories(eventID)
})

watch(
  () => [route.query.eventID, route.query.seatCategory],
  () => {
    const hasAppliedEvent = applyEventPrefill()
    if (!hasAppliedEvent && events.value.length > 0 && !events.value.some((event) => event.event_id === selectedEventID.value)) {
      selectedEventID.value = events.value[0]?.event_id || ''
    }

    const hasAppliedCategory = applyCategoryPrefill()
    if (!hasAppliedCategory && categories.value.length > 0 && !categories.value.some((category) => category.category_code === selectedSeatCategory.value)) {
      selectedSeatCategory.value = categories.value[0]?.category_code || ''
    }
  }
)

async function handleReserve() {
  localError.value = ''
  submitting.value = true

  try {
    if (!selectedEventID.value || !selectedSeatCategory.value) {
      throw new Error('Please select an event and seat category.')
    }

    const response = await reservation.reserve({
      eventID: selectedEventID.value,
      seatCategory: selectedSeatCategory.value,
      qty: 1,
    })

    if (response?.status === 'PAYMENT_PENDING' && response?.holdID) {
      await router.push({
        name: 'booking-pending',
        params: { holdID: response.holdID },
      })
      return
    }

    if (response?.status === 'WAITLISTED' && response?.waitlistID) {
      await router.push({
        name: 'waitlist-status',
        params: { waitlistID: response.waitlistID },
      })
      return
    }

    throw new Error('Unexpected reservation response.')
  } catch (error) {
    localError.value = error?.message || reservation.errorMessage.value || 'Unable to submit reservation.'
  } finally {
    submitting.value = false
  }
}

onMounted(() => {
  loadEvents()
})
</script>

<template>
  <main class="min-h-screen bg-[var(--swiss-bg)] text-[var(--swiss-fg)]">
    <header class="border-b-4 border-black bg-white">
      <div class="mx-auto flex max-w-[1800px] items-center justify-between gap-4 px-6 py-5 md:px-10">
        <RouterLink to="/" class="block focus-visible:outline-none">
          <p class="text-sm font-black uppercase tracking-[0.28em]">TicketBlitz</p>
          <p class="text-[10px] font-medium uppercase tracking-[0.22em] text-black/65">Scenario 01</p>
        </RouterLink>

        <nav class="hidden items-center gap-6 lg:flex">
          <component
            :is="item.to === '#' ? 'a' : 'RouterLink'"
            v-for="item in navItems"
            :key="item.label"
            :to="item.to !== '#' ? item.to : undefined"
            :href="item.to === '#' ? '#' : undefined"
            class="swiss-link-slide text-xs font-black uppercase tracking-[0.2em] focus-visible:outline-none"
            :data-alt="item.label"
          >
            <span>{{ item.label }}</span>
          </component>
        </nav>

        <UiButton to="/my-tickets" variant="secondary" class="min-w-[10rem]">My Tickets</UiButton>
      </div>
    </header>

    <section class="border-b-4 border-black bg-white">
      <div class="mx-auto max-w-[1800px] px-6 py-8 md:px-10 md:py-10">
        <SectionLabel index="06." label="Reserve Ticket" />
        <h1 class="mt-8 text-[clamp(2.4rem,7vw,5.6rem)] font-black uppercase leading-[0.9] tracking-[-0.04em]">
          Start Booking
        </h1>
      </div>
    </section>

    <section class="border-b-4 border-black">
      <div class="mx-auto grid max-w-[1800px] grid-cols-1 gap-0 lg:grid-cols-12">
        <div class="swiss-grid-pattern border-b-4 border-black p-6 md:p-10 lg:col-span-8 lg:border-b-0 lg:border-r-4 lg:p-14">
          <SectionLabel index="07." label="Reservation Input" />

          <form class="mt-8 space-y-6" @submit.prevent="handleReserve">
            <label class="block">
              <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.22em]">Event</span>
              <select
                v-model="selectedEventID"
                class="w-full border-2 border-black bg-white px-4 py-3 text-sm font-medium outline-none transition duration-200 ease-out focus:border-[var(--swiss-accent)]"
                :disabled="loadingEvents || events.length === 0"
              >
                <option value="" disabled>Select event</option>
                <option v-for="event in events" :key="event.event_id" :value="event.event_id">
                  {{ event.name }} ({{ event.event_code }})
                </option>
              </select>
            </label>

            <label class="block">
              <span class="mb-2 block text-[11px] font-black uppercase tracking-[0.22em]">Seat Category</span>
              <select
                v-model="selectedSeatCategory"
                class="w-full border-2 border-black bg-white px-4 py-3 text-sm font-medium outline-none transition duration-200 ease-out focus:border-[var(--swiss-accent)]"
                :disabled="loadingCategories || categories.length === 0"
              >
                <option value="" disabled>Select category</option>
                <option v-for="category in categories" :key="category.category_id" :value="category.category_code">
                  {{ category.category_code }} - {{ category.name }}
                </option>
              </select>
            </label>


            <p
              v-if="localError || reservation.errorMessage"
              class="border-2 border-black bg-black px-4 py-3 text-xs font-black uppercase tracking-[0.14em] text-white"
            >
              {{ localError || reservation.errorMessage }}
            </p>

            <div class="flex flex-col gap-4 border-t-2 border-black pt-6 sm:flex-row">
              <button
                type="submit"
                class="inline-flex h-14 w-full items-center justify-center border-2 border-black bg-black px-6 text-xs font-black uppercase tracking-[0.24em] text-white transition duration-200 ease-out hover:bg-[var(--swiss-accent)] hover:text-black disabled:cursor-not-allowed disabled:opacity-50 sm:w-auto sm:min-w-[12rem]"
                :disabled="submitting || !selectedEventID || !selectedSeatCategory"
              >
                {{ submitting ? 'Submitting' : 'Reserve Ticket' }}
              </button>
              <RouterLink
                to="/"
                class="inline-flex h-14 w-full items-center justify-center border-2 border-black bg-white px-6 text-xs font-black uppercase tracking-[0.24em] transition duration-200 ease-out hover:bg-black hover:text-white sm:w-auto sm:min-w-[12rem]"
              >
                Back
              </RouterLink>
            </div>
          </form>
        </div>

        <aside class="swiss-dots bg-[var(--swiss-muted)] p-6 md:p-10 lg:col-span-4 lg:p-14">
          <SectionLabel index="08." label="Live Summary" />

          <div class="mt-8 border-4 border-black bg-white p-6">
            <p class="text-xs font-bold uppercase tracking-[0.2em] text-black/70">Selected Event</p>
            <h2 class="mt-4 text-3xl font-black uppercase leading-[0.92] tracking-tight">
              {{ selectedEvent?.name || 'No Event Selected' }}
            </h2>

            <div class="mt-6 space-y-3 border-t-2 border-black pt-4 text-sm font-medium">
              <div class="flex items-center justify-between">
                <span>Event Code</span>
                <span class="font-black">{{ selectedEvent?.event_code || 'N/A' }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span>Status</span>
                <span class="font-black">{{ selectedEvent?.status || 'N/A' }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span>Seat Category</span>
                <span class="font-black">{{ selectedCategory?.category_code || 'N/A' }}</span>
              </div>
              <div class="flex items-center justify-between">
                <span>Current Price</span>
                <span class="font-black">
                  {{ selectedCategory?.currency || 'SGD' }} {{ selectedCategory?.current_price || 'N/A' }}
                </span>
              </div>
            </div>
          </div>

          <p class="mt-5 text-xs font-medium uppercase tracking-[0.14em] text-black/60">
            If sold out, this flow automatically moves to waitlist and starts position tracking.
          </p>
        </aside>
      </div>
    </section>
  </main>
</template>