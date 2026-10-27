import { createRouter, createWebHistory } from 'vue-router'
import LandingView from '../views/LandingView.vue'
import LoginView from '../views/LoginView.vue'
import SignupView from '../views/SignupView.vue'
import AppView from '../views/AppView.vue'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', name: 'landing', component: LandingView },
    { path: '/login', name: 'login', component: LoginView, meta: { guestOnly: true } },
    { path: '/signup', name: 'signup', component: SignupView, meta: { guestOnly: true } },
    { path: '/app', name: 'app', component: AppView, meta: { requiresAuth: true } },
  ],
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.ready) await auth.fetchMe()
  if (to.meta.requiresAuth && !auth.user) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.meta.guestOnly && auth.user) return { name: 'app' }
})

export default router
