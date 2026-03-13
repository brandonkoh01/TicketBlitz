<script setup>
defineProps({
  title: {
    type: String,
    required: true,
  },
  subtitle: {
    type: String,
    required: true,
  },
  links: {
    type: Array,
    required: true,
  },
})
</script>

<template>
  <aside class="border-b-4 border-black bg-[var(--swiss-muted)] p-6 lg:min-h-screen lg:border-b-0 lg:border-r-4 lg:p-8">
    <p class="text-xs font-black uppercase tracking-[0.28em]">{{ title }}</p>
    <p class="mt-3 text-[11px] font-bold uppercase tracking-[0.2em] text-black/65">{{ subtitle }}</p>

    <nav class="mt-8 space-y-2">
      <component
        :is="link.to === '#' ? 'a' : 'RouterLink'"
        v-for="link in links"
        :key="link.label"
        :to="link.to !== '#' ? link.to : undefined"
        :href="link.to === '#' ? '#' : undefined"
        class="group flex min-h-11 items-center justify-between border-2 border-black bg-white px-4 py-3 text-xs font-black uppercase tracking-[0.2em] transition duration-150 ease-linear hover:bg-black hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2"
      >
        <span>{{ link.label }}</span>
        <span class="text-[11px]">{{ link.icon }}</span>
      </component>
    </nav>

    <div class="swiss-grid-pattern mt-8 border-4 border-black bg-white p-5">
      <p class="text-xs font-black uppercase tracking-[0.2em]">Need Help?</p>
      <p class="mt-3 text-sm leading-relaxed">Check our guide on dynamic ticket pricing strategies.</p>
      <UiButton variant="secondary" :full-width="true" class="mt-5">View Documentation</UiButton>
    </div>
  </aside>
</template>
