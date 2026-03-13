import { createRouter, createWebHistory } from 'vue-router'
import MainLandingPage from '@/pages/MainLandingPage.vue'
import OrganiserDashboardPage from '@/pages/OrganiserDashboardPage.vue'

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
  ],
  scrollBehavior() {
    return { top: 0 }
  },
})

export default router
