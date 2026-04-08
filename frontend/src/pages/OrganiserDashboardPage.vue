<script setup>
import { computed } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { useOrganiserDashboardScenario2 } from '@/composables/useOrganiserDashboardScenario2'

const authStore = useAuthStore()
const isAuthenticated = computed(() => authStore.isAuthenticated.value)

const sideNavLinks = [
  { icon: 'dashboard', label: 'Dashboard', active: true, to: null },
  { icon: 'event', label: 'Events', active: false, to: '/events' },
  { icon: 'trending_up', label: 'Sales Analytics', active: false, to: null },
]

const alertRows = [
  { icon: 'payments', title: 'Payout Alerts', detail: 'Every 10 tickets sold' },
  { icon: 'trending_up', title: 'Tier Activation', detail: 'Instant push when price jumps' },
  { icon: 'error', title: 'Inventory Low', detail: 'Notify when < 5% remaining' },
]

const {
  discountPercentage,
  durationMinutes,
  escalationPercentage,
  errorMessage,
  noticeMessage,
  unsupportedMessage,
  eventsLoading,
  launchLoading,
  endLoading,
  requestBusy,
  selectedEventID,
  eventOptions,
  tierRows,
  flashSaleIsActive,
  activeFlashSaleID,
  canEndFlashSale,
  lastCorrelationID,
  systemHealth,
  clearFlashMessages,
  loadEvents,
  launchSelectedFlashSale,
  endSelectedFlashSale,
} = useOrganiserDashboardScenario2()

const unsupportedControlNote = 'Not available for current backend scope.'

const isLaunchDisabled = computed(() => launchLoading.value || requestBusy.value || !selectedEventID.value)

function onLaunchSale() {
  clearFlashMessages()
  void launchSelectedFlashSale()
}

function onEndSale() {
  clearFlashMessages()
  void endSelectedFlashSale()
}

function onRefreshEvents() {
  void loadEvents()
}
</script>

