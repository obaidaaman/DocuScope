<script setup>
import { ref, computed } from 'vue'
import { useWorkspaceStore } from '../stores/workspace'
import { useAuthStore } from '../stores/auth'

const props = defineProps({
  onOpenChunks: {
    type: Function,
    default: () => {}
  },
  onProceedToReconcile: {
    type: Function,
    default: () => {}
  }
})

const emit = defineEmits(['open-new-project-modal'])

const workspace = useWorkspaceStore()
const auth = useAuthStore()

// UI State
const searchQuery = ref('')
const isDragging = ref(false)
const fileInput = ref(null)
const liveFileInput = ref(null)

// Organization creation state
const orgNameInput = ref('')
const creatingOrg = ref(false)
const orgError = ref('')

const hasOrg = computed(() => Boolean(auth.user?.org_id))

const greeting = computed(() => {
  const hr = new Date().getHours()
  if (hr < 12) return 'Good morning'
  if (hr < 17) return 'Good afternoon'
  return 'Good evening'
})

const filteredDocs = computed(() => {
  const docs = workspace.currentDocs || []
  if (!searchQuery.value.trim()) return docs
  const q = searchQuery.value.toLowerCase()
  return docs.filter(d => d.filename.toLowerCase().includes(q))
})

async function handleCreateOrg() {
  if (!orgNameInput.value.trim()) {
    orgError.value = 'Please enter an organization name.'
    return
  }
  creatingOrg.value = true
  orgError.value = ''
  try {
    await auth.createOrganization(orgNameInput.value.trim())
    orgNameInput.value = ''
    await workspace.fetchProjects()
  } catch (err) {
    orgError.value = err?.response?.data?.detail || err.message || 'Failed to create organization'
  } finally {
    creatingOrg.value = false
  }
}

function openFileDialog() {
  if (!hasOrg.value) {
    workspace.actionError = 'Please create an organization first.'
    return
  }
  if (!workspace.currentProjectId) {
    emit('open-new-project-modal')
    return
  }
  fileInput.value?.click()
}

async function onFilesSelected(event) {
  const files = Array.from(event.target.files || [])
  if (files.length) {
    await workspace.uploadDocuments(files)
  }
  if (event.target) event.target.value = ''
}

async function onDropFiles(event) {
  isDragging.value = false
  if (!hasOrg.value || !workspace.currentProjectId) return
  const files = Array.from(event.dataTransfer?.files || [])
  if (files.length) {
    await workspace.uploadDocuments(files)
  }
}

function triggerLivePipelineUpload() {
  if (!hasOrg.value) {
    workspace.actionError = 'Please create an organization first.'
    return
  }
  if (!workspace.currentProjectId) {
    emit('open-new-project-modal')
    return
  }
  liveFileInput.value?.click()
}

async function onLiveFilesSelected(event) {
  const files = Array.from(event.target.files || [])
  if (files.length >= 2) {
    props.onProceedToReconcile('reconcile')
    await workspace.startLivePipeline(files, (nextTab) => {
      props.onProceedToReconcile(nextTab)
    })
  } else if (files.length === 1) {
    workspace.actionError = 'Live reconciliation requires at least 2 PDF documents.'
  }
  if (event.target) event.target.value = ''
}

async function triggerLiveReconciliationOnSelected() {
  if (workspace.selectedDocIds.length < 2) {
    workspace.actionError = 'Please select at least 2 documents to reconcile.'
    return
  }
  props.onProceedToReconcile('reconcile')
  await workspace.startLiveReconciliation((nextTab) => {
    props.onProceedToReconcile(nextTab)
  })
}

function toggleDocSelection(docId) {
  const idx = workspace.selectedDocIds.indexOf(docId)
  if (idx > -1) {
    workspace.selectedDocIds.splice(idx, 1)
  } else {
    workspace.selectedDocIds.push(docId)
  }
}

function selectAllParsed() {
  workspace.selectedDocIds = workspace.parsedDocs.map(d => d.id)
}

function deselectAll() {
  workspace.selectedDocIds = []
}
</script>

