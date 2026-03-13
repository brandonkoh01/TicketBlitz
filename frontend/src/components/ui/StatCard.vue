<script setup>
defineProps({
  value: {
    type: String,
    required: true,
  },
  label: {
    type: String,
    required: true,
  },
})
</script>

<template>
  <article class="group border-4 border-black bg-white p-6 transition duration-200 ease-out hover:-translate-y-px hover:bg-black hover:text-white">
    <p class="text-4xl font-black tracking-tight transition duration-200 ease-out group-hover:scale-105">{{ value }}</p>
    <p class="mt-2 text-xs font-bold uppercase tracking-[0.2em]">{{ label }}</p>
  </article>
</template>
