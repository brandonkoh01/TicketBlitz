<script setup>
defineProps({
  title: {
    type: String,
    required: true,
  },
  dateLocation: {
    type: String,
    required: true,
  },
  price: {
    type: String,
    required: true,
  },
  status: {
    type: String,
    required: true,
  },
  action: {
    type: String,
    required: true,
  },
})

function statusClass(status) {
  if (status === 'Sold Out') return 'bg-black text-white'
  if (status === 'Low Stock') return 'bg-[var(--swiss-accent)] text-black'
  return 'bg-white text-black'
}
</script>

<template>
  <article class="group border-4 border-black bg-white p-6 transition duration-200 ease-out hover:-translate-y-px hover:bg-[var(--swiss-accent)]">
    <div class="mb-5 flex items-center justify-between gap-4">
      <span class="border-2 border-black px-3 py-1 text-[11px] font-black uppercase tracking-[0.2em]" :class="statusClass(status)">{{ status }}</span>
      <span class="text-[11px] font-bold uppercase tracking-[0.2em]">{{ dateLocation }}</span>
    </div>
    <h3 class="text-2xl font-black uppercase leading-tight tracking-tight">{{ title }}</h3>
    <div class="mt-8 flex items-center justify-between border-t-2 border-black pt-4">
      <p class="text-lg font-black">{{ price }}</p>
      <a href="#" class="swiss-link-slide text-xs font-black uppercase tracking-[0.2em]" :data-alt="action">
        <span>{{ action }}</span>
      </a>
    </div>
  </article>
</template>
