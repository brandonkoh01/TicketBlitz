<script setup>
import { computed } from 'vue'

const props = defineProps({
  points: {
    type: Array,
    required: true,
  },
  revenue: {
    type: String,
    required: true,
  },
  sold: {
    type: Number,
    required: true,
  },
  capacity: {
    type: Number,
    required: true,
  },
  velocity: {
    type: String,
    required: true,
  },
})

const maxPoint = computed(() => Math.max(...props.points, 1))

const columns = computed(() => {
  return props.points.map((point) => {
    const height = Math.max((point / maxPoint.value) * 100, 14)
    return {
      point,
      height,
    }
  })
})
</script>

<template>
  <section class="swiss-dots border-4 border-black bg-[var(--swiss-muted)] p-6">
    <p class="text-sm font-black uppercase tracking-[0.24em]">Sales Velocity Tracker</p>
    <p class="mt-2 text-xs font-bold uppercase tracking-[0.18em] text-black/70">Live updates for flash sale</p>

    <div class="mt-5 grid h-40 grid-cols-8 items-end gap-2 border-2 border-black bg-white p-3">
      <div v-for="(column, index) in columns" :key="index" class="flex flex-col items-center gap-2">
        <div class="w-full border-2 border-black bg-[var(--swiss-accent)]" :style="{ height: `${column.height}%` }" />
        <span class="text-[10px] font-black">{{ column.point }}</span>
      </div>
    </div>

    <div class="mt-5 grid gap-3 sm:grid-cols-3">
      <article class="border-2 border-black bg-white p-3">
        <p class="text-[10px] font-black uppercase tracking-[0.2em]">Revenue</p>
        <p class="mt-2 text-xl font-black tracking-tight">{{ revenue }}</p>
      </article>
      <article class="border-2 border-black bg-white p-3">
        <p class="text-[10px] font-black uppercase tracking-[0.2em]">Tickets Sold</p>
        <p class="mt-2 text-xl font-black tracking-tight">{{ sold }} / {{ capacity }}</p>
      </article>
      <article class="border-2 border-black bg-black p-3 text-white">
        <p class="text-[10px] font-black uppercase tracking-[0.2em]">Velocity</p>
        <p class="mt-2 text-xl font-black tracking-tight">{{ velocity }}</p>
      </article>
    </div>
  </section>
</template>
