<script setup>
defineProps({
  event: {
    type: Object,
    default: null,
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
</script>

<template>
  <div class="mt-8 border-4 border-black bg-white p-6">
    <div v-if="loading" class="animate-pulse" aria-live="polite" aria-busy="true">
      <div class="h-4 w-2/3 bg-[var(--swiss-muted)]" />
      <div class="mt-4 h-10 w-full bg-[var(--swiss-muted)]" />
      <div class="mt-3 h-10 w-3/4 bg-[var(--swiss-muted)]" />
      <div class="mt-6 h-20 w-full bg-[var(--swiss-muted)]" />
      <div class="mt-8 grid grid-cols-2 gap-3">
        <div class="aspect-square border-2 border-black bg-[var(--swiss-muted)]" />
        <div class="aspect-square border-2 border-black bg-[var(--swiss-muted)]" />
        <div class="aspect-square border-2 border-black bg-[var(--swiss-muted)]" />
        <div class="aspect-square border-2 border-black bg-[var(--swiss-muted)]" />
      </div>
    </div>

    <UiStateNotice
      v-else-if="errorMessage"
      tone="warning"
      eyebrow="Featured Event"
      title="Live Data Unavailable"
      :message="errorMessage"
    />

    <div v-else-if="event">
      <p class="text-xs font-bold uppercase tracking-[0.2em] text-black/70">{{ event.venue }} - {{ event.dateLabel }}</p>
      <h2 class="mt-4 text-4xl font-black uppercase leading-[0.92] tracking-tight">{{ event.name }}</h2>
      <p class="mt-6 text-sm leading-relaxed">{{ event.copy }}</p>

      <UiButton
        :to="event.detailTo"
        variant="secondary"
        :full-width="true"
        class="mt-7"
      >
        View Event
      </UiButton>

      <div class="mt-8 grid grid-cols-2 gap-3">
        <div class="swiss-grid-pattern aspect-square border-2 border-black bg-[var(--swiss-muted)]" />
        <div class="swiss-diagonal aspect-square border-2 border-black bg-[var(--swiss-accent)]" />
        <div class="aspect-square border-2 border-black bg-black" />
        <div class="swiss-dots aspect-square border-2 border-black bg-white" />
      </div>
    </div>

    <UiStateNotice
      v-else
      tone="warning"
      eyebrow="Featured Event"
      title="No Featured Event"
      message="No featured event is currently available."
    />
  </div>
</template>