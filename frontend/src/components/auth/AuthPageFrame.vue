<script setup>
import AuthFooter from '@/components/auth/AuthFooter.vue'

defineProps({
  topActionLabel: {
    type: String,
    required: true,
  },
  topActionTo: {
    type: String,
    required: true,
  },
})
</script>

<template>
  <div class="relative min-h-screen bg-[var(--swiss-muted)] text-black">
    <div class="pointer-events-none fixed inset-0 z-0 swiss-dot-grid opacity-60" />

    <header class="relative z-10 flex items-center justify-between border-b-4 border-black bg-white px-6 py-6">
      <RouterLink
        to="/"
        class="text-xl font-black uppercase tracking-[-0.03em] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2"
      >
        TicketBlitz
      </RouterLink>

      <RouterLink
        :to="topActionTo"
        class="text-[11px] font-black uppercase tracking-[0.14em] transition duration-150 ease-linear hover:text-[var(--swiss-accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2"
      >
        {{ topActionLabel }}
      </RouterLink>
    </header>

    <main class="relative z-10 mx-auto grid min-h-[calc(100vh-100px)] max-w-[1440px] grid-cols-1 md:grid-cols-12">
      <section class="border-b-4 border-black px-6 py-16 md:col-span-7 md:border-b-0 md:border-r-4 md:px-8 md:py-20 lg:px-10">
        <slot name="left" />
      </section>

      <section class="bg-white px-6 py-14 md:col-span-5 md:px-8 md:py-20 lg:px-10">
        <slot name="right" />
      </section>
    </main>

    <AuthFooter />
  </div>
</template>
