<script setup>
defineProps({
  activeSessions: {
    type: String,
    required: true,
  },
  insight: {
    type: String,
    required: true,
  },
})
</script>

<template>
  <section class="border-4 border-black bg-black p-6 text-white">
    <p class="text-sm font-black uppercase tracking-[0.24em]">System Health</p>

    <div class="mt-5 border-2 border-white/60 p-4">
      <p class="text-[10px] font-black uppercase tracking-[0.2em] text-[var(--swiss-accent)]">Active Sessions</p>
      <p class="mt-2 text-4xl font-black tracking-tight">{{ activeSessions }}</p>
    </div>

    <blockquote class="mt-5 border-l-4 border-[var(--swiss-accent)] pl-4 text-sm leading-relaxed text-white/90">
      {{ insight }}
    </blockquote>
  </section>
</template>
