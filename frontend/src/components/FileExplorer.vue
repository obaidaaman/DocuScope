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

const orgDisplayName = computed(() => {
  return auth.user?.org_name || (hasOrg.value ? `Organization #${auth.user.org_id}` : 'No Organization')
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
  <div class="simple-dashboard">
    <!-- 1. Organization Section -->
    <div v-if="!hasOrg" class="org-setup-card frame">
      <div class="org-setup-info">
        <span class="label gold">Step 1 · Organization Required</span>
        <h3>Set Up Your Organization</h3>
        <p class="soft">Create your organization to start creating projects and uploading documents.</p>
      </div>
      <form class="org-form" @submit.prevent="handleCreateOrg">
        <input
          v-model="orgNameInput"
          type="text"
          placeholder="Organization Name (e.g., Apex Logistics Corp)"
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

    <!-- 2. Main Layout: Sidebar (Org + Projects) & Content (Documents) -->
    <div v-else class="workspace-grid">
      <!-- Left Column: Organization & Projects -->
      <aside class="sidebar-panel frame">
        <div class="org-summary">
          <span class="label faint">Organization</span>
          <div class="org-name">{{ orgDisplayName }}</div>
        </div>

        <div class="projects-section">
          <div class="section-head">
            <span class="label faint">Projects ({{ workspace.projects.length }})</span>
            <button class="btn-link-gold" @click="emit('open-new-project-modal')">+ New</button>
          </div>

          <div v-if="!workspace.projects.length" class="empty-projects">
            <p>No projects yet.</p>
            <button class="btn btn-ink sm" @click="emit('open-new-project-modal')">
              Create First Project
            </button>
          </div>

          <ul v-else class="project-list">
            <li
              v-for="p in workspace.projects"
              :key="p.id"
              class="project-item"
              :class="{ active: workspace.currentProjectId === p.id }"
              @click="workspace.selectProject(p.id)"
            >
              <span class="project-item-name">{{ p.name }}</span>
              <span class="project-item-count">{{ p.documents?.length || 0 }}</span>
            </li>
          </ul>
        </div>
      </aside>

      <!-- Right Column: Documents in Selected Project -->
      <div class="docs-panel frame">
        <!-- Empty state if no project is selected -->
        <div v-if="!workspace.currentProject" class="empty-docs">
          <h3>Select or Create a Project</h3>
          <p class="soft">Choose a project on the left or create a new one to manage its documents.</p>
          <button class="btn btn-ink sm" @click="emit('open-new-project-modal')">
            + New Project
          </button>
        </div>

        <template v-else>
          <!-- Project Header & Upload Actions -->
          <div class="docs-header">
            <div>
              <span class="label gold">Active Project</span>
              <h3>{{ workspace.currentProject.name }}</h3>
            </div>

            <div class="docs-actions">
              <button
                class="btn btn-outline sm"
                :disabled="workspace.isUploading"
                @click="openFileDialog"
              >
                {{ workspace.isUploading ? 'Uploading…' : '+ Upload PDFs' }}
              </button>

              <button
                class="btn btn-ink sm"
                :disabled="workspace.livePipelineActive"
                @click="triggerLivePipelineUpload"
              >
                {{ workspace.livePipelineActive ? 'Running Pipeline…' : 'Upload & Reconcile ⚡' }}
              </button>

              <button
                class="btn btn-outline sm"
                @click="workspace.fetchProjects()"
                title="Refresh"
              >
                Refresh
              </button>

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
          </div>

          <!-- Simple Dropzone -->
          <div
            class="dropzone"
            :class="{ dragging: isDragging }"
            @dragover.prevent="isDragging = true"
            @dragleave.prevent="isDragging = false"
            @drop.prevent="onDropFiles"
            @click="openFileDialog"
          >
            <span>Drop PDF documents here or <u>click to browse</u></span>
          </div>

          <!-- Documents List -->
          <div v-if="workspace.currentDocs.length" class="docs-list-section">
            <div class="docs-toolbar">
              <div class="selection-bar">
                <span>
                  <b>{{ workspace.selectedDocIds.length }}</b> of {{ workspace.currentDocs.length }} selected
                </span>
                <button class="btn-text" @click="selectAllParsed">Select all parsed</button>
                <button v-if="workspace.selectedDocIds.length" class="btn-text" @click="deselectAll">
                  Clear
                </button>
              </div>

              <input
                v-model="searchQuery"
                type="text"
                placeholder="Filter documents…"
                class="search-input"
              />
            </div>

            <div class="table-wrap">
              <table class="docs-table">
                <thead>
                  <tr>
                    <th style="width: 36px;">
                      <input
                        type="checkbox"
                        :checked="workspace.selectedDocIds.length === workspace.parsedDocs.length && workspace.parsedDocs.length > 0"
                        @change="workspace.selectedDocIds.length === workspace.parsedDocs.length ? deselectAll() : selectAllParsed()"
                      />
                    </th>
                    <th>Document</th>
                    <th>Status</th>
                    <th>Chunks</th>
                    <th>Date</th>
                    <th style="text-align: right;">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr
                    v-for="doc in filteredDocs"
                    :key="doc.id"
                    :class="{ selected: workspace.selectedDocIds.includes(doc.id) }"
                    @click="toggleDocSelection(doc.id)"
                  >
                    <td @click.stop>
                      <input
                        type="checkbox"
                        :checked="workspace.selectedDocIds.includes(doc.id)"
                        @change="toggleDocSelection(doc.id)"
                      />
                    </td>
                    <td class="doc-name">{{ doc.filename }}</td>
                    <td>
                      <span class="status-pill" :class="doc.status.toLowerCase()">
                        {{ doc.status }}
                      </span>
                    </td>
                    <td class="muted">{{ doc.chunks?.length || 0 }}</td>
                    <td class="muted">{{ new Date(doc.created_at).toLocaleDateString() }}</td>
                    <td style="text-align: right;" @click.stop>
                      <button
                        v-if="doc.status === 'FAILED'"
                        class="btn-text danger"
                        @click="workspace.retryDocument(doc.id)"
                      >
                        Retry
                      </button>
                      <button class="btn-text" @click="onOpenChunks(doc.id)">
                        Inspect Chunks
                      </button>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <!-- Reconcile Footer Bar -->
            <div v-if="workspace.selectedDocIds.length >= 2" class="reconcile-bar">
              <span>Ready to reconcile {{ workspace.selectedDocIds.length }} documents</span>
              <button
                class="btn btn-ink sm"
                :disabled="workspace.livePipelineActive"
                @click="triggerLiveReconciliationOnSelected"
              >
                {{ workspace.livePipelineActive ? 'Running…' : `Reconcile Selected (${workspace.selectedDocIds.length}) →` }}
              </button>
            </div>
          </div>

          <div v-else class="empty-docs">
            <p class="soft">No documents in this project yet. Upload PDFs above to begin.</p>
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
.simple-dashboard {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.org-setup-card {
  background: var(--paper);
  padding: 28px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 600px;
}

.org-form {
  display: flex;
  gap: 12px;
}

.workspace-grid {
  display: grid;
  grid-template-columns: 260px 1fr;
  gap: 20px;
  align-items: start;
}

/* Sidebar: Org & Projects */
.sidebar-panel {
  background: var(--paper);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.org-summary {
  padding-bottom: 16px;
  border-bottom: 1px solid var(--hairline);
}

.org-name {
  font-weight: 600;
  font-size: 15px;
  margin-top: 4px;
}

.projects-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.btn-link-gold {
  background: none;
  border: none;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink);
  cursor: pointer;
  text-decoration: underline;
}

.project-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.project-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 9px 12px;
  border-radius: 2px;
  cursor: pointer;
  font-size: 14px;
  color: var(--ink-soft);
  transition: background 0.15s, color 0.15s;
}

.project-item:hover {
  background: rgba(26, 25, 23, 0.05);
  color: var(--ink);
}

.project-item.active {
  background: var(--ink);
  color: var(--cream);
  font-weight: 500;
}

.project-item-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.project-item-count {
  font-family: var(--font-mono);
  font-size: 11px;
  opacity: 0.75;
}

.empty-projects {
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-size: 13.5px;
  color: var(--ink-soft);
  padding: 12px 0;
}

/* Main Documents Panel */
.docs-panel {
  background: var(--paper);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.docs-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.docs-header h3 {
  font-size: 1.35rem;
  margin-top: 2px;
}

.docs-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.hidden-input {
  display: none;
}

.dropzone {
  border: 1px dashed var(--hairline-strong);
  background: rgba(255, 255, 255, 0.35);
  padding: 20px;
  text-align: center;
  font-size: 14px;
  color: var(--ink-soft);
  cursor: pointer;
  border-radius: 2px;
  transition: border-color 0.15s, background 0.15s;
}

.dropzone:hover,
.dropzone.dragging {
  border-color: var(--ink);
  background: rgba(255, 255, 255, 0.7);
  color: var(--ink);
}

.docs-list-section {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.docs-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 13px;
}

.selection-bar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.search-input {
  padding: 6px 10px;
  border: 1px solid var(--hairline-strong);
  border-radius: 2px;
  background: rgba(255, 255, 255, 0.5);
  font-size: 13px;
  color: var(--ink);
}

.search-input:focus {
  outline: none;
  border-color: var(--ink);
  background: #fff;
}

.table-wrap {
  overflow-x: auto;
}

.docs-table {
  width: 100%;
  border-collapse: collapse;
}

.docs-table th,
.docs-table td {
  padding: 11px 12px;
  text-align: left;
  border-bottom: 1px solid var(--hairline);
  font-size: 13.5px;
}

.docs-table th {
  font-family: var(--font-mono);
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-faint);
}

.docs-table tbody tr {
  cursor: pointer;
}

.docs-table tbody tr:hover {
  background: rgba(26, 25, 23, 0.03);
}

.docs-table tbody tr.selected {
  background: rgba(194, 164, 92, 0.12);
}

.doc-name {
  font-weight: 500;
}

.muted {
  color: var(--ink-soft);
  font-size: 12.5px;
}

.status-pill {
  display: inline-block;
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 2px 8px;
  border-radius: 999px;
  text-transform: uppercase;
}

.status-pill.parsed {
  background: rgba(94, 122, 74, 0.15);
  color: #4D6B3A;
}

.status-pill.processing,
.status-pill.queued {
  background: rgba(194, 164, 92, 0.2);
  color: #7A6028;
}

.status-pill.failed {
  background: rgba(181, 83, 42, 0.15);
  color: #B5532A;
}

.btn-text {
  background: none;
  border: none;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink);
  text-decoration: underline;
  cursor: pointer;
  padding: 2px 4px;
}

.btn-text.danger {
  color: #B5532A;
  margin-right: 8px;
}

.reconcile-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: rgba(26, 25, 23, 0.04);
  border: 1px solid var(--hairline);
  font-size: 13.5px;
}

.empty-docs {
  text-align: center;
  padding: 32px 16px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

.btn.sm {
  padding: 8px 16px;
  font-size: 13px;
}

@media (max-width: 800px) {
  .workspace-grid {
    grid-template-columns: 1fr;
  }
  .org-form {
    flex-direction: column;
  }
}
</style>
