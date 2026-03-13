<script setup>
defineProps({
  label: {
    type: String,
    required: true,
  },
  value: {
    type: String,
    required: true,
  },
})
</script>

<template>
  <article class="border-4 border-black bg-white p-6 transition duration-200 ease-out hover:-translate-y-px hover:bg-[var(--swiss-accent)]">
    <p class="text-[11px] font-bold uppercase tracking-[0.22em] text-black/75">{{ label }}</p>
    <p class="mt-3 text-5xl font-black tracking-tight md:text-6xl">{{ value }}</p>
  </article>
</template>
