<script setup>
defineProps({
  title: {
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
  <div>
    <h3 class="text-[11px] font-black uppercase tracking-[0.24em] text-[var(--swiss-accent)]">{{ title }}</h3>
    <ul class="mt-4 space-y-2">
      <li v-for="link in links" :key="link">
        <a href="#" class="swiss-link-slide text-xs font-bold uppercase tracking-[0.18em] text-white" :data-alt="link">
          <span>{{ link }}</span>
        </a>
      </li>
    </ul>
  </div>
</template>
