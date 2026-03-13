<script setup>
defineProps({
  index: {
    type: String,
    required: true,
  },
  label: {
    type: String,
    required: true,
  },
})
</script>

<template>
  <div class="flex items-center gap-3 border-b-2 border-black pb-3">
    <span class="text-sm font-black uppercase tracking-[0.28em] text-[var(--swiss-accent)]">{{ index }}</span>
    <span class="text-sm font-bold uppercase tracking-[0.28em]">{{ label }}</span>
  </div>
</template>
