import { createRouter, createWebHistory } from 'vue-router'
import MainLandingPage from '@/pages/MainLandingPage.vue'
import EventCatalogPage from '@/pages/EventCatalogPage.vue'
import EventDetailPage from '@/pages/EventDetailPage.vue'
import OrganiserDashboardPage from '@/pages/OrganiserDashboardPage.vue'
import TicketPurchasePage from '@/pages/TicketPurchasePage.vue'
import MyTicketsPage from '@/pages/MyTicketsPage.vue'
import BookingPendingPage from '@/pages/BookingPendingPage.vue'
import BookingResultPage from '@/pages/BookingResultPage.vue'
import WaitlistListPage from '@/pages/WaitlistListPage.vue'
import WaitlistStatusPage from '@/pages/WaitlistStatusPage.vue'
import WaitlistConfirmPage from '@/pages/WaitlistConfirmPage.vue'
import SignInPage from '@/pages/SignInPage.vue'
import SignUpPage from '@/pages/SignUpPage.vue'
import { useAuthStore } from '@/stores/authStore'

function normalizeInternalRedirect(target) {
  if (typeof target !== 'string') return '/'

  const trimmed = target.trim()
  if (!trimmed.startsWith('/')) return '/'
  if (trimmed.startsWith('//')) return '/'

  return trimmed
}

function resolveRoleHomePath(authStore) {
  return normalizeInternalRedirect(authStore.roleHomePath?.value)
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: MainLandingPage,
    },
    {
      path: '/events',
      name: 'events',
      component: EventCatalogPage,
    },
    {
      path: '/events/:eventID',
      name: 'event-detail',
      component: EventDetailPage,
    },
    {
      path: '/organiser-dashboard',
      name: 'organiser-dashboard',
      component: OrganiserDashboardPage,
      meta: {
        requiresAuth: true,
        allowedRoles: ['organiser'],
      },
    },
    {
      path: '/ticket-purchase',
      name: 'ticket-purchase',
      component: TicketPurchasePage,
      meta: {
        requiresAuth: true,
      },
    },
    {
      path: '/my-tickets',
      name: 'my-tickets',
      component: MyTicketsPage,
      meta: {
        requiresAuth: true,
        allowedRoles: ['fan'],
      },
    },
    {
      path: '/booking/pending/:holdID',
      name: 'booking-pending',
      component: BookingPendingPage,
      meta: {
        requiresAuth: true,
        allowedRoles: ['fan'],
      },
    },
    {
      path: '/booking/result/:holdID',
      name: 'booking-result',
      component: BookingResultPage,
      meta: {
        requiresAuth: true,
        allowedRoles: ['fan'],
      },
    },
    {
      path: '/waitlist',
      name: 'waitlist-list',
      component: WaitlistListPage,
      meta: {
        requiresAuth: true,
        allowedRoles: ['fan'],
      },
    },
    {
      path: '/waitlist/:waitlistID',
      name: 'waitlist-status',
      component: WaitlistStatusPage,
      meta: {
        requiresAuth: true,
        allowedRoles: ['fan'],
      },
    },
    {
      path: '/waitlist/confirm/:holdID',
      name: 'waitlist-confirm',
      component: WaitlistConfirmPage,
      meta: {
        requiresAuth: true,
        allowedRoles: ['fan'],
      },
    },
    {
      path: '/sign-in',
      name: 'sign-in',
      component: SignInPage,
      meta: {
        guestOnly: true,
      },
    },
    {
      path: '/sign-up',
      name: 'sign-up',
      component: SignUpPage,
      meta: {
        guestOnly: true,
      },
    },
  ],
  scrollBehavior() {
    return { top: 0 }
  },
})

router.beforeEach(async (to) => {
  const authStore = useAuthStore()
  await authStore.initializeAuthStore()

  if (!authStore.authEnabled) {
    if (to.meta.requiresAuth) {
      return {
        name: 'sign-in',
        query: {
          redirect: normalizeInternalRedirect(to.fullPath),
        },
      }
    }

    return true
  }

  const isAuthenticated = authStore.isAuthenticated.value
  const roleHomePath = resolveRoleHomePath(authStore)

  if (to.meta.requiresAuth && !isAuthenticated) {
    return {
      name: 'sign-in',
      query: {
        redirect: normalizeInternalRedirect(to.fullPath),
      },
    }
  }

  if (to.meta.guestOnly && isAuthenticated) {
    const queryRedirect = normalizeInternalRedirect(to.query.redirect)

    if (queryRedirect === '/sign-in' || queryRedirect === '/sign-up' || queryRedirect === '/') {
      return roleHomePath
    }

    return queryRedirect
  }

  if (to.meta.requiresAuth && isAuthenticated) {
    const allowedRoles = Array.isArray(to.meta.allowedRoles) ? to.meta.allowedRoles : []
    const currentRole = typeof authStore.currentRole?.value === 'string' ? authStore.currentRole.value : 'fan'

    if (allowedRoles.length > 0 && !allowedRoles.includes(currentRole)) {
      return roleHomePath
    }
  }

  return true
})

export default router
