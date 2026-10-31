import { ref } from 'vue'
import { defineStore } from 'pinia'
import api from '../api/client'

export const useAuthStore = defineStore('auth', () => {
  const user = ref(null)
  const ready = ref(false)

  async function fetchMe() {
    try {
      const { data } = await api.get('/auth/me')
      user.value = data
    } catch {
      user.value = null
    } finally {
      ready.value = true
    }
    return user.value
  }

  async function login(email, password) {
    const { data } = await api.post('/auth/login', { email, password })
    user.value = data.user
    ready.value = true
  }

  async function register(payload) {
    await api.post('/auth/register', payload)
    await login(payload.email, payload.password)
  }

  async function createOrganization(name) {
    const { data } = await api.post('/auth/organization', { name })
    if (user.value) {
      user.value.org_id = data.organization.id
      user.value.org_name = data.organization.name
    }
    return data.organization
  }

  async function logout() {
    try { await api.post('/auth/logout') } finally { user.value = null }
  }

  return { user, ready, fetchMe, login, register, logout, createOrganization }
})
