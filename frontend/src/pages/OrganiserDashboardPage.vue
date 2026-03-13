<script setup>
const sideNavLinks = [
  { icon: 'dashboard', label: 'Dashboard', active: true },
  { icon: 'event', label: 'Events', active: false },
  { icon: 'trending_up', label: 'Sales Analytics', active: false },
]

const tierRows = [
  {
    name: 'Early Bird',
    subtitle: 'First adopters special',
    range: '0 - 50%',
    progressClass: 'w-1/2 bg-[#ffd900]',
    price: '$80.00',
    status: 'active',
  },
  {
    name: 'Phase 1',
    subtitle: 'General admission mid-tier',
    range: '51 - 80%',
    progressClass: 'w-[30%] bg-[#ffd900]/30',
    price: '$120.00',
    status: 'pending',
  },
  {
    name: 'Last Chance',
    subtitle: 'Final inventory pricing',
    range: '81 - 100%',
    progressClass: 'w-1/5 bg-[#ffd900]/30',
    price: '$160.00',
    status: 'pending',
  },
]

const alertRows = [
  { icon: 'payments', title: 'Payout Alerts', detail: 'Every 10 tickets sold' },
  { icon: 'trending_up', title: 'Tier Activation', detail: 'Instant push when price jumps' },
  { icon: 'error', title: 'Inventory Low', detail: 'Notify when < 5% remaining' },
]
</script>

