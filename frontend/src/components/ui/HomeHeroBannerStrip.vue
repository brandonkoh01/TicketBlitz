<script setup>
defineProps({
  banners: {
    type: Array,
    default: () => [],
  },
})
</script>

<template>
  <section class="mt-10 grid gap-4 md:grid-cols-3" aria-label="Homepage showcase metrics">
    <MetricCard
      v-for="banner in banners"
      :key="banner.label"
      :label="banner.label"
      :value="banner.value"
    />
  </section>
</template>