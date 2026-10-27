<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import AuthLayout from '../components/AuthLayout.vue'
import { useAuthStore } from '../stores/auth'
import { errorMessage } from '../api/client'

const auth = useAuthStore()
const router = useRouter()

const form = ref({ first_name: '', last_name: '', email: '', password: '', phone: '', org_name: '' })
const showPw = ref(false)
const loading = ref(false)
const error = ref('')

const valid = computed(() =>
  form.value.first_name.trim() && form.value.last_name.trim() &&
  /^\S+@\S+\.\S+$/.test(form.value.email.trim()) && form.value.password.length >= 8
)

async function submit() {
  error.value = ''
  loading.value = true
  try {
    const f = form.value
    await auth.register({
      first_name: f.first_name.trim(),
      last_name: f.last_name.trim(),
      email: f.email.trim(),
      password: f.password,
      phone: f.phone.trim() || null,
      org_name: f.org_name.trim() || null,
    })
    router.push('/app')
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
        <h1>Create your <span class="serif-accent">account</span></h1>
        <p class="sub">Start tracing every claim in your documents.</p>
      </div>

      <form class="form" @submit.prevent="submit" novalidate>
        <div v-if="error" class="form-error" role="alert" id="signup-error">{{ error }}</div>

        <div class="grid-2">
          <div class="field">
            <label for="signup-first">First name</label>
            <input id="signup-first" v-model="form.first_name" class="input" autocomplete="given-name" required autofocus />
          </div>
          <div class="field">
            <label for="signup-last">Last name</label>
            <input id="signup-last" v-model="form.last_name" class="input" autocomplete="family-name" required />
          </div>
        </div>

        <div class="field">
          <label for="signup-email">Work email</label>
          <input id="signup-email" v-model="form.email" class="input" type="email" autocomplete="email" placeholder="you@company.com" required />
        </div>

        <div class="field">
          <label for="signup-password">Password</label>
          <div class="pw">
            <input id="signup-password" v-model="form.password" class="input" :type="showPw ? 'text' : 'password'" autocomplete="new-password" placeholder="At least 8 characters" required />
            <button type="button" id="signup-toggle-pw" @click="showPw = !showPw">{{ showPw ? 'Hide' : 'Show' }}</button>
          </div>
        </div>

        <div class="grid-2">
          <div class="field">
            <label for="signup-org">Organization <i>(optional)</i></label>
            <input id="signup-org" v-model="form.org_name" class="input" autocomplete="organization" />
          </div>
          <div class="field">
            <label for="signup-phone">Phone <i>(optional)</i></label>
            <input id="signup-phone" v-model="form.phone" class="input" type="tel" autocomplete="tel" />
          </div>
        </div>

        <button id="signup-submit" class="btn btn-ink btn-block" type="submit" :disabled="loading || !valid">
          {{ loading ? 'Creating account…' : 'Create account' }}
        </button>
      </form>

      <p class="switch">Already have an account? <RouterLink to="/login" id="signup-to-login">Log in</RouterLink></p>
    </div>
  </AuthLayout>
</template>
