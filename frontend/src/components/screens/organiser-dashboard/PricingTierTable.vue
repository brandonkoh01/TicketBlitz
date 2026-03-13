<script setup>
defineProps({
  tiers: {
    type: Array,
    required: true,
  },
  activeCount: {
    type: Number,
    required: true,
  },
  pendingCount: {
    type: Number,
    required: true,
  },
})

function statusClass(status) {
  if (status === 'Active') {
    return 'bg-black text-white'
  }

  return 'bg-[var(--swiss-accent)] text-black'
}
</script>

<template>
  <section class="border-4 border-black bg-white p-6">
    <div class="flex flex-wrap items-center justify-between gap-3 border-b-2 border-black pb-4">
      <p class="text-sm font-black uppercase tracking-[0.24em]">Automated Pricing Tiers</p>
      <div class="flex items-center gap-2">
        <span class="border-2 border-black px-2 py-1 text-[10px] font-black uppercase tracking-[0.2em]">{{ activeCount }} Active</span>
        <span class="border-2 border-black bg-[var(--swiss-muted)] px-2 py-1 text-[10px] font-black uppercase tracking-[0.2em]">{{ pendingCount }} Pending</span>
      </div>
    </div>

    <div class="mt-5 overflow-x-auto">
      <table class="min-w-full border-collapse text-left">
        <thead>
          <tr>
            <th class="border-2 border-black bg-[var(--swiss-muted)] px-3 py-2 text-[11px] font-black uppercase tracking-[0.2em]">Tier</th>
            <th class="border-2 border-black bg-[var(--swiss-muted)] px-3 py-2 text-[11px] font-black uppercase tracking-[0.2em]">Inventory</th>
            <th class="border-2 border-black bg-[var(--swiss-muted)] px-3 py-2 text-[11px] font-black uppercase tracking-[0.2em]">Price</th>
            <th class="border-2 border-black bg-[var(--swiss-muted)] px-3 py-2 text-[11px] font-black uppercase tracking-[0.2em]">Status</th>
            <th class="border-2 border-black bg-[var(--swiss-muted)] px-3 py-2 text-[11px] font-black uppercase tracking-[0.2em]">Action</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="tier in tiers" :key="tier.id">
            <td class="border-2 border-black px-3 py-3 text-xs font-bold uppercase tracking-[0.12em]">{{ tier.name }}</td>
            <td class="border-2 border-black px-3 py-3 text-xs font-bold uppercase tracking-[0.12em]">{{ tier.inventoryRange }}</td>
            <td class="border-2 border-black px-3 py-3 text-base font-black">{{ tier.price }}</td>
            <td class="border-2 border-black px-3 py-3">
              <span class="inline-flex border-2 border-black px-2 py-1 text-[10px] font-black uppercase tracking-[0.2em]" :class="statusClass(tier.status)">{{ tier.status }}</span>
            </td>
            <td class="border-2 border-black px-3 py-3">
              <button type="button" class="min-h-11 border-2 border-black bg-white px-3 text-[10px] font-black uppercase tracking-[0.2em] transition duration-150 ease-linear hover:bg-black hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2">
                Edit
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
