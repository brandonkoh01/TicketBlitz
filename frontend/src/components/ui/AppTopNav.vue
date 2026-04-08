<script setup>
import { computed } from 'vue'
import { useAuthStore } from '@/stores/authStore'
import { useRoleNavigation } from '@/composables/useRoleNavigation'

const props = defineProps({
  pageLabel: {
    type: String,
    default: 'Main Page 01',
  },
  showSearch: {
    type: Boolean,
    default: true,
  },
})

const authStore = useAuthStore()
const isAuthenticated = computed(() => authStore.isAuthenticated.value)
const { primaryNavItems: navItems } = useRoleNavigation()
</script>

<template>
  <header class="border-b-4 border-black bg-white">
    <div class="mx-auto flex max-w-[1800px] items-center justify-between gap-4 px-6 py-5 md:px-10">
      <RouterLink to="/" class="block focus-visible:outline-none">
        <p class="text-sm font-black uppercase tracking-[0.28em]">TicketBlitz</p>
        <p class="text-[10px] font-medium uppercase tracking-[0.22em] text-black/65">{{ pageLabel }}</p>
      </RouterLink>

      <nav class="hidden items-center gap-6 lg:flex">
        <RouterLink
          v-for="item in navItems"
          :key="item.label"
          :to="item.to"
          class="swiss-link-slide text-xs font-black uppercase tracking-[0.2em] focus-visible:outline-none"
          :data-alt="item.label"
        >
          <span>{{ item.label }}</span>
        </RouterLink>
      </nav>

      <div class="flex items-center gap-3">
        <slot name="actions">
          <button
            v-if="props.showSearch"
            type="button"
            aria-label="Search"
            class="inline-flex h-11 w-11 items-center justify-center border-2 border-black text-lg font-black transition duration-200 ease-out hover:bg-black hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--swiss-accent)] focus-visible:ring-offset-2"
          >
            ⌕
          </button>

          <AuthSessionControls v-if="isAuthenticated" />
          <UiButton v-else to="/sign-in" variant="primary" class="min-w-[9rem]">Login</UiButton>
        </slot>
      </div>
    </div>
  </header>
</template>