<template>
  <div class="studio-home">
    <!-- Greeting Header (Reducto Studio style) -->
    <div class="studio-greeting">
      <h1>{{ greeting }}, {{ auth.user?.first_name || 'there' }}.</h1>
    </div>

    <!-- 1. Organization Setup (if none) -->
    <div v-if="!hasOrg" class="org-setup-card">
      <div>
        <span class="label muted">Step 1 · Organization</span>
        <h3>Set up your workspace organization</h3>
        <p class="muted">Create your organization to start creating projects and reconciling documents.</p>
      </div>
      <form class="org-form" @submit.prevent="handleCreateOrg">
        <input
          v-model="orgNameInput"
          type="text"
          placeholder="Organization Name (e.g., Horizon Logistics Corp)"
          class="input"
        />
        <button
          type="submit"
          class="btn btn-ink sm"
          :disabled="creatingOrg || !orgNameInput.trim()"
        >
          {{ creatingOrg ? 'Creating…' : 'Create Organization' }}
        </button>
      </form>
      <p v-if="orgError" class="form-error">{{ orgError }}</p>
    </div>

    <!-- 2. Main Studio Home Content -->
    <template v-else>
      <!-- Single-Row Drop Strip (exact Reducto Studio Home drop bar) -->
      <div
        class="drop-strip"
        :class="{ dragging: isDragging }"
        @dragover.prevent="isDragging = true"
        @dragleave.prevent="isDragging = false"
        @drop.prevent="onDropFiles"
      >
        <div class="drop-strip-left" @click="openFileDialog">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M8 3v10M3 8h10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/>
          </svg>
          <span>
            Drop PDF documents to parse into
            <strong>{{ workspace.currentProject?.name || 'a project' }}</strong>
          </span>
        </div>

        <div class="drop-strip-actions">
          <button
            class="btn-studio-ghost"
            :disabled="workspace.isUploading"
            @click="openFileDialog"
          >
            {{ workspace.isUploading ? 'Uploading…' : 'Choose files' }}
          </button>
          <button
            class="btn-studio-ghost"
            :disabled="workspace.livePipelineActive"
            @click="triggerLivePipelineUpload"
          >
            {{ workspace.livePipelineActive ? 'Running…' : 'Upload & Reconcile' }}
          </button>
        </div>

        <input
          ref="fileInput"
          type="file"
          multiple
          accept=".pdf"
          class="hidden-input"
          @change="onFilesSelected"
        />
        <input
          ref="liveFileInput"
          type="file"
          multiple
          accept=".pdf"
          class="hidden-input"
          @change="onLiveFilesSelected"
        />
      </div>

      <!-- Filter & Action Toolbar Row -->
      <div class="studio-toolbar">
        <div class="toolbar-left">
          <select
            v-if="workspace.projects.length"
            class="filter-pill"
            :value="workspace.currentProjectId"
            @change="(e) => workspace.selectProject(Number(e.target.value))"
            aria-label="Active project"
          >
            <option v-for="p in workspace.projects" :key="p.id" :value="p.id">
              {{ p.name }} ({{ p.documents?.length || 0 }})
            </option>
          </select>

          <div class="search-wrap">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <circle cx="7" cy="7" r="4.8" stroke="currentColor" stroke-width="1.4"/>
              <path d="M10.8 10.8L14 14" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/>
            </svg>
            <input
              v-model="searchQuery"
              type="text"
              placeholder="Search files…"
              class="search-bare"
            />
          </div>

          <button
            v-if="workspace.parsedDocs.length"
            class="filter-btn"
            @click="selectAllParsed"
          >
            Select all ({{ workspace.parsedDocs.length }})
          </button>
          <button
            v-if="workspace.selectedDocIds.length"
            class="filter-btn"
            @click="deselectAll"
          >
            Clear
          </button>
          <button
            class="filter-btn"
            @click="workspace.fetchProjects()"
            title="Refresh project documents"
          >
            Refresh
          </button>
        </div>

        <div class="toolbar-right">
          <button
            v-if="workspace.selectedDocIds.length >= 2"
            class="btn-studio-black"
            :disabled="workspace.livePipelineActive"
            @click="triggerLiveReconciliationOnSelected"
          >
            {{ workspace.livePipelineActive ? 'Reconciling…' : `Reconcile (${workspace.selectedDocIds.length})` }}
          </button>
          <button
            class="btn-studio-black"
            @click="emit('open-new-project-modal')"
          >
            + Create project
          </button>
        </div>
      </div>

      <!-- Empty State: No Project -->
      <div v-if="!workspace.currentProject" class="studio-empty">
        <p class="empty-title">No project selected</p>
        <p class="muted">Create your first project to upload PDFs and detect cross-document conflicts.</p>
        <button class="btn-studio-black" style="margin-top: 12px" @click="emit('open-new-project-modal')">
          + Create project
        </button>
      </div>

      <!-- Empty State: No Documents -->
      <div v-else-if="!workspace.currentDocs.length" class="studio-empty">
        <p class="empty-title">No documents in {{ workspace.currentProject.name }}</p>
        <p class="muted">Drop 2 or more PDF files in the bar above to parse and reconcile them.</p>
      </div>

      <!-- Clean Minimalist Table (Reducto Studio Style) -->
      <div v-else class="studio-table-wrap">
        <table class="studio-table">
          <thead>
            <tr>
              <th style="width: 36px"></th>
              <th>Document</th>
              <th>Pipeline</th>
              <th>Status</th>
              <th>ID</th>
              <th style="text-align: right">Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="doc in filteredDocs"
              :key="doc.id"
              :class="{ selected: workspace.selectedDocIds.includes(doc.id) }"
              @click="doc.status === 'PARSED' && toggleDocSelection(doc.id)"
            >
              <td @click.stop>
                <input
                  type="checkbox"
                  :checked="workspace.selectedDocIds.includes(doc.id)"
                  :disabled="doc.status !== 'PARSED'"
                  @change="toggleDocSelection(doc.id)"
                />
              </td>
              <td class="doc-name-cell">{{ doc.filename }}</td>
              <td>
                <span class="steps-chip">
                  <span>Parse</span>
                  <span class="steps-arrow">→</span>
                  <span>Extract</span>
                  <span class="steps-arrow">→</span>
                  <span>Judge</span>
                </span>
              </td>
              <td>
                <span class="status-pill" :class="doc.status.toLowerCase()">
                  <span class="s-dot"></span>
                  {{ doc.status }}
                </span>
              </td>
              <td class="mono-muted">#{{ doc.id }}</td>
              <td class="actions-cell" @click.stop>
                <button
                  v-if="doc.status === 'FAILED'"
                  class="row-action danger"
                  @click="workspace.retryDocument(doc.id)"
                >
                  Retry
                </button>
                <button
                  v-if="doc.status === 'PARSED'"
                  class="row-action"
                  @click="onOpenChunks(doc.id)"
                >
                  Inspect chunks
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<style scoped>
.studio-home {
  display: flex;
  flex-direction: column;
  gap: 24px;
  max-width: 980px;
  margin: 0 auto;
  width: 100%;
  padding-top: 12px;
}

