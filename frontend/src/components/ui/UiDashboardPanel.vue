<script setup>
import { computed, useSlots } from 'vue'

const props = defineProps({
  icon: {
    type: String,
    required: true,
  },
  title: {
    type: String,
    required: true,
  },
  theme: {
    type: String,
    default: 'light',
    validator: (value) => ['light', 'midnight'].includes(value),
  },
})

const slots = useSlots()
const hasActions = computed(() => Boolean(slots.actions))
const isMidnightTheme = computed(() => props.theme === 'midnight')
const panelClass = computed(() => (
  isMidnightTheme.value
    ? 'border border-slate-700/50 bg-gradient-to-br from-[#0f1f3d] to-[#0a1a36] text-slate-100 rounded-xl overflow-hidden shadow-sm'
    : 'bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm'
))
const headerClass = computed(() => (
  isMidnightTheme.value
    ? 'px-6 py-4 border-b border-slate-700/40 flex items-center gap-2 bg-slate-900/20'
    : 'px-6 py-4 border-b border-slate-100 flex items-center gap-2 bg-slate-50/50'
))
const titleClass = computed(() => (
  isMidnightTheme.value
    ? 'font-bold uppercase tracking-tight text-sm text-slate-300'
    : 'font-bold uppercase tracking-tight text-sm text-slate-900'
))
</script>

<template>
  <section :class="panelClass">
    <header :class="[headerClass, hasActions ? 'justify-between' : '']">
      <div class="flex items-center gap-2">
        <UiMaterialIcon :name="icon" class="text-[#ffd900]" />
        <h3 :class="titleClass">{{ title }}</h3>
      </div>
      <slot name="actions" />
    </header>
    <div class="p-6">
      <slot />
    </div>
  </section>
</template>
