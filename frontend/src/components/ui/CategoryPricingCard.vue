<script setup>
const props = defineProps({
  category: {
    type: Object,
    required: true,
  },
  selectable: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['select'])

function categoryStatusClass(status) {
  if (status === 'SOLD_OUT') {
    return 'border-black bg-black text-white'
  }

  return 'border-black bg-white text-black'
}

function handleSelect() {
  if (!props.selectable) return
  emit('select', props.category)
}

function categoryActionLabel(status) {
  if (status === 'SOLD_OUT') {
    return 'Join waitlist'
  }

  return 'Buy This Category'
}
</script>

<template>
  <article
    class="group border-2 border-black bg-white p-4 transition duration-200 ease-out"
    :class="selectable ? 'hover:-translate-y-px hover:bg-[var(--swiss-accent)]' : ''"
  >
    <div class="flex items-center justify-between gap-3">
      <div>
        <p class="text-sm font-black uppercase tracking-[0.08em]">{{ category.code }}</p>
        <p class="mt-1 text-[11px] font-bold uppercase tracking-[0.1em] text-black/70">{{ category.name }}</p>
      </div>

      <span
        class="border-2 px-2 py-1 text-[10px] font-black uppercase tracking-[0.18em]"
        :class="categoryStatusClass(category.status)"
      >
        {{ category.status === 'SOLD_OUT' ? 'Sold Out' : 'Available' }}
      </span>
    </div>

    <div class="mt-4 border-t-2 border-black pt-3">
      <p class="text-[11px] font-bold uppercase tracking-[0.1em] text-black/65">Base: {{ category.basePriceLabel }}</p>
      <p class="mt-1 text-[11px] font-black uppercase tracking-[0.1em]">Current: {{ category.currentPriceLabel }}</p>
      <p
        v-if="category.changed"
        class="mt-2 text-[10px] font-black uppercase tracking-[0.14em] text-black/70"
      >
        Adjusted by flash sale or escalation
      </p>
    </div>

    <button
      v-if="selectable"
      type="button"
      class="mt-4 inline-flex h-11 w-full items-center justify-center border-2 border-black bg-black px-4 text-[11px] font-black uppercase tracking-[0.2em] text-white transition duration-200 ease-out hover:bg-white hover:text-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2"
      @click="handleSelect"
    >
      {{ categoryActionLabel(category.status) }}
    </button>
  </article>
</template>