.studio-greeting h1 {
  font-family: var(--font-body);
  font-size: clamp(1.65rem, 2.6vw, 2.05rem);
  font-weight: 500;
  letter-spacing: -0.025em;
  color: var(--ink);
}

/* Org Setup */
.org-setup-card {
  border: 1px solid var(--hairline);
  border-radius: var(--radius-md);
  background: var(--paper);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.org-setup-card h3 {
  font-size: 1.15rem;
  font-weight: 600;
  margin: 4px 0;
}
.org-form {
  display: flex;
  gap: 10px;
  max-width: 520px;
}
.org-form .input { flex: 1; }

/* Single-Row Drop Strip */
.drop-strip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 13px 16px;
  border: 1px dashed var(--hairline-strong);
  border-radius: var(--radius-md);
  background: var(--surface);
  transition: border-color 0.18s ease, background 0.18s ease;
  flex-wrap: wrap;
}
.drop-strip:hover,
.drop-strip.dragging {
  border-color: var(--ink);
  background: var(--paper);
}
.drop-strip-left {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 13.5px;
  color: var(--ink-soft);
  cursor: pointer;
}
.drop-strip-left strong {
  color: var(--ink);
  font-weight: 500;
}
.drop-strip-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.btn-studio-ghost {
  background: var(--surface);
  color: var(--ink);
  border: 1px solid var(--hairline);
  border-radius: 7px;
  padding: 6px 12px;
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.btn-studio-ghost:hover:not(:disabled) {
  border-color: var(--hairline-strong);
  background: var(--paper);
}
.btn-studio-ghost:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.hidden-input { display: none; }

/* Toolbar */
.studio-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.toolbar-left,
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.filter-pill {
  border: 1px solid var(--hairline);
  background: var(--surface);
  color: var(--ink);
  border-radius: 7px;
  padding: 6px 10px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
}
.filter-pill:focus {
  outline: none;
  border-color: var(--ink);
}
.search-wrap {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  border: 1px solid var(--hairline);
  border-radius: 7px;
  color: var(--ink-faint);
  background: var(--surface);
}
.search-wrap:focus-within {
  border-color: var(--ink);
  color: var(--ink);
}
.search-bare {
  border: none;
  outline: none;
  font-size: 13px;
  color: var(--ink);
  background: transparent;
  width: 140px;
}
.filter-btn {
  border: 1px solid var(--hairline);
  background: var(--surface);
  color: var(--ink-soft);
  border-radius: 7px;
  padding: 6px 10px;
  font-size: 12.5px;
  cursor: pointer;
  transition: color 0.15s, border-color 0.15s;
}
.filter-btn:hover {
  color: var(--ink);
  border-color: var(--hairline-strong);
}

.btn-studio-black {
  background: var(--dark);
  color: #FFFFFF;
  border: 1px solid var(--dark);
  border-radius: 7px;
  padding: 7px 14px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, transform 0.15s;
}
.btn-studio-black:hover:not(:disabled) {
  background: var(--dark-2);
  transform: translateY(-1px);
}
.btn-studio-black:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* Minimalist Table */
.studio-table-wrap {
  overflow-x: auto;
}
.studio-table {
  width: 100%;
  border-collapse: collapse;
}
.studio-table th {
  font-size: 12px;
  font-weight: 500;
  color: var(--ink-faint);
  text-align: left;
  padding: 10px 10px;
  border-bottom: 1px solid var(--hairline);
}
.studio-table td {
  padding: 14px 10px;
  font-size: 13.5px;
  color: var(--ink);
  border-bottom: 1px solid #F1F1F3;
  vertical-align: middle;
}
.studio-table tbody tr {
  cursor: pointer;
  transition: background 0.14s ease;
}
.studio-table tbody tr:hover {
  background: var(--paper);
}
.studio-table tbody tr.selected {
  background: #F4F4F5;
}
.doc-name-cell {
  font-weight: 500;
}
.steps-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  background: var(--paper-deep);
  border: 1px solid var(--hairline);
  border-radius: 6px;
  padding: 3px 9px;
  font-size: 11.5px;
  color: var(--ink-soft);
}
.steps-arrow {
  color: var(--ink-faint);
}
.status-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 500;
  padding: 3px 9px;
  border-radius: 999px;
  text-transform: uppercase;
}
.s-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.status-pill.parsed {
  background: var(--success-soft);
  color: var(--success);
}
.status-pill.processing,
.status-pill.queued {
  background: var(--paper-deep);
  color: var(--ink);
}
.status-pill.processing .s-dot {
  animation: pulse 1.2s infinite;
}
.status-pill.failed {
  background: var(--danger-soft);
  color: var(--danger);
}
.mono-muted {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--ink-faint);
}
.actions-cell {
  text-align: right;
  white-space: nowrap;
}
.row-action {
  background: none;
  border: none;
  font-size: 12.5px;
  font-weight: 500;
  color: var(--ink-soft);
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 5px;
  transition: background 0.14s, color 0.14s;
}
.row-action:hover {
  background: var(--paper-deep);
  color: var(--ink);
}
.row-action.danger {
  color: var(--danger);
}

.studio-empty {
  text-align: center;
  padding: 56px 20px;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-md);
  background: var(--paper);
}
.empty-title {
  font-size: 15px;
  font-weight: 500;
  color: var(--ink);
  margin-bottom: 4px;
}
.muted {
  color: var(--ink-faint);
  font-size: 13.5px;
}
</style>
