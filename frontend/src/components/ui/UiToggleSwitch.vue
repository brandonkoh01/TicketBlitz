<script setup>
const props = defineProps({
  enabled: {
    type: Boolean,
    default: false,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['toggle'])

function onToggle() {
  if (props.disabled) return
  emit('toggle', !props.enabled)
}
</script>

<template>
  <button
    type="button"
    :aria-pressed="enabled"
    :disabled="disabled"
    class="relative flex h-6 w-10 items-center rounded-full px-1 transition-colors"
    :class="[
      enabled ? 'bg-[#ffd900]' : 'bg-slate-200',
      disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
    ]"
    @click="onToggle"
  >
    <div class="w-4 h-4 rounded-full" :class="enabled ? 'bg-slate-900 ml-auto' : 'bg-white'" />
  </button>
</template>
