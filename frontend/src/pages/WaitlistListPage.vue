<script setup>
import { useFanWaitlistList } from '@/composables/useFanWaitlistList'

const {
  entries,
  loading,
  refreshing,
  errorMessage,
  waitlistMetrics,
  loadWaitlist,
} = useFanWaitlistList()

function onRefresh() {
  void loadWaitlist({ silent: false })
}

function statusClass(entry) {
  if (entry.status === 'HOLD_OFFERED') {
    return 'border-black bg-[var(--swiss-accent)] text-black'
  }

  return 'border-black bg-white text-black'
}
</script>

<template>
  <main class="min-h-screen bg-[var(--swiss-bg)] text-[var(--swiss-fg)]">
    <AppTopNav page-label="Main Page 01" />

    <section class="border-b-4 border-black bg-white">
      <div class="mx-auto max-w-[1800px] px-6 py-8 md:px-10 md:py-10">
        <div class="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <SectionLabel index="12." label="Waitlist" />
            <h1 class="mt-8 text-[clamp(2.2rem,8vw,6rem)] font-black uppercase leading-[0.88] tracking-[-0.05em]">
              Waitlist
              <br>
              Queue
            </h1>
            <p class="mt-5 max-w-3xl text-sm uppercase leading-relaxed tracking-[0.04em] md:text-base">
              Track active entries and respond quickly when an offer opens.
            </p>
          </div>

          <button
            type="button"
            class="inline-flex h-12 items-center justify-center border-2 border-black bg-white px-5 text-xs font-black uppercase tracking-[0.2em] transition duration-200 ease-out hover:bg-black hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
            :disabled="loading || refreshing"
            @click="onRefresh"
          >
            {{ loading || refreshing ? 'Refreshing' : 'Refresh Waitlist' }}
          </button>
        </div>

        <div class="mt-8 grid gap-4 md:grid-cols-3">
          <MetricCard
            v-for="metric in waitlistMetrics"
            :key="metric.label"
            :label="metric.label"
            :value="metric.value"
          />
        </div>
      </div>
    </section>

    <section class="swiss-grid-pattern border-b-4 border-black bg-[var(--swiss-muted)]">
      <div class="mx-auto max-w-[1800px] px-6 py-10 md:px-10 md:py-14">
        <div v-if="errorMessage" class="border-2 border-black bg-rose-100 px-4 py-4 text-sm font-bold uppercase tracking-[0.06em] text-black">
          {{ errorMessage }}
        </div>

        <div
          v-else-if="loading"
          class="grid gap-5 md:grid-cols-2"
        >
          <article
            v-for="placeholder in 4"
            :key="placeholder"
            class="animate-pulse border-4 border-black bg-white p-6"
          >
            <div class="h-5 w-32 bg-[var(--swiss-muted)]" />
            <div class="mt-4 h-8 w-4/5 bg-[var(--swiss-muted)]" />
            <div class="mt-3 h-4 w-3/5 bg-[var(--swiss-muted)]" />
            <div class="mt-6 h-10 w-full border-2 border-black bg-[var(--swiss-muted)]" />
          </article>
        </div>

        <div
          v-else-if="entries.length === 0"
          class="border-4 border-black bg-white p-8 md:p-12"
        >
          <p class="text-xs font-black uppercase tracking-[0.2em] text-black/65">No active waitlist entries</p>
          <h2 class="mt-3 text-4xl font-black uppercase leading-[0.9] tracking-tight">Queue Clear</h2>
          <p class="mt-5 max-w-xl text-sm uppercase leading-relaxed tracking-[0.04em]">
            You are not currently waiting in any active queue.
          </p>
          <UiButton to="/events" variant="secondary" class="mt-6">Browse Events</UiButton>
        </div>

        <div v-else class="grid gap-5 md:grid-cols-2">
          <article
            v-for="entry in entries"
            :key="entry.waitlistID"
            class="group border-4 border-black bg-white p-6 transition duration-200 ease-out hover:-translate-y-px"
          >
            <div class="mb-5 flex items-center justify-between gap-3">
              <span
                class="border-2 px-3 py-1 text-[11px] font-black uppercase tracking-[0.2em]"
                :class="statusClass(entry)"
              >
                {{ entry.status }}
              </span>
              <span class="text-[10px] font-black uppercase tracking-[0.2em] text-black/70">
                {{ entry.eventCode }}
              </span>
            </div>

            <h2 class="text-2xl font-black uppercase leading-tight tracking-tight">{{ entry.eventName }}</h2>
            <p class="mt-4 text-xs font-bold uppercase tracking-[0.12em] text-black/75">{{ entry.venue }}</p>
            <p class="mt-1 text-xs font-bold uppercase tracking-[0.12em] text-black/60">{{ entry.eventDateLabel }}</p>

            <div class="mt-6 grid gap-3 border-t-2 border-black pt-4 sm:grid-cols-2">
              <div class="border-2 border-black bg-[var(--swiss-muted)] px-3 py-2">
                <p class="text-[10px] font-black uppercase tracking-[0.16em] text-black/60">Seat Category</p>
                <p class="mt-2 text-xs font-black uppercase tracking-[0.12em]">{{ entry.seatCategory }}</p>
              </div>
              <div class="border-2 border-black bg-[var(--swiss-muted)] px-3 py-2">
                <p class="text-[10px] font-black uppercase tracking-[0.16em] text-black/60">Queue Position</p>
                <p class="mt-2 text-xs font-black uppercase tracking-[0.12em]">{{ entry.position ?? 'N/A' }}</p>
              </div>
              <div class="border-2 border-black bg-[var(--swiss-muted)] px-3 py-2 sm:col-span-2">
                <p class="text-[10px] font-black uppercase tracking-[0.16em] text-black/60">Joined At</p>
                <p class="mt-2 text-xs font-black uppercase tracking-[0.12em]">{{ entry.joinedAtLabel }}</p>
              </div>
            </div>

            <div class="mt-6 flex flex-col gap-3 sm:flex-row sm:flex-wrap">
              <RouterLink
                v-if="entry.isOfferReady"
                :to="`/waitlist/confirm/${entry.holdID}`"
                class="inline-flex h-11 items-center justify-center border-2 border-black bg-[var(--swiss-accent)] px-4 text-xs font-black uppercase tracking-[0.2em] transition duration-200 ease-out hover:bg-black hover:text-white"
              >
                Complete Offer
              </RouterLink>

              <RouterLink
                :to="`/waitlist/${entry.waitlistID}`"
                class="inline-flex h-11 items-center justify-center border-2 border-black bg-white px-4 text-xs font-black uppercase tracking-[0.2em] transition duration-200 ease-out hover:bg-black hover:text-white"
              >
                View Status
              </RouterLink>

              <RouterLink
                v-if="entry.eventID"
                :to="`/events/${entry.eventID}`"
                class="inline-flex h-11 items-center justify-center border-2 border-black bg-white px-4 text-xs font-black uppercase tracking-[0.2em] transition duration-200 ease-out hover:bg-black hover:text-white"
              >
                View Event
              </RouterLink>
            </div>
          </article>
        </div>
      </div>
    </section>
  </main>
</template>
