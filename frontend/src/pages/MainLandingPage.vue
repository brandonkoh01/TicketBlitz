<script setup>
import { computed } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { useRoleNavigation } from '@/composables/useRoleNavigation'

const authStore = useAuthStore()
const isAuthenticated = computed(() => authStore.isAuthenticated.value)
const { primaryNavItems: navItems } = useRoleNavigation()

const heroMetrics = [
  { label: 'Global Tickets Sold', value: '2.5M+' },
  { label: 'Partner Venues', value: '120' },
  { label: 'Verified Artists', value: '500+' },
]

const featureEvent = {
  name: 'Neon Overdrive Tour',
  city: 'Tokyo',
  date: 'Nov 19 2026',
  copy: 'Flash-demand access architecture tuned for global premiere nights and large-volume synchronized drops.',
}

const events = [
  {
    title: 'Synthwave Night',
    dateLocation: 'Nov 24 - Berlin',
    price: '$89.00',
    status: 'Sold Out',
    action: 'Details',
  },
  {
    title: 'Rock Revival 2026',
    dateLocation: 'Dec 02 - London',
    price: '$125.00',
    status: 'Low Stock',
    action: 'Buy Now',
    actionTo: '/ticket-purchase',
  },
  {
    title: 'Jazz Fusion Fest',
    dateLocation: 'Dec 15 - NYC',
    price: '$65.00',
    status: 'Available',
    action: 'Details',
  },
]

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

    <section class="border-b-4 border-black">
      <div class="mx-auto grid max-w-[1800px] grid-cols-1 lg:grid-cols-12">
        <div class="swiss-grid-pattern border-b-4 border-black p-6 md:p-10 lg:col-span-8 lg:border-b-0 lg:border-r-4 lg:p-14">
          <SectionLabel index="01." label="Hero" />
          <h1 class="mt-8 max-w-5xl text-[clamp(3rem,10vw,9.6rem)] font-black uppercase leading-[0.88] tracking-[-0.06em]">
            Blitz
            <br>
            Speed
            <br>
            Access
          </h1>

          <p class="mt-8 max-w-2xl text-sm uppercase leading-relaxed tracking-[0.06em] md:text-base">
            Experience high-demand global tours. No queues, no delays. Secure your front-row spot in milliseconds.
          </p>

          <div class="mt-10 flex flex-col gap-4 sm:flex-row">
            <UiButton to="/events" variant="primary" :full-width="true" class="sm:w-auto">Explore Events</UiButton>
            <UiButton variant="secondary" :full-width="true" class="sm:w-auto">Live Map</UiButton>
          </div>

          <div class="mt-10 grid gap-4 md:grid-cols-3">
            <MetricCard v-for="item in heroMetrics" :key="item.label" :label="item.label" :value="item.value" />
          </div>
        </div>

        <aside class="swiss-dots bg-[var(--swiss-muted)] p-6 md:p-10 lg:col-span-4 lg:p-14">
          <SectionLabel index="02." label="Featured Event" />
          <div class="mt-8 border-4 border-black bg-white p-6">
            <p class="text-xs font-bold uppercase tracking-[0.2em] text-black/70">{{ featureEvent.city }} - {{ featureEvent.date }}</p>
            <h2 class="mt-4 text-4xl font-black uppercase leading-[0.92] tracking-tight">{{ featureEvent.name }}</h2>
            <p class="mt-6 text-sm leading-relaxed">{{ featureEvent.copy }}</p>
            <div class="mt-8 grid grid-cols-2 gap-3">
              <div class="swiss-grid-pattern aspect-square border-2 border-black bg-[var(--swiss-muted)]" />
              <div class="swiss-diagonal aspect-square border-2 border-black bg-[var(--swiss-accent)]" />
              <div class="aspect-square border-2 border-black bg-black" />
              <div class="swiss-dots aspect-square border-2 border-black bg-white" />
            </div>
          </div>
        </aside>
      </div>
    </section>

    <section class="border-b-4 border-black bg-[var(--swiss-muted)]">
      <div class="mx-auto max-w-[1800px] px-6 py-10 md:px-10 md:py-14">
        <SectionLabel index="03." label="Upcoming Blitz Events" />
        <div class="mt-8 grid gap-5 lg:grid-cols-3">
          <EventCard
            v-for="event in events"
            :key="event.title"
            :title="event.title"
            :date-location="event.dateLocation"
            :price="event.price"
            :status="event.status"
            :action="event.action"
            :action-to="event.actionTo"
          />
        </div>
      </div>
    </section>

    <section class="border-b-4 border-black bg-white">
      <div class="mx-auto grid max-w-[1800px] grid-cols-1 lg:grid-cols-12">
        <div class="border-b-4 border-black p-6 md:p-10 lg:col-span-8 lg:border-b-0 lg:border-r-4 lg:p-14">
          <SectionLabel index="04." label="Ready for the Rush?" />
          <h2 class="mt-8 max-w-4xl text-[clamp(2.1rem,7vw,6rem)] font-black uppercase leading-[0.9] tracking-[-0.04em]">
            Built For Fans,
            <br>
            By The Fans.
          </h2>
          <p class="mt-7 max-w-2xl text-sm leading-relaxed md:text-base">
            TicketBlitz is the world's fastest ticketing platform for high-demand experiences, designed for fair access and reliable checkout under load.
          </p>
        </div>

        <div class="swiss-diagonal bg-[var(--swiss-muted)] p-6 md:p-10 lg:col-span-4 lg:p-14">
          <div class="border-4 border-black bg-white p-6">
            <p class="text-xs font-black uppercase tracking-[0.2em]">Get Priority Access</p>
            <p class="mt-4 text-sm leading-relaxed">Join the waitlist to receive drop alerts, venue unlocks, and pre-sale inventory windows.</p>
            <UiButton variant="accent" :full-width="true" class="mt-7">Join Waitlist</UiButton>
          </div>
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