<template>
  <main class="bg-[#f8f8f5] text-slate-900 font-display">
    <div class="relative flex h-auto min-h-screen w-full flex-col overflow-x-hidden">
      <header class="flex items-center justify-between whitespace-nowrap border-b border-slate-200 bg-white px-6 py-3 lg:px-10">
        <div class="flex items-center gap-8">
          <div class="flex items-center gap-3 text-slate-900">
            <div class="flex items-center justify-center rounded bg-[#ffd900] p-1">
              <UiMaterialIcon name="confirmation_number" class="text-slate-900" />
            </div>
            <h2 class="text-lg font-black leading-tight tracking-tight uppercase">
              TicketBlitz <span class="font-light text-slate-500">Organiser</span>
            </h2>
          </div>

          <div class="hidden md:flex flex-col min-w-64 max-w-md">
            <div class="relative flex w-full items-stretch h-10">
              <div class="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none text-slate-400">
                <UiMaterialIcon name="search" class="text-xl" />
              </div>
              <input
                class="w-full rounded-lg border border-slate-200 bg-slate-50 py-2 pl-10 pr-4 text-sm outline-none transition-all focus:border-transparent focus:ring-2 focus:ring-[#ffd900]"
                placeholder="Search events, sales, or attendees..."
              >
            </div>
          </div>
        </div>

        <div class="flex items-center gap-4">
          <div class="flex gap-2">
            <button class="relative flex items-center justify-center w-10 h-10 rounded-lg transition-colors hover:bg-slate-100">
              <UiMaterialIcon name="notifications" />
              <span class="absolute top-2 right-2 flex h-2 w-2 rounded-full bg-[#ffd900] ring-2 ring-white" />
            </button>
            <button class="flex items-center justify-center w-10 h-10 rounded-lg transition-colors hover:bg-slate-100">
              <UiMaterialIcon name="settings" />
            </button>
          </div>

          <div class="h-8 w-px bg-slate-200" />

          <div class="flex items-center gap-3">
            <div class="text-right hidden sm:block">
              <p class="text-xs font-bold leading-none">Studio Arena</p>
              <p class="mt-1 text-[10px] text-slate-500 uppercase tracking-widest">Verified Organiser</p>
            </div>
            <div class="bg-[#ffd900]/20 p-0.5 rounded-full ring-2 ring-[#ffd900]">
              <div
                class="bg-center bg-no-repeat aspect-square bg-cover rounded-full size-8"
                style='background-image: url("https://lh3.googleusercontent.com/aida-public/AB6AXuAEP-eZJilXh7kK2h3K2dYqTwvqlinHJWvkn0LyXM202NVjxIA2plIpoftjSfV2-VP1lXmfsrAYCW9EuO-TU5Z9RiJesDMTLKW5ofdwxN9ace1Oc2NpS1o0gBypByS7K3ePWzWX0bpAg1tQq5V3-H6MYdxmPC8IUaS60px0nsA6LQf2MwHT4rcg6XHePgXxLLj5jA555xFopHt9wJQ0gdKmSPShKimn8NX4QapJZBH7OV_COOYtO08ikklffTSMYgrYfTqVBTCMrPch")'
              />
            </div>
          </div>
        </div>
      </header>

      <div class="flex flex-1">
        <aside class="w-64 border-r border-slate-200 hidden lg:flex flex-col bg-white">
          <div class="p-6">
            <nav class="space-y-1">
              <a
                v-for="item in sideNavLinks"
                :key="item.label"
                href="#"
                class="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors"
                  :class="item.active
                  ? 'bg-[#ffd900] text-slate-900 font-semibold'
                  : 'text-slate-600 hover:bg-slate-100'"
              >
                <UiMaterialIcon :name="item.icon" :class="item.active ? 'text-slate-900' : ''" />
                <span>{{ item.label }}</span>
              </a>
            </nav>
          </div>

          <div class="mt-auto p-6 border-t border-slate-200">
            <div class="rounded-xl border border-[#ffd900]/20 bg-[#ffd900]/10 p-4">
              <p class="mb-2 text-xs font-bold text-slate-900 uppercase tracking-widest">Need Help?</p>
              <p class="mb-3 text-xs text-slate-600">Check our guide on dynamic ticket pricing strategies.</p>
              <button class="w-full rounded-lg bg-slate-900 py-2 text-xs font-bold text-white">View Documentation</button>
            </div>
          </div>
        </aside>

        <section class="flex-1 overflow-y-auto bg-[#f8f8f5] p-4 custom-scrollbar lg:p-10">
          <div class="mb-10 flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
            <div class="space-y-2">
              <nav class="mb-4 flex gap-2 text-xs font-medium text-slate-400">
                <a class="hover:text-[#ffd900]" href="#">Events</a>
                <span>/</span>
                <a class="hover:text-[#ffd900]" href="#">Neon Nights 2026</a>
                <span>/</span>
                <span class="text-slate-900">Flash Sale Setup</span>
              </nav>
              <h1 class="text-4xl font-black leading-tight tracking-tighter uppercase text-slate-900">Flash Sale Setup</h1>
              <p class="max-w-xl text-slate-500">Configure automated ticket price increments based on inventory depletion. Once a threshold is reached, the next tier activates instantly.</p>
            </div>

            <div class="flex gap-3">
              <button class="rounded-lg border border-slate-200 px-6 py-2.5 text-sm font-bold transition-all hover:bg-white">Save Draft</button>
              <button class="rounded-lg bg-[#ffd900] px-6 py-2.5 text-sm font-bold text-slate-900 transition-all hover:shadow-lg hover:shadow-[#ffd900]/20">Launch Sale</button>
            </div>
          </div>

          <div class="grid grid-cols-1 gap-8 xl:grid-cols-3">
            <div class="xl:col-span-2 space-y-8">
              <div class="bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm">
                <div class="px-6 py-4 border-b border-slate-100 flex justify-between items-center bg-slate-50/50">
                  <div class="flex items-center gap-2">
                    <UiMaterialIcon name="sell" class="text-[#ffd900]" />
                    <h3 class="font-bold uppercase tracking-tight text-sm">Automated Pricing Tiers</h3>
                  </div>
                  <button class="text-xs font-bold bg-[#ffd900] px-3 py-1 rounded text-slate-900 hover:opacity-90 transition-opacity flex items-center gap-1">
                    <UiMaterialIcon name="add" class="text-xs" /> Add Tier
                  </button>
                </div>
                <div class="overflow-x-auto">
                  <table class="w-full text-left border-collapse">
                    <thead>
                      <tr class="text-[10px] uppercase tracking-widest text-slate-400 border-b border-slate-100">
                        <th class="px-6 py-4 font-black">Tier Name</th>
                        <th class="px-6 py-4 font-black">Capacity Range</th>
                        <th class="px-6 py-4 font-black">Price ($)</th>
                        <th class="px-6 py-4 font-black">Status</th>
                        <th class="px-6 py-4 font-black text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                      <tr v-for="row in tierRows" :key="row.name" class="group hover:bg-slate-50 transition-colors">
                        <td class="px-6 py-5">
                          <p class="text-sm font-bold">{{ row.name }}</p>
                          <p class="text-xs text-slate-400">{{ row.subtitle }}</p>
                        </td>
                        <td class="px-6 py-5">
                          <div class="flex items-center gap-3">
                            <span class="text-sm font-mono font-medium">{{ row.range }}</span>
                            <div class="h-1.5 w-24 bg-slate-100 rounded-full overflow-hidden">
                              <div class="h-full" :class="row.progressClass" />
                            </div>
                          </div>
                        </td>
                        <td class="px-6 py-5 font-mono text-sm font-bold">{{ row.price }}</td>
                        <td class="px-6 py-5">
                          <span
                            v-if="row.status === 'active'"
                            class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-green-100 text-green-600 uppercase tracking-tighter"
                          >
                            <span class="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
                            Active
                          </span>
                          <span
                            v-else
                            class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-400 uppercase tracking-tighter"
                          >
                            Pending
                          </span>
                        </td>
                        <td class="px-6 py-5 text-right">
                          <button class="text-slate-400 hover:text-[#ffd900] transition-colors">
                            <UiMaterialIcon name="edit" class="text-xl" />
                          </button>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              <!-- Real-time Sales Graph -->
            </div>

            <div class="space-y-8">
              <UiDashboardPanel icon="tune" title="Sale Configuration">
                <div class="space-y-6">
                  <div>
                    <label class="mb-2 block text-[10px] font-black uppercase tracking-widest text-slate-400">Max Tickets per Order</label>
                    <select class="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 outline-none transition-all focus:ring-2 focus:ring-[#ffd900]">
                      <option>4 Tickets</option>
                      <option>6 Tickets</option>
                      <option>10 Tickets</option>
                    </select>
                  </div>

                  <div>
                    <label class="mb-2 block text-[10px] font-black uppercase tracking-widest text-slate-400">Resale Protection</label>
                    <div class="flex items-center justify-between">
                      <span class="text-sm font-medium text-slate-700">Identity Verification Required</span>
                      <UiToggleSwitch :enabled="true" />
                    </div>
                  </div>

                  <div>
                    <label class="mb-2 block text-[10px] font-black uppercase tracking-widest text-slate-400">Countdown Display</label>
                    <div class="flex items-center justify-between">
                      <span class="text-sm font-medium text-slate-700">Show inventory bar to users</span>
                      <UiToggleSwitch :enabled="false" />
                    </div>
                  </div>
                </div>
              </UiDashboardPanel>

              <UiDashboardPanel icon="notifications_active" title="Alert Settings">
                <div class="space-y-5">
                  <div
                    v-for="alert in alertRows"
                    :key="alert.title"
                    class="flex gap-4 rounded-lg border border-transparent p-3 transition-colors hover:border-slate-100 hover:bg-slate-50"
                  >
                    <div class="h-10 w-10 shrink-0 rounded-lg bg-[#ffd900]/20 text-[#ffd900] flex items-center justify-center">
                      <UiMaterialIcon :name="alert.icon" />
                    </div>
                    <div>
                      <p class="text-sm font-bold text-slate-900">{{ alert.title }}</p>
                      <p class="text-xs text-slate-500">{{ alert.detail }}</p>
                    </div>
                  </div>

                  <button class="w-full pt-2 text-xs font-bold uppercase tracking-widest text-slate-400 transition-colors hover:text-[#ffd900]">Configure Integrations</button>
                </div>
              </UiDashboardPanel>

              <section class="rounded-xl bg-[#ffd900] p-6 shadow-lg shadow-[#ffd900]/10">
                <div class="mb-4 flex items-center justify-between">
                  <UiMaterialIcon name="bolt" class="text-slate-900" />
                  <span class="text-[10px] font-black uppercase tracking-widest text-slate-900/50">System Health</span>
                </div>
                <div class="space-y-4">
                  <div>
                    <p class="text-xs font-bold uppercase tracking-tight text-slate-900/70">Active Sessions</p>
                    <p class="text-3xl font-black text-slate-900">1,204</p>
                  </div>
                  <div class="h-1 w-full rounded-full bg-slate-900/10">
                    <div class="h-full w-[78%] rounded-full bg-slate-900" />
                  </div>
                  <p class="text-[10px] italic font-medium leading-relaxed text-slate-900/70">"Dynamic pricing is performing 22% better than static pre-sales for this time slot."</p>
                </div>
              </section>
            </div>
          </div>
        </section>
      </div>
    </div>
  </main>
</template>
