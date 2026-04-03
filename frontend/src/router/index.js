import { createRouter, createWebHistory } from 'vue-router'
import MainLandingPage from '@/pages/MainLandingPage.vue'
import OrganiserDashboardPage from '@/pages/OrganiserDashboardPage.vue'
import TicketPurchasePage from '@/pages/TicketPurchasePage.vue'
import MyTicketsPage from '@/pages/MyTicketsPage.vue'
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

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: MainLandingPage,
    },
    {
      path: '/organiser-dashboard',
      name: 'organiser-dashboard',
      component: OrganiserDashboardPage,
      meta: {
        requiresAuth: true,
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

    if (queryRedirect === '/sign-in' || queryRedirect === '/sign-up') {
      return '/'
    }

    return queryRedirect
  }

  return true
})

export default router
