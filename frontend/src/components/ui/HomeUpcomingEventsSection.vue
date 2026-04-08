<script setup>
const props = defineProps({
  events: {
    type: Array,
    default: () => [],
  },
  loading: {
    type: Boolean,
    default: false,
  },
  errorMessage: {
    type: String,
    default: '',
  },
})

const emit = defineEmits(['refresh'])

function onRefresh() {
  emit('refresh')
}
</script>

<template>
  <section class="border-b-4 border-black bg-[var(--swiss-muted)]">
    <div class="mx-auto max-w-[1800px] px-6 py-10 md:px-10 md:py-14">
      <SectionLabel index="03." label="Upcoming Blitz Events" />

      <UiStateNotice
        v-if="errorMessage"
        class="mt-8"
        tone="warning"
        eyebrow="Events"
        title="Unable To Load Events"
        :message="errorMessage"
      >
        <template #actions>
          <button
            type="button"
            class="inline-flex h-10 items-center justify-center border-2 border-black bg-white px-4 text-[11px] font-black uppercase tracking-[0.16em] transition duration-200 ease-out hover:bg-black hover:text-white"
            @click="onRefresh"
          >
            Retry
          </button>
        </template>
      </UiStateNotice>

      <div
        v-else-if="loading"
        class="mt-8 grid gap-5 lg:grid-cols-3"
        aria-live="polite"
        aria-busy="true"
      >
        <article
          v-for="placeholder in 3"
          :key="placeholder"
          class="animate-pulse border-4 border-black bg-white p-6"
        >
          <div class="h-6 w-1/2 bg-[var(--swiss-muted)]" />
          <div class="mt-3 h-9 w-full bg-[var(--swiss-muted)]" />
          <div class="mt-8 h-8 w-2/3 bg-[var(--swiss-muted)]" />
          <div class="mt-4 h-10 w-28 border-2 border-black bg-[var(--swiss-muted)]" />
        </article>
      </div>

      <UiStateNotice
        v-else-if="props.events.length === 0"
        class="mt-8"
        tone="warning"
        eyebrow="Events"
        title="No Upcoming Events"
        message="No upcoming bookable events are available yet."
      />

      <div v-else class="mt-8 grid gap-5 lg:grid-cols-3">
        <EventCard
          v-for="event in props.events"
          :key="event.id"
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
</template>