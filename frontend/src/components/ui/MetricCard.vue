<script setup>
import { computed } from 'vue'

const props = defineProps({
  label: {
    type: String,
    required: true,
  },
  value: {
    type: String,
    required: true,
  },
  valueVariant: {
    type: String,
    default: 'default',
  },
})

const valueTextClass = computed(() => {
  if (props.valueVariant === 'compact') {
    return 'mt-3 text-3xl font-black leading-tight tracking-tight md:text-4xl'
  }

  return 'mt-3 text-5xl font-black tracking-tight md:text-6xl'
})
</script>

<template>
  <article class="border-4 border-black bg-white p-6 transition duration-200 ease-out hover:-translate-y-px hover:bg-[var(--swiss-accent)]">
    <p class="text-[11px] font-bold uppercase tracking-[0.22em] text-black/75">{{ label }}</p>
    <p :class="valueTextClass">{{ value }}</p>
  </article>
</template>
