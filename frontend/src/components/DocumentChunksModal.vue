<script setup>
import { ref, watch } from 'vue'
import { useWorkspaceStore } from '../stores/workspace'

const props = defineProps({
  show: Boolean,
  docId: Number,
  docFilename: String
})

const emit = defineEmits(['close'])

const workspace = useWorkspaceStore()
const chunksData = ref(null)
const loading = ref(false)
const error = ref('')

watch(() => props.docId, async (newId) => {
  if (newId && props.show) {
    loading.value = true
    error.value = ''
    try {
      chunksData.value = await workspace.fetchDocumentChunks(newId)
    } catch (err) {
      error.value = err.message || 'Failed to fetch chunks.'
    } finally {
      loading.value = false
    }
  }
}, { immediate: true })
</script>

<template>
  <div v-if="show" class="drawer-backdrop" @click.self="emit('close')">
    <div class="drawer">
      <div class="drawer-head">
        <div>
          <span class="label gold">Ingestion Inspector</span>
          <h3>{{ docFilename || 'Document Chunks' }}</h3>
          <p class="meta" v-if="chunksData">
            Document ID: {{ docId }} · {{ chunksData.total_chunks }} Chunks Extracted & Embedded
          </p>
        </div>
        <button class="btn-close" @click="emit('close')" aria-label="Close">✕</button>
      </div>

      <div class="drawer-body">
        <div v-if="loading" class="loading-state">
          <div class="spinner"></div>
          <p>Loading chunks and extraction metadata…</p>
        </div>

        <div v-else-if="error" class="form-error">
          {{ error }}
        </div>

        <div v-else-if="chunksData?.chunks" class="chunks-list">
          <article v-for="c in chunksData.chunks" :key="c.chunk_index" class="chunk-card">
            <div class="chunk-meta">
              <span class="tag-idx">Chunk #{{ c.chunk_index }}</span>
              <span class="tag-page">Page {{ c.page_number }}</span>
              <span v-if="c.has_tables" class="tag-table">Tables Extracted</span>
              <span v-if="c.has_images" class="tag-image">Images Found</span>
            </div>
            <p class="chunk-text">{{ c.raw_text_preview }}</p>
          </article>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.drawer-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(20, 19, 15, 0.75);
  backdrop-filter: blur(8px);
  z-index: 100;
  display: flex;
  justify-content: flex-end;
}

.drawer {
  width: min(640px, 92vw);
  height: 100vh;
  background: var(--paper);
  border-left: 1px solid var(--hairline);
  box-shadow: -20px 0 60px rgba(10, 9, 6, 0.4);
  display: flex;
  flex-direction: column;
}

.drawer-head {
  padding: 24px 28px;
  border-bottom: 1px solid var(--hairline);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.drawer-head h3 {
  font-size: 1.4rem;
  margin-top: 4px;
  word-break: break-all;
}

.meta {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-faint);
  margin-top: 6px;
}

.btn-close {
  background: none;
  border: none;
  font-size: 18px;
  color: var(--ink-faint);
  cursor: pointer;
  padding: 4px 8px;
}
.btn-close:hover {
  color: var(--ink);
}

.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px;
}

.chunks-list {
  display: grid;
  gap: 16px;
}

.chunk-card {
  padding: 18px;
  background: rgba(26, 25, 23, 0.03);
  border: 1px solid var(--hairline);
  border-radius: 2px;
}

.chunk-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.tag-idx, .tag-page, .tag-table, .tag-image {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 2px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

.tag-idx {
  background: var(--olive);
  color: var(--paper);
}

.tag-page {
  background: rgba(26, 25, 23, 0.08);
  color: var(--ink);
}

.tag-table {
  background: rgba(194, 164, 92, 0.2);
  color: #7A6028;
  font-weight: 500;
}

.tag-image {
  background: rgba(201, 129, 87, 0.2);
  color: var(--copper);
}

.chunk-text {
  font-size: 13.5px;
  line-height: 1.6;
  color: var(--ink-soft);
  white-space: pre-wrap;
  font-family: var(--font-mono);
}

.loading-state {
  display: grid;
  place-items: center;
  padding: 60px 0;
  gap: 16px;
  color: var(--ink-faint);
}

.spinner {
  width: 32px;
  height: 32px;
  border: 2px solid var(--hairline-strong);
  border-top-color: var(--ink);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}
</style>
