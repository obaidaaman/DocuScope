<script setup>
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import AuthLayout from '../components/AuthLayout.vue'
import { useAuthStore } from '../stores/auth'
import { errorMessage } from '../api/client'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const email = ref('')
const password = ref('')
const showPw = ref(false)
const loading = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(email.value.trim(), password.value)
    router.push(route.query.redirect || '/app')
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <AuthLayout>
    <div class="auth-card">
      <div>
        <h1>Welcome <span class="serif-accent">back</span></h1>
        <p class="sub">Log in to continue reconciling your documents.</p>
      </div>

      <form class="form" @submit.prevent="submit" novalidate>
        <div v-if="error" class="form-error" role="alert" id="login-error">{{ error }}</div>

        <div class="field">
          <label for="login-email">Email</label>
          <input id="login-email" v-model="email" class="input" type="email" autocomplete="email" placeholder="you@company.com" required autofocus />
        </div>

        <div class="field">
          <label for="login-password">Password</label>
          <div class="pw">
            <input id="login-password" v-model="password" class="input" :type="showPw ? 'text' : 'password'" autocomplete="current-password" placeholder="Your password" required />
            <button type="button" id="login-toggle-pw" @click="showPw = !showPw">{{ showPw ? 'Hide' : 'Show' }}</button>
          </div>
        </div>

        <button id="login-submit" class="btn btn-ink btn-block" type="submit" :disabled="loading || !email || !password">
          {{ loading ? 'Logging in…' : 'Log in' }}
        </button>
      </form>

      <p class="switch">New to SuperDocs? <RouterLink to="/signup" id="login-to-signup">Create an account</RouterLink></p>
    </div>
  </AuthLayout>
</template>
