<script setup>
defineProps({
  enabled: {
    type: Boolean,
    default: false,
  },
})
</script>

<template>
  <button
    type="button"
    :aria-pressed="enabled"
    class="w-10 h-6 rounded-full relative flex items-center px-1"
    :class="enabled ? 'bg-[#ffd900]' : 'bg-slate-200'"
  >
    <div class="w-4 h-4 rounded-full" :class="enabled ? 'bg-slate-900 ml-auto' : 'bg-white'" />
  </button>
</template>
