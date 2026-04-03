<script setup>
import { computed } from 'vue'
import { RouterLink } from 'vue-router'

const props = defineProps({
  as: {
    type: String,
    default: 'button',
  },
  href: {
    type: String,
    default: '',
  },
  to: {
    type: [String, Object],
    default: '',
  },
  type: {
    type: String,
    default: 'button',
  },
  variant: {
    type: String,
    default: 'primary',
  },
  fullWidth: {
    type: Boolean,
    default: false,
  },
})

const tag = computed(() => {
  if (props.to) return RouterLink
  if (props.href) return 'a'
  return props.as
})

const variantClasses = computed(() => {
  if (props.variant === 'secondary') {
    return 'bg-white text-black border-black hover:bg-black hover:text-white'
  }

  if (props.variant === 'accent') {
    return 'bg-[var(--swiss-accent)] text-black border-black hover:bg-black hover:text-white'
  }

  return 'bg-black text-white border-black hover:bg-[var(--swiss-accent)] hover:text-black'
})
</script>

<template>
  <component
    :is="tag"
    :to="props.to || undefined"
    :href="href || undefined"
    :type="tag === 'button' ? type : undefined"
    class="inline-flex h-14 items-center justify-center border-2 px-6 text-xs font-black uppercase tracking-[0.24em] transition duration-200 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2"
    :class="[variantClasses, fullWidth ? 'w-full' : 'w-auto min-w-[12rem]']"
  >
    <slot />
  </component>
</template>
