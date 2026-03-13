<script setup>
defineProps({
  icon: {
    type: String,
    required: true,
  },
  title: {
    type: String,
    required: true,
  },
  body: {
    type: String,
    required: true,
  },
})
</script>

<template>
  <article class="group border-4 border-black bg-white p-8 transition duration-200 ease-out hover:-translate-y-px hover:bg-[var(--swiss-accent)]">
    <div class="mb-8 flex items-center justify-between">
      <span class="text-3xl font-black">{{ icon }}</span>
      <span class="text-2xl font-black transition duration-200 ease-linear group-hover:rotate-90">+</span>
    </div>
    <h3 class="mb-3 text-2xl font-black uppercase tracking-tight">{{ title }}</h3>
    <p class="max-w-prose text-sm leading-relaxed text-black/80">{{ body }}</p>
  </article>
</template>
