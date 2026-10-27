<script setup>
import { ref } from 'vue'

const props = defineProps({
  show: Boolean,
  userOrgId: [Number, String]
})

const emit = defineEmits(['close', 'create'])

const projectName = ref('')
const error = ref('')
const loading = ref(false)

function handleClose() {
  projectName.value = ''
  error.value = ''
  emit('close')
}

async function handleCreate() {
  if (!projectName.value.trim()) {
    error.value = 'Please provide a project name.'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await emit('create', projectName.value.trim())
    handleClose()
  } catch (err) {
    error.value = err.message || 'Failed to create project.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div v-if="show" class="modal-backdrop" @click.self="handleClose">
    <div class="modal-card">
      <div class="modal-head">
        <div>
          <span class="label gold">Workspace</span>
          <h3>New Project</h3>
        </div>
        <button class="btn-close" @click="handleClose" aria-label="Close">✕</button>
      </div>

      <form @submit.prevent="handleCreate" class="modal-body">
        <div v-if="error" class="form-error">{{ error }}</div>

        <div class="field">
          <label for="project-name">Project Name</label>
          <input
            id="project-name"
            v-model="projectName"
            class="input"
            placeholder="e.g., Q3 Vendor MSA & Invoices Audit"
            autofocus
            required
          />
        </div>

        <div class="modal-foot">
          <button type="button" class="btn btn-outline" @click="handleClose">Cancel</button>
          <button type="submit" class="btn btn-ink" :disabled="loading || !projectName.trim()">
            {{ loading ? 'Creating…' : 'Create Project' }}
          </button>
        </div>
      </form>
    </div>
  </div>
</template>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(20, 19, 15, 0.75);
  backdrop-filter: blur(8px);
  z-index: 100;
  display: grid;
  place-items: center;
  padding: 20px;
}

.modal-card {
  width: min(480px, 100%);
  background: var(--paper);
  border: 1px solid var(--hairline);
  box-shadow: 0 24px 60px rgba(10, 9, 6, 0.4);
  display: grid;
  gap: 20px;
  padding: 28px;
}

.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.modal-head h3 {
  font-size: 1.5rem;
  margin-top: 4px;
}

.btn-close {
  background: none;
  border: none;
  font-size: 16px;
  color: var(--ink-faint);
  cursor: pointer;
  padding: 4px 8px;
}

.btn-close:hover {
  color: var(--ink);
}

.modal-body {
  display: grid;
  gap: 18px;
}

.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 10px;
}
</style>
