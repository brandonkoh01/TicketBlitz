<script setup>
defineProps({
  configItems: {
    type: Array,
    required: true,
  },
})
</script>

<template>
  <section class="border-4 border-black bg-white p-6">
    <p class="text-sm font-black uppercase tracking-[0.24em]">Sale Configuration</p>
    <ul class="mt-5 space-y-3">
      <li
        v-for="item in configItems"
        :key="item.id"
        class="flex flex-col justify-between gap-3 border-2 border-black bg-[var(--swiss-muted)] p-4 sm:flex-row sm:items-center"
      >
        <div>
          <p class="text-xs font-black uppercase tracking-[0.16em]">{{ item.label }}</p>
          <p class="mt-1 text-xs leading-relaxed">{{ item.description }}</p>
        </div>

        <button
          type="button"
          class="min-h-11 min-w-24 border-2 border-black px-3 text-[10px] font-black uppercase tracking-[0.2em] transition duration-150 ease-linear focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2"
          :class="item.enabled ? 'bg-black text-white' : 'bg-white text-black'"
          :aria-pressed="item.enabled"
        >
          {{ item.enabled ? 'Enabled' : 'Disabled' }}
        </button>
      </li>
    </ul>
  </section>
</template>