<template>
  <main class="bg-[#f8f8f5] text-slate-900 font-display">
    <div class="relative flex h-auto min-h-screen w-full flex-col overflow-x-hidden">
      <header class="flex items-center justify-between whitespace-nowrap border-b border-slate-200 bg-white px-6 py-3 lg:px-10">
        <div class="flex items-center gap-8">
          <RouterLink
            to="/"
            class="flex items-center gap-3 text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ffd900] focus-visible:ring-offset-2"
          >
            <div class="flex items-center justify-center border-2 border-black bg-[#ffd900] p-1">
              <UiMaterialIcon name="confirmation_number" class="text-slate-900" />
            </div>
            <h2 class="text-lg font-black leading-tight tracking-tight uppercase">
              TicketBlitz <span class="font-light text-slate-500">Organiser</span>
            </h2>
          </RouterLink>

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
            <button
              class="relative flex h-10 w-10 cursor-not-allowed items-center justify-center rounded-lg opacity-50"
              type="button"
              disabled
              :title="unsupportedControlNote"
            >
              <UiMaterialIcon name="notifications" />
              <span class="absolute top-2 right-2 flex h-2 w-2 rounded-full bg-[#ffd900] ring-2 ring-white" />
            </button>
            <button
              class="flex h-10 w-10 cursor-not-allowed items-center justify-center rounded-lg opacity-50"
              type="button"
              disabled
              :title="unsupportedControlNote"
            >
              <UiMaterialIcon name="settings" />
            </button>
          </div>

          <div class="h-8 w-px bg-slate-200" />

          <AuthSessionControls v-if="isAuthenticated" />
        </div>
      </header>

      <div class="flex flex-1">
        <aside class="w-64 border-r border-slate-200 hidden lg:flex flex-col bg-white">
          <div class="p-6">
            <nav class="space-y-1">
              <component
                v-for="item in sideNavLinks"
                :key="item.label"
                :is="item.to ? 'RouterLink' : 'a'"
                :to="item.to || undefined"
                :href="item.to ? undefined : '#'"
                class="flex items-center gap-3 px-3 py-2 rounded-lg transition-colors"
                  :class="item.active
                  ? 'bg-[#ffd900] text-slate-900 font-semibold'
                  : 'text-slate-600 hover:bg-slate-100'"
              >
                <UiMaterialIcon :name="item.icon" :class="item.active ? 'text-slate-900' : ''" />
                <span>{{ item.label }}</span>
              </component>
            </nav>
          </div>

          <div class="mt-auto p-6 border-t border-slate-200">
            <div class="rounded-xl border border-[#ffd900]/20 bg-[#ffd900]/10 p-4">
              <p class="mb-2 text-xs font-bold text-slate-900 uppercase tracking-widest">Need Help?</p>
              <p class="mb-3 text-xs text-slate-600">Check our guide on dynamic ticket pricing strategies.</p>
              <button
                class="w-full cursor-not-allowed rounded-lg bg-slate-900 py-2 text-xs font-bold text-white opacity-60"
                type="button"
                disabled
                :title="unsupportedControlNote"
              >
                View Documentation
              </button>
            </div>
          </div>
        </aside>

        <section class="flex-1 overflow-y-auto bg-[#f8f8f5] p-4 custom-scrollbar lg:p-10">
          <div class="mb-6 grid grid-cols-1 gap-3 xl:grid-cols-3">
            <div class="rounded-xl border border-slate-200 bg-white p-4 xl:col-span-2">
              <label class="mb-2 block text-[10px] font-black uppercase tracking-widest text-slate-500">Selected Event</label>
              <div class="flex gap-3">
                <select
                  v-model="selectedEventID"
                  class="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-[#ffd900]"
                  :disabled="eventsLoading || requestBusy"
                >
                  <option value="" disabled>Select an event</option>
                  <option v-for="event in eventOptions" :key="event.id" :value="event.id">{{ event.label }}</option>
                </select>
                <button
                  class="rounded-lg border border-slate-200 bg-white px-4 text-xs font-bold uppercase tracking-wider disabled:cursor-not-allowed disabled:opacity-50"
                  type="button"
                  :disabled="eventsLoading || requestBusy"
                  @click="onRefreshEvents"
                >
                  {{ eventsLoading ? 'Loading...' : 'Refresh' }}
                </button>
              </div>
            </div>
            <div class="rounded-xl border border-slate-200 bg-white p-4">
              <p class="text-[10px] font-black uppercase tracking-widest text-slate-500">Flash Sale Status</p>
              <p class="mt-2 text-sm font-semibold" :class="flashSaleIsActive ? 'text-green-600' : 'text-slate-500'">
                {{ flashSaleIsActive ? 'ACTIVE' : 'INACTIVE' }}
              </p>
              <p class="mt-1 text-xs text-slate-500">{{ activeFlashSaleID || 'No active flash sale id' }}</p>
            </div>
          </div>

          <div v-if="errorMessage" class="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {{ errorMessage }}
          </div>
          <div v-if="noticeMessage" class="mb-4 rounded-lg border border-green-200 bg-green-50 px-4 py-3 text-sm text-green-700">
            {{ noticeMessage }}
          </div>
          <div v-if="unsupportedMessage" class="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">
            {{ unsupportedMessage }}
          </div>
          <div v-if="lastCorrelationID" class="mb-4 text-[11px] font-medium uppercase tracking-widest text-slate-500">
            Correlation ID: {{ lastCorrelationID }}
          </div>

          <div class="mb-10 flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
            <div class="space-y-2">
              <nav class="mb-4 flex gap-2 text-xs font-medium text-slate-400">
                <RouterLink class="hover:text-[#ffd900]" to="/events">Events</RouterLink>
                <span>/</span>
                <a class="hover:text-[#ffd900]" href="#">Live Event Configuration</a>
                <span>/</span>
                <span class="text-slate-900">Flash Sale Setup</span>
              </nav>
              <h1 class="text-4xl font-black leading-tight tracking-tighter uppercase text-slate-900">Flash Sale Setup</h1>
              <p class="max-w-xl text-slate-500">Configure automated ticket price increments based on inventory depletion. Once a threshold is reached, the next tier activates instantly.</p>
            </div>

            <div class="flex flex-wrap gap-3">
              <button
                class="cursor-not-allowed rounded-lg border border-slate-200 px-6 py-2.5 text-sm font-bold opacity-60"
                type="button"
                disabled
                :title="unsupportedControlNote"
              >
                Save Draft
              </button>
              <button
                class="rounded-lg bg-[#ffd900] px-6 py-2.5 text-sm font-bold text-slate-900 transition-all hover:shadow-lg hover:shadow-[#ffd900]/20 disabled:cursor-not-allowed disabled:opacity-50"
                type="button"
                :disabled="isLaunchDisabled"
                @click="onLaunchSale"
              >
                {{ launchLoading ? 'Launching...' : 'Launch Sale' }}
              </button>
              <button
                class="rounded-lg border border-slate-300 bg-white px-6 py-2.5 text-sm font-bold text-slate-900 transition-all hover:bg-slate-50 disabled:cursor-not-allowed disabled:opacity-50"
                type="button"
                :disabled="!canEndFlashSale"
                @click="onEndSale"
              >
                {{ endLoading ? 'Ending...' : 'End Sale' }}
              </button>
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
                  <button
                    class="flex cursor-not-allowed items-center gap-1 rounded bg-[#ffd900] px-3 py-1 text-xs font-bold text-slate-900 opacity-60"
                    type="button"
                    disabled
                    :title="unsupportedControlNote"
                  >
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
                      </tr>
                    </thead>
                    <tbody class="divide-y divide-slate-100">
                      <tr
                        v-for="row in tierRows"
                        :key="row.id"
                        class="group transition-colors"
                        :class="row.isChanged ? 'bg-[#fff9cc]' : 'hover:bg-slate-50'"
                      >
                        <td class="px-6 py-5">
                          <p class="text-sm font-bold">{{ row.name }}</p>
                          <p class="text-xs text-slate-400">{{ row.subtitle }}</p>
                        </td>
                        <td class="px-6 py-5">
                          <div class="flex items-center gap-3">
                            <span class="text-sm font-mono font-medium">{{ row.range }}</span>
                            <div class="h-1.5 w-24 bg-slate-100 rounded-full overflow-hidden">
                              <div
                                class="h-full rounded-full transition-all duration-500"
                                :class="row.progressClass"
                                :style="{ width: `${row.progressPercent}%` }"
                              />
                            </div>
                          </div>
                          <p class="mt-1 text-[10px] uppercase tracking-widest text-slate-400">Sold {{ row.soldSeats }}</p>
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
                            v-else-if="row.status === 'sold_out'"
                            class="inline-flex items-center gap-1 rounded-full bg-rose-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-tighter text-rose-700"
                          >
                            Sold Out
                          </span>
                          <span
                            v-else
                            class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-slate-100 text-slate-400 uppercase tracking-tighter"
                          >
                            Pending
                          </span>
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
                    <label class="mb-2 block text-[10px] font-black uppercase tracking-widest text-slate-400">Discount Percentage</label>
                    <input
                      v-model="discountPercentage"
                      type="number"
                      min="1"
                      max="100"
                      step="0.01"
                      class="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 outline-none transition-all focus:ring-2 focus:ring-[#ffd900]"
                    >
                  </div>

                  <div>
                    <label class="mb-2 block text-[10px] font-black uppercase tracking-widest text-slate-400">Duration (Minutes)</label>
                    <input
                      v-model="durationMinutes"
                      type="number"
                      min="1"
                      max="40320"
                      class="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 outline-none transition-all focus:ring-2 focus:ring-[#ffd900]"
                    >
                  </div>

                  <div>
                    <label class="mb-2 block text-[10px] font-black uppercase tracking-widest text-slate-400">Escalation Percentage</label>
                    <input
                      v-model="escalationPercentage"
                      type="number"
                      min="0"
                      max="500"
                      step="0.01"
                      class="w-full rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-700 outline-none transition-all focus:ring-2 focus:ring-[#ffd900]"
                    >
                  </div>

                  <div class="pt-2">
                    <label class="mb-2 block text-[10px] font-black uppercase tracking-widest text-slate-400">Resale Protection</label>
                    <div class="flex items-center justify-between">
                      <span class="text-sm font-medium text-slate-700">Show inventory bar to users</span>
                      <UiToggleSwitch :enabled="false" :disabled="true" />
                    </div>
                  </div>

                  <p class="text-[11px] uppercase tracking-wider text-slate-400">{{ unsupportedControlNote }}</p>
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

                  <button
                    class="w-full cursor-not-allowed pt-2 text-xs font-bold uppercase tracking-widest text-slate-400 opacity-60"
                    type="button"
                    disabled
                    :title="unsupportedControlNote"
                  >
                    Configure Integrations
                  </button>
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
                    <p class="text-3xl font-black text-slate-900">{{ systemHealth.activeSessions }}</p>
                  </div>
                  <div class="h-1 w-full rounded-full bg-slate-900/10">
                    <div class="h-full rounded-full bg-slate-900" :style="{ width: `${systemHealth.progressPercent}%` }" />
                  </div>
                  <p class="text-[10px] italic font-medium leading-relaxed text-slate-900/70">"{{ systemHealth.insight }}"</p>
                </div>
              </section>
            </div>
          </div>
        </section>
      </div>
    </div>
  </main>
</template>
