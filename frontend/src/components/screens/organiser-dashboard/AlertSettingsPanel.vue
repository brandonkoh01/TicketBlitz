<script setup>
defineProps({
  alerts: {
    type: Array,
    required: true,
  },
})
</script>

<template>
  <section class="swiss-diagonal border-4 border-black bg-[var(--swiss-muted)] p-6">
    <p class="text-sm font-black uppercase tracking-[0.24em]">Alert Settings</p>

    <ul class="mt-5 space-y-3">
      <li v-for="alert in alerts" :key="alert.id" class="border-2 border-black bg-white p-4">
        <div class="flex items-center justify-between gap-3">
          <p class="text-xs font-black uppercase tracking-[0.16em]">{{ alert.title }}</p>
          <span class="text-[11px] font-black uppercase">{{ alert.icon }}</span>
        </div>
        <p class="mt-2 text-xs leading-relaxed">{{ alert.detail }}</p>
      </li>
    </ul>

    <UiButton variant="secondary" :full-width="true" class="mt-5">Configure Integrations</UiButton>
  </section>
</template>
