<script setup>
import { computed } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { useRoleNavigation } from '@/composables/useRoleNavigation'
import { useFanEventCatalog } from '@/composables/useFanEventCatalog'

const authStore = useAuthStore()
const isAuthenticated = computed(() => authStore.isAuthenticated.value)
const { primaryNavItems: navItems } = useRoleNavigation()

const {
  events,
  loading,
  refreshing,
  errorMessage,
  catalogMetrics,
  loadCatalog,
} = useFanEventCatalog()

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

function statusClass(eventRow) {
  if (eventRow.flashSaleActive) {
    return 'border-black bg-[var(--swiss-accent)] text-black'
  }

  if (eventRow.eventStatus === 'ACTIVE') {
    return 'border-black bg-white text-black'
  }

  return 'border-black bg-black text-white'
}

function statusLabel(eventRow) {
  if (eventRow.flashSaleActive) return 'Flash Sale Live'
  if (eventRow.eventStatus === 'ACTIVE') return 'Open'
  return 'Scheduled'
}

function priceLabel(eventRow) {
  if (!eventRow.minPrice && !eventRow.maxPrice) {
    return 'Pricing unavailable'
  }

  if (eventRow.minPrice && eventRow.maxPrice && eventRow.minPrice !== eventRow.maxPrice) {
    return `From ${eventRow.minPrice} to ${eventRow.maxPrice}`
  }

  return `From ${eventRow.minPrice || eventRow.maxPrice}`
}

function onRefresh() {
  void loadCatalog({ silent: false })
}
</script>

<template>
  <main class="min-h-screen bg-[var(--swiss-bg)] text-[var(--swiss-fg)]">
    <header class="border-b-4 border-black bg-white">
      <div class="mx-auto flex max-w-[1800px] items-center justify-between gap-4 px-6 py-5 md:px-10">
        <RouterLink to="/" class="block focus-visible:outline-none">
          <p class="text-sm font-black uppercase tracking-[0.28em]">TicketBlitz</p>
          <p class="text-[10px] font-medium uppercase tracking-[0.22em] text-black/65">Main Page 01</p>
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

        <div class="flex items-center gap-3">
          <button
            type="button"
            aria-label="Search"
            class="inline-flex h-11 w-11 items-center justify-center border-2 border-black text-lg font-black transition duration-200 ease-out hover:bg-black hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2"
          >
            ⌕
          </button>

          <AuthSessionControls v-if="isAuthenticated" />
          <UiButton v-else to="/sign-in" variant="primary" class="min-w-[9rem]">Login</UiButton>
        </div>
      </div>
    </header>

    <section class="border-b-4 border-black bg-white">
      <div class="mx-auto max-w-[1800px] px-6 py-8 md:px-10 md:py-10">
        <SectionLabel index="10." label="Events" />
        <div class="mt-8 flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <h1 class="text-[clamp(2.4rem,8vw,6rem)] font-black uppercase leading-[0.88] tracking-[-0.05em]">
              Event
              <br>
              Catalog
            </h1>
            <p class="mt-5 max-w-3xl text-sm uppercase leading-relaxed tracking-[0.04em] md:text-base">
              Explore upcoming shows and monitor live Scenario 2 flash sale price movement in one place.
            </p>
          </div>

          <button
            type="button"
            class="inline-flex h-12 items-center justify-center border-2 border-black bg-white px-5 text-xs font-black uppercase tracking-[0.2em] transition duration-200 ease-out hover:bg-black hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="loading || refreshing"
            @click="onRefresh"
          >
            {{ loading || refreshing ? 'Refreshing' : 'Refresh Catalog' }}
          </button>
        </div>

        <div class="mt-8 grid gap-4 md:grid-cols-3">
          <MetricCard
            v-for="metric in catalogMetrics"
            :key="metric.label"
            :label="metric.label"
            :value="metric.value"
          />
        </div>
      </div>
    </section>

    <section class="border-b-4 border-black bg-[var(--swiss-muted)]">
      <div class="mx-auto max-w-[1800px] px-6 py-10 md:px-10 md:py-14">
        <div v-if="errorMessage" class="border-2 border-black bg-rose-100 px-4 py-4 text-sm font-bold uppercase tracking-[0.06em] text-black">
          {{ errorMessage }}
        </div>

        <div
          v-else-if="loading"
          class="grid gap-5 md:grid-cols-2 xl:grid-cols-3"
        >
          <article
            v-for="placeholder in 6"
            :key="placeholder"
            class="animate-pulse border-4 border-black bg-white p-6"
          >
            <div class="h-5 w-28 bg-[var(--swiss-muted)]" />
            <div class="mt-5 h-8 w-4/5 bg-[var(--swiss-muted)]" />
            <div class="mt-3 h-8 w-3/5 bg-[var(--swiss-muted)]" />
            <div class="mt-6 h-4 w-2/3 bg-[var(--swiss-muted)]" />
            <div class="mt-8 h-10 w-40 border-2 border-black bg-[var(--swiss-muted)]" />
          </article>
        </div>

        <div
          v-else-if="events.length === 0"
          class="border-4 border-black bg-white p-8 md:p-12"
        >
          <p class="text-xs font-black uppercase tracking-[0.2em] text-black/65">No events found</p>
          <h2 class="mt-3 text-4xl font-black uppercase leading-[0.9] tracking-tight">Catalog Empty</h2>
          <p class="mt-5 max-w-xl text-sm uppercase leading-relaxed tracking-[0.04em]">
            No active events were returned by the backend. Try refreshing the catalog in a moment.
          </p>
        </div>

        <div v-else class="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
          <article
            v-for="eventRow in events"
            :key="eventRow.id"
            class="group border-4 border-black bg-white p-6 transition duration-200 ease-out hover:-translate-y-px hover:bg-[var(--swiss-accent)]"
          >
            <div class="mb-5 flex items-center justify-between gap-3">
              <span
                class="border-2 px-3 py-1 text-[11px] font-black uppercase tracking-[0.2em]"
                :class="statusClass(eventRow)"
              >
                {{ statusLabel(eventRow) }}
              </span>
              <span class="text-[10px] font-black uppercase tracking-[0.2em] text-black/70">
                {{ eventRow.code }}
              </span>
            </div>

            <h3 class="text-2xl font-black uppercase leading-tight tracking-tight">{{ eventRow.name }}</h3>
            <p class="mt-4 text-xs font-bold uppercase tracking-[0.12em] text-black/75">{{ eventRow.venue }}</p>
            <p class="mt-1 text-xs font-bold uppercase tracking-[0.12em] text-black/60">{{ eventRow.eventDateLabel }}</p>

            <div class="mt-6 border-t-2 border-black pt-4">
              <p class="text-xs font-black uppercase tracking-[0.16em]">{{ priceLabel(eventRow) }}</p>
              <p class="mt-2 text-[11px] font-bold uppercase tracking-[0.14em] text-black/70">
                {{ eventRow.soldOutCount }} sold out / {{ eventRow.categoryCount }} categories
              </p>
            </div>

            <RouterLink
              :to="`/events/${eventRow.id}`"
              class="mt-8 inline-flex h-11 items-center justify-center border-2 border-black bg-white px-4 text-xs font-black uppercase tracking-[0.2em] transition duration-200 ease-out hover:bg-black hover:text-white"
            >
              View Details
            </RouterLink>
          </article>
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
