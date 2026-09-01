import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      redirect: '/events',
    },
    {
      path: '/events',
      name: 'events',
      component: () => import('../views/EventGeneration.vue'),
      meta: { title: 'Coupled Event Detection' },
    },
    {
      path: '/risk',
      name: 'risk',
      component: () => import('../views/RiskCalculation.vue'),
      meta: { title: 'Risk Assessment' },
    },
  ],
})

router.afterEach((to) => {
  const title = typeof to.meta.title === 'string' ? to.meta.title : 'EQTyCatRisk'
  document.title = `${title} | EQTyCatRisk`
})

export default router
