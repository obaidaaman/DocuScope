<script setup>
import { ref } from 'vue'

const props = defineProps({
  show: Boolean,
  item: Object
})

const emit = defineEmits(['close', 'resolve'])

const customText = ref('')
const loading = ref(false)
const error = ref('')

function handleClose() {
  customText.value = ''
  error.value = ''
  emit('close')
}

async function handleResolve() {
  if (!customText.value.trim()) {
    error.value = 'Please enter the custom clause text to commit.'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await emit('resolve', {
      reviewItemId: props.item.id,
      action: 'CUSTOM_RESOLUTION',
      customText: customText.value.trim()
    })
    handleClose()
  } catch (err) {
    error.value = err.message || 'Failed to resolve review item.'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div v-if="show && item" class="modal-backdrop" @click.self="handleClose">
    <div class="modal-card">
      <div class="modal-head">
        <div>
          <span class="label gold">Human Review Gate</span>
          <h3>Custom Contractual Resolution</h3>
          <p class="topic-meta">{{ item.category }}</p>
        </div>
        <button class="btn-close" @click="handleClose" aria-label="Close">✕</button>
      </div>

      <div class="summary-box">
        <span class="label faint">Disagreement Summary</span>
        <p>{{ item.summary }}</p>
      </div>

      <form @submit.prevent="handleResolve" class="modal-body">
        <div v-if="error" class="form-error">{{ error }}</div>

        <div class="field">
          <label for="custom-clause">Final Agreed Clause Text (To be Committed)</label>
          <textarea
            id="custom-clause"
            v-model="customText"
            class="input textarea"
            rows="5"
            placeholder="Type the authoritative, reconciled contractual text to be included in the deliverable brief…"
            required
            autofocus
          ></textarea>
        </div>

        <div class="modal-foot">
          <button type="button" class="btn btn-outline" @click="handleClose">Cancel</button>
          <button type="submit" class="btn btn-ink" :disabled="loading || !customText.trim()">
            {{ loading ? 'Saving…' : 'Commit Custom Clause' }}
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
  width: min(600px, 100%);
  background: var(--paper);
  border: 1px solid var(--hairline);
  box-shadow: 0 24px 60px rgba(10, 9, 6, 0.4);
  display: grid;
  gap: 18px;
  padding: 28px;
}

.modal-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.modal-head h3 {
  font-size: 1.4rem;
  margin-top: 4px;
}

.topic-meta {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--copper);
  margin-top: 4px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
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

.summary-box {
  padding: 14px 16px;
  background: rgba(26, 25, 23, 0.04);
  border-left: 2px solid var(--copper);
  font-size: 13.5px;
  line-height: 1.5;
  display: grid;
  gap: 6px;
}

.modal-body {
  display: grid;
  gap: 16px;
}

.textarea {
  resize: vertical;
  line-height: 1.5;
  font-family: var(--font-body);
}

.modal-foot {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 6px;
}
</style>
