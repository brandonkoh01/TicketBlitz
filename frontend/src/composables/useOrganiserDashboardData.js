import { computed, ref } from 'vue'
import { useRoleNavigation } from '@/composables/useRoleNavigation'

export function useOrganiserDashboardData() {
  const { dashboardPath } = useRoleNavigation()

  const navLinks = computed(() => [
    { icon: 'dashboard', label: 'Dashboard', to: dashboardPath.value },
    { icon: 'event', label: 'Events', to: '#' },
    { icon: 'trending_up', label: 'Sales Analytics', to: '#' },
    { icon: 'campaign', label: 'Marketing', to: '#' },
    { icon: 'group', label: 'Customers', to: '#' },
  ])

  const eventInfo = ref({
    venue: 'Studio Arena',
    organiserStatus: 'Verified Organiser',
    title: 'Flash Sale Setup',
    subtitle:
      'Configure automated ticket price increments based on inventory depletion. Once a threshold is reached, the next tier activates instantly.',
    eventName: 'Neon Nights 2026',
  })

  const tierRows = ref([
    {
      id: 1,
      name: 'Early Bird / First adopters special',
      inventoryRange: '0 - 50%',
      price: '$80.00',
      status: 'Active',
    },
    {
      id: 2,
      name: 'Phase 1 / General admission mid-tier',
      inventoryRange: '51 - 80%',
      price: '$120.00',
      status: 'Pending',
    },
    {
      id: 3,
      name: 'Last Chance / Final inventory pricing',
      inventoryRange: '81 - 100%',
      price: '$160.00',
      status: 'Pending',
    },
  ])

  const velocitySeries = ref([12, 24, 31, 42, 56, 72, 28, 9])

  const topMetrics = ref({
    revenue: '$12,480.00',
    sold: 156,
    capacity: 400,
    velocity: '+12%',
  })

  const saleConfig = ref([
    { id: 1, label: 'Max Tickets Per Order', description: 'Limit set to 6 tickets', enabled: true },
    { id: 2, label: 'Resale Protection', description: 'Transfer lock for 24h post-purchase', enabled: true },
    { id: 3, label: 'Identity Verification Required', description: 'Government ID checks at checkout', enabled: false },
    { id: 4, label: 'Countdown Display', description: 'Show inventory bar to users', enabled: true },
  ])

  const alerts = ref([
    { id: 1, icon: 'payments', title: 'Payout Alerts', detail: 'Every 10 tickets sold' },
    { id: 2, icon: 'trending_up', title: 'Tier Activation', detail: 'Instant push when price jumps' },
    { id: 3, icon: 'error', title: 'Inventory Low', detail: 'Notify when less than 5% remaining' },
  ])

  const systemHealth = ref({
    activeSessions: '1,204',
    insight:
      'Dynamic pricing is performing 22% better than static pre-sales for this time slot.',
  })

  // Pulled from Supabase metadata for project cpxcpvcfbohvpiubbujg.
  const databaseContext = ref({
    projectId: 'cpxcpvcfbohvpiubbujg',
    relevantPublicTables: ['public.test', 'public.community_posts', 'public.community_post_likes'],
    migrationSignals: ['add_glossary_term_with_definition_rpc', 'add_sanitisation_check_constraints_v2'],
    note: 'No organiser-specific ticketing tables were found in the current public schema snapshot.',
  })

  const activeTierCount = computed(() => tierRows.value.filter((row) => row.status === 'Active').length)

  const pendingTierCount = computed(() => tierRows.value.filter((row) => row.status === 'Pending').length)

  return {
    navLinks,
    eventInfo,
    tierRows,
    velocitySeries,
    topMetrics,
    saleConfig,
    alerts,
    systemHealth,
    databaseContext,
    activeTierCount,
    pendingTierCount,
  }
}
