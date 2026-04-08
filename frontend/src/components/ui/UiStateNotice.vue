<script setup>
import { computed } from 'vue'

const props = defineProps({
  tone: {
    type: String,
    default: 'neutral',
  },
  eyebrow: {
    type: String,
    default: '',
  },
  title: {
    type: String,
    default: '',
  },
  message: {
    type: String,
    default: '',
  },
})

const toneClasses = computed(() => {
  if (props.tone === 'error') {
    return 'bg-black text-white border-black'
  }

  if (props.tone === 'warning') {
    return 'bg-[var(--swiss-accent)] text-black border-black'
  }

  return 'bg-[var(--swiss-muted)] text-black border-black'
})

const eyebrowClasses = computed(() => {
  if (props.tone === 'error') {
    return 'text-white/70'
  }

  return 'text-black/65'
})
</script>

<template>
  <section
    class="border-2 px-4 py-4"
    :class="toneClasses"
    role="status"
    aria-live="polite"
  >
    <p
      v-if="eyebrow"
      class="text-[10px] font-black uppercase tracking-[0.2em]"
      :class="eyebrowClasses"
    >
      {{ eyebrow }}
    </p>

    <p
      v-if="title"
      class="mt-2 text-xs font-black uppercase tracking-[0.14em]"
    >
      {{ title }}
    </p>

    <p
      v-if="message"
      class="mt-2 text-xs font-bold uppercase leading-relaxed tracking-[0.08em]"
    >
      {{ message }}
    </p>

    <div
      v-if="$slots.actions"
      class="mt-4 flex flex-wrap gap-2"
    >
      <slot name="actions" />
    </div>
  </section>
</template>
