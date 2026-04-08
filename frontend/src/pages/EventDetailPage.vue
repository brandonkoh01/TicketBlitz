<script setup>
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useFanEventDetailScenario2 } from '@/composables/useFanEventDetailScenario2'

const route = useRoute()
const router = useRouter()

const eventID = computed(() =>
  typeof route.params.eventID === 'string' ? route.params.eventID : ''
)

const {
  eventSummary,
  flashSale,
  categoryRows,
  detailMetrics,
  loading,
  refreshing,
  errorMessage,
  refreshDetail,
} = useFanEventDetailScenario2(eventID)

const footerGroups = [
  {
    title: 'Navigation',
    links: ['Press Kit', 'Privacy Policy', 'Terms of Service'],
  },
  {
    title: 'Connect',
    links: ['Share', 'Language', 'Mail'],
  },
]

function onRefresh() {
  void refreshDetail({ silent: false })
}

async function onSelectCategory(category) {
  if (!eventID.value || !category?.code) return

  await router.push({
    name: 'ticket-purchase',
    query: {
      eventID: eventID.value,
      seatCategory: category.code,
    },
  })
}
</script>

<template>
  <main class="min-h-screen bg-[var(--swiss-bg)] text-[var(--swiss-fg)]">
    <AppTopNav page-label="Main Page 01" />

    <section class="border-b-4 border-black bg-white">
      <div class="mx-auto max-w-[1800px] px-6 py-8 md:px-10 md:py-10">
        <div class="flex items-center justify-between gap-3">
          <SectionLabel index="11." label="Event Detail" />
          <button
            type="button"
            class="inline-flex h-11 items-center justify-center border-2 border-black bg-white px-4 text-xs font-black uppercase tracking-[0.2em] transition duration-200 ease-out hover:bg-black hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="loading || refreshing"
            @click="onRefresh"
          >
            {{ loading || refreshing ? 'Refreshing' : 'Refresh Live Data' }}
          </button>
        </div>

        <div class="mt-8">
          <RouterLink
            to="/events"
            class="inline-flex items-center border-2 border-black bg-white px-3 py-2 text-[11px] font-black uppercase tracking-[0.2em] transition duration-200 ease-out hover:bg-black hover:text-white"
          >
            ← Back to Events
          </RouterLink>
        </div>

        <div v-if="errorMessage" class="mt-8 border-2 border-black bg-rose-100 px-4 py-4 text-sm font-bold uppercase tracking-[0.06em] text-black">
          {{ errorMessage }}
        </div>

        <div
          v-else-if="loading && !eventSummary"
          class="mt-8 animate-pulse border-4 border-black bg-[var(--swiss-muted)] p-8"
        >
          <div class="h-7 w-56 bg-white" />
          <div class="mt-4 h-12 w-3/4 bg-white" />
          <div class="mt-4 h-5 w-2/3 bg-white" />
        </div>

        <div
          v-else-if="eventSummary"
          class="mt-8 grid gap-8 xl:grid-cols-12"
        >
          <article class="border-4 border-black bg-white p-6 md:p-8 xl:col-span-8">
            <div class="flex flex-wrap items-center gap-3">
              <span class="border-2 border-black bg-white px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em]">{{ eventSummary.code }}</span>
              <span class="border-2 border-black bg-[var(--swiss-muted)] px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em]">{{ eventSummary.status }}</span>
              <span
                v-if="flashSale.isActive"
                class="border-2 border-black bg-[var(--swiss-accent)] px-3 py-1 text-[10px] font-black uppercase tracking-[0.2em]"
              >
                Flash Sale Active
              </span>
            </div>

            <h1 class="mt-6 text-[clamp(2rem,5vw,4.2rem)] font-black uppercase leading-[0.9] tracking-[-0.04em]">{{ eventSummary.name }}</h1>
            <p class="mt-4 text-sm font-black uppercase tracking-[0.08em]">{{ eventSummary.venue }}</p>
            <p class="mt-2 text-xs font-bold uppercase tracking-[0.1em] text-black/70">{{ eventSummary.eventDateLabel }}</p>

            <div class="mt-8 grid gap-4 md:grid-cols-3">
              <MetricCard
                v-for="metric in detailMetrics"
                :key="metric.label"
                :label="metric.label"
                :value="metric.value"
              />
            </div>

            <div v-if="flashSale.isActive" class="mt-8 border-4 border-black bg-[var(--swiss-accent)] p-5">
              <p class="text-xs font-black uppercase tracking-[0.2em]">Live Scenario 2 Sale</p>
              <div class="mt-4 grid gap-4 md:grid-cols-3">
                <div class="border-2 border-black bg-white p-3">
                  <p class="text-[10px] font-black uppercase tracking-[0.18em] text-black/60">Discount</p>
                  <p class="mt-2 text-lg font-black">{{ flashSale.discountPercentage || 'N/A' }}%</p>
                </div>
                <div class="border-2 border-black bg-white p-3">
                  <p class="text-[10px] font-black uppercase tracking-[0.18em] text-black/60">Starts</p>
                  <p class="mt-2 text-xs font-black uppercase tracking-[0.08em]">{{ flashSale.startsAtLabel }}</p>
                </div>
                <div class="border-2 border-black bg-white p-3">
                  <p class="text-[10px] font-black uppercase tracking-[0.18em] text-black/60">Ends</p>
                  <p class="mt-2 text-xs font-black uppercase tracking-[0.08em]">{{ flashSale.expiresAtLabel }}</p>
                </div>
              </div>
            </div>

            <div class="mt-8 border-t-2 border-black pt-5">
              <p class="text-xs font-black uppercase tracking-[0.2em]">Booking Window</p>
              <p class="mt-3 text-xs font-bold uppercase tracking-[0.08em] text-black/80">Opens: {{ eventSummary.bookingOpenLabel }}</p>
              <p class="mt-1 text-xs font-bold uppercase tracking-[0.08em] text-black/80">Closes: {{ eventSummary.bookingCloseLabel }}</p>
            </div>
          </article>

          <aside class="border-4 border-black bg-white p-6 xl:col-span-4">
            <p class="text-xs font-black uppercase tracking-[0.22em]">Category Pricing</p>

            <div class="mt-5 space-y-4">
              <CategoryPricingCard
                v-for="category in categoryRows"
                :key="category.id"
                :category="category"
                :selectable="Boolean(eventSummary?.id && category.code)"
                @select="onSelectCategory"
              />
            </div>

            <p class="mt-6 border-t-2 border-black pt-4 text-[10px] font-black uppercase tracking-[0.16em] text-black/60">
              Select a category to continue booking with prefilled values.
            </p>
          </aside>
        </div>
      </div>
    </section>

    <footer class="bg-black px-6 py-14 text-white md:px-10 md:py-20">
      <div class="mx-auto grid max-w-[1800px] gap-10 lg:grid-cols-12">
        <div class="lg:col-span-7">
          <p class="text-xs font-black uppercase tracking-[0.3em] text-[var(--swiss-accent)]">05. TicketBlitz International</p>
          <h2 class="mt-5 text-5xl font-black uppercase leading-[0.88] tracking-[-0.04em] md:text-7xl">TicketBlitz</h2>
          <p class="mt-6 max-w-xl text-sm leading-relaxed text-white/80 md:text-base">
            The world's fastest ticketing platform for high-demand experiences.
          </p>
        </div>

        <div class="grid gap-8 sm:grid-cols-2 lg:col-span-5">
          <FooterLinkGroup
            v-for="group in footerGroups"
            :key="group.title"
            :title="group.title"
            :links="group.links"
          />
        </div>

        <p class="border-t-2 border-white/20 pt-6 text-[11px] font-medium uppercase tracking-[0.2em] text-white/70 lg:col-span-12">
          ©2026 TicketBlitz International
        </p>
      </div>
    </footer>
  </main>
</template>
