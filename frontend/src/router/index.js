import { createRouter, createWebHistory } from 'vue-router'
import MainLandingPage from '@/pages/MainLandingPage.vue'
import OrganiserDashboardPage from '@/pages/OrganiserDashboardPage.vue'
import TicketPurchasePage from '@/pages/TicketPurchasePage.vue'

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
    },
    {
      path: '/ticket-purchase',
      name: 'ticket-purchase',
      component: TicketPurchasePage,
    },
  ],
  scrollBehavior() {
    return { top: 0 }
  },
})

export default router
