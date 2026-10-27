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

// Local Explorer UI State
const viewMode = ref('details') // 'grid' | 'details'
const searchQuery = ref('')
const isDragging = ref(false)
const fileInput = ref(null)

// Organization creation modal/inline state
const orgNameInput = ref('')
const creatingOrg = ref(false)
const orgError = ref('')

// Navigation state within explorer
// 'projects' (viewing all project folders) | 'project' (inside an open project folder)
const currentFolderView = ref('project')

const hasOrg = computed(() => {
  return Boolean(auth.user?.org_id)
})

const orgDisplayName = computed(() => {
  return auth.user?.org_name || (hasOrg.value ? 'My Organization' : 'No Organization')
})

const filteredDocs = computed(() => {
  const docs = workspace.currentDocs || []
  if (!searchQuery.value.trim()) return docs
  const q = searchQuery.value.toLowerCase()
  return docs.filter(d => d.filename.toLowerCase().includes(q))
})

const filteredProjects = computed(() => {
  const projs = workspace.projects || []
  if (!searchQuery.value.trim()) return projs
  const q = searchQuery.value.toLowerCase()
  return projs.filter(p => p.name.toLowerCase().includes(q))
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

function navigateToProjects() {
  currentFolderView.value = 'projects'
}

async function openProjectFolder(projectId) {
  await workspace.selectProject(projectId)
  currentFolderView.value = 'project'
}

function openFileDialog() {
  if (!hasOrg.value) {
    alert('Please create or join an organization first.')
    return
  }
  if (!workspace.currentProjectId) {
    alert('Please select or open a project folder before uploading documents.')
    return
  }
  if (fileInput.value) {
    fileInput.value.click()
  }
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

function formatBytes(bytes) {
  if (!bytes) return '—'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1048576).toFixed(1) + ' MB'
}
</script>

<template>
  <div class="win-explorer-window">
    <!-- 1. OS Window Title Bar -->
    <div class="win-title-bar">
      <div class="win-title-left">
        <svg class="win-app-icon" width="16" height="16" viewBox="0 0 24 24" fill="none">
          <path d="M2 5a2 2 0 0 1 2-2h4.586a1 1 0 0 1 .707.293L11.414 5H20a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5z" fill="#E8B84B" stroke="#B88A20" stroke-width="1.2"/>
        </svg>
        <span class="win-title-text">
          SuperDocs Explorer — {{ currentFolderView === 'projects' ? 'Projects Directory' : (workspace.currentProject?.name || 'No Project Selected') }}
        </span>
      </div>
      <div class="win-controls">
        <span class="win-ctrl win-min">─</span>
        <span class="win-ctrl win-max">□</span>
        <span class="win-ctrl win-close">✕</span>
      </div>
    </div>

    <!-- 2. Explorer Ribbon / Command Bar -->
    <div class="win-ribbon">
      <div class="ribbon-btn-group">
        <button
          class="ribbon-btn"
          :disabled="!hasOrg"
          @click="emit('open-new-project-modal')"
          title="Create a new Project Folder"
        >
          <span class="ribbon-icon">📁+</span>
          <span class="ribbon-label">New Project</span>
        </button>

        <button
          class="ribbon-btn"
          :disabled="!hasOrg || !workspace.currentProjectId || workspace.isUploading"
          @click="openFileDialog"
          title="Upload PDF files into current project folder"
        >
          <span class="ribbon-icon">📄⬆</span>
          <span class="ribbon-label">{{ workspace.isUploading ? 'Uploading…' : 'Upload PDFs' }}</span>
        </button>

        <button
          class="ribbon-btn"
          @click="workspace.fetchProjects()"
          title="Refresh Directory"
        >
          <span class="ribbon-icon">⟳</span>
          <span class="ribbon-label">Refresh</span>
        </button>

        <input
          ref="fileInput"
          type="file"
          multiple
          accept=".pdf"
          class="hidden-file-input"
          @change="onFilesSelected"
        />
      </div>

      <div class="ribbon-view-group">
        <button
          class="view-toggle-btn"
          :class="{ active: viewMode === 'details' }"
          @click="viewMode = 'details'"
          title="Details Table View"
        >
          ☰ Details
        </button>
        <button
          class="view-toggle-btn"
          :class="{ active: viewMode === 'grid' }"
          @click="viewMode = 'grid'"
          title="Large Icons Grid View"
        >
          ▦ Icons
        </button>
      </div>
    </div>

    <!-- 3. Navigation Address Bar & Search -->
    <div class="win-address-bar">
      <div class="nav-arrows">
        <button
          class="nav-arrow-btn"
          :disabled="currentFolderView === 'projects'"
          @click="navigateToProjects"
          title="Up one level (to Projects directory)"
        >
          ⬆ Up
        </button>
      </div>

      <div class="breadcrumb-bar">
        <span class="crumb-icon">🖥️</span>
        <span class="crumb-item" @click="navigateToProjects">This PC</span>
        <span class="crumb-sep">›</span>
        <span class="crumb-item" @click="navigateToProjects">🏢 {{ orgDisplayName }}</span>
        <span class="crumb-sep">›</span>
        <span
          v-if="currentFolderView === 'project' && workspace.currentProject"
          class="crumb-item active"
        >
          📁 {{ workspace.currentProject.name }}
        </span>
        <span v-else class="crumb-item active">📁 Projects</span>
      </div>

      <div class="search-box">
        <span class="search-icon">🔍</span>
        <input
          v-model="searchQuery"
          type="text"
          :placeholder="currentFolderView === 'projects' ? 'Search projects…' : 'Search documents…'"
        />
      </div>
    </div>

    <!-- 4. Explorer Main Body (Sidebar Tree + File List) -->
    <div class="win-explorer-body">
      <!-- Left Navigation Tree Pane -->
      <aside class="win-tree-pane">
        <div class="tree-root">
          <div class="tree-node root-node">
            <span class="tree-expander">▾</span>
            <span class="tree-icon">🖥️</span>
            <span class="tree-label">This PC</span>
          </div>

          <div class="tree-sub">
            <!-- Organization Node -->
            <div class="tree-node org-node" :class="{ 'node-warning': !hasOrg }">
              <span class="tree-expander">▾</span>
              <span class="tree-icon">🏢</span>
              <span class="tree-label">{{ orgDisplayName }}</span>
            </div>

            <!-- Projects Folder Tree -->
            <div v-if="hasOrg" class="tree-sub">
              <div
                class="tree-node folder-node"
                :class="{ active: currentFolderView === 'projects' }"
                @click="navigateToProjects"
              >
                <span class="tree-expander">▾</span>
                <span class="tree-icon">📁</span>
                <span class="tree-label">Projects</span>
                <span class="tree-badge">{{ workspace.projects.length }}</span>
              </div>

              <!-- Individual Project Sub-nodes -->
              <div class="tree-sub">
                <div
                  v-for="p in workspace.projects"
                  :key="p.id"
                  class="tree-node leaf-node"
                  :class="{ active: currentFolderView === 'project' && workspace.currentProjectId === p.id }"
                  @click="openProjectFolder(p.id)"
                >
                  <span class="tree-icon">📁</span>
                  <span class="tree-label">{{ p.name }}</span>
                  <span class="tree-badge">{{ p.documents?.length || 0 }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Quick Access Box -->
        <div class="quick-access-box">
          <span class="quick-title">Quick Access</span>
          <div
            v-if="workspace.currentProject"
            class="quick-item"
            @click="currentFolderView = 'project'"
          >
            <span>⭐ {{ workspace.currentProject.name }}</span>
            <span class="quick-count">{{ workspace.currentDocs.length }} docs</span>
          </div>
          <div class="quick-item" @click="selectAllParsed">
            <span>✓ Select All Parsed</span>
            <span class="quick-count">{{ workspace.parsedDocs.length }} ready</span>
          </div>
        </div>
      </aside>

      <!-- Right Main Content Area -->
      <main class="win-content-pane">
        <!-- ALERT A: User has NO Organization -->
        <div v-if="!hasOrg" class="win-alert-banner warning">
          <div class="alert-icon">⚠️</div>
          <div class="alert-body">
            <h4>Organization Setup Required</h4>
            <p>
              In accordance with security and data segregation rules, documents cannot be ingested and projects cannot be created until an organization is registered.
            </p>
            <div class="inline-org-form">
              <input
                v-model="orgNameInput"
                type="text"
                placeholder="Enter Organization Name (e.g., Apex Logistics Corp)"
                class="input-org"
                @keyup.enter="handleCreateOrg"
              />
              <button
                class="btn-win-primary"
                :disabled="creatingOrg || !orgNameInput.trim()"
                @click="handleCreateOrg"
              >
                {{ creatingOrg ? 'Creating…' : 'Create Organization' }}
              </button>
            </div>
            <p v-if="orgError" class="err-text">{{ orgError }}</p>
          </div>
        </div>

        <!-- VIEW 1: Projects Directory View (Folders Grid) -->
        <div v-else-if="currentFolderView === 'projects'" class="projects-folder-view">
          <div class="folder-header-bar">
            <span class="folder-title">Projects ({{ filteredProjects.length }} Folders)</span>
            <button class="btn-win-sm" @click="emit('open-new-project-modal')">+ New Project Folder</button>
          </div>

          <div class="win-folders-grid">
            <div
              v-for="p in filteredProjects"
              :key="p.id"
              class="win-folder-item"
              :class="{ selected: workspace.currentProjectId === p.id }"
              @dblclick="openProjectFolder(p.id)"
              @click="workspace.selectProject(p.id)"
            >
              <div class="folder-graphic">
                <svg width="48" height="48" viewBox="0 0 24 24" fill="none">
                  <path d="M2 5a2 2 0 0 1 2-2h4.586a1 1 0 0 1 .707.293L11.414 5H20a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5z" fill="#F4C752" stroke="#C49B22" stroke-width="1.2"/>
                  <path d="M2 10h20v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-9z" fill="#FFD56B"/>
                </svg>
                <span v-if="p.documents?.length" class="folder-doc-badge">{{ p.documents.length }}</span>
              </div>
              <div class="folder-meta">
                <span class="folder-name">{{ p.name }}</span>
                <span class="folder-sub">{{ p.documents?.length || 0 }} files · Double-click to open</span>
              </div>
            </div>

            <!-- New Folder Card -->
            <div class="win-folder-item new-folder-card" @click="emit('open-new-project-modal')">
              <div class="folder-graphic plus">
                <span>➕</span>
              </div>
              <div class="folder-meta">
                <span class="folder-name">New Project…</span>
                <span class="folder-sub">Create folder</span>
              </div>
            </div>
          </div>
        </div>

        <!-- VIEW 2: Inside Project Folder (Documents List & Ingestion Area) -->
        <div v-else class="project-files-view">
          <!-- Folder Info & Ingestion Gate -->
          <div class="project-banner">
            <div class="banner-info">
              <div class="banner-title-row">
                <h3>📁 {{ workspace.currentProject?.name || 'Untitled Project' }}</h3>
                <span class="badge-folder-id">ID: {{ workspace.currentProjectId }}</span>
              </div>
              <p class="banner-desc">
                Drag PDF documents into this folder to start parallel ingestion and title-based chunking.
              </p>
            </div>

            <div class="banner-actions">
              <button class="btn-win-sm" @click="navigateToProjects">⬆ All Projects</button>
              <button
                class="btn-win-primary"
                :disabled="workspace.isUploading"
                @click="openFileDialog"
              >
                {{ workspace.isUploading ? 'Ingesting…' : '📄+ Upload Documents' }}
              </button>
            </div>
          </div>

          <!-- Dropzone inside Project Folder -->
          <div
            class="win-dropzone"
            :class="{ 'is-dragging': isDragging, 'has-files': filteredDocs.length > 0 }"
            @dragover.prevent="isDragging = true"
            @dragleave.prevent="isDragging = false"
            @drop.prevent="onDropFiles"
            @click="openFileDialog"
          >
            <div class="dropzone-inner">
              <span class="drop-icon">📥</span>
              <div class="drop-text">
                <b>Drop PDF files here to ingest into {{ workspace.currentProject?.name }}</b>
                <span>or click to browse your computer (Master Agreements, SOWs, Change Orders, Invoices)</span>
              </div>
            </div>
          </div>

          <!-- DOCUMENTS: View Mode Details (Table) -->
          <div v-if="viewMode === 'details' && filteredDocs.length" class="win-table-container">
            <table class="win-file-table">
              <thead>
                <tr>
                  <th style="width: 38px;">
                    <input
                      type="checkbox"
                      :checked="workspace.selectedDocIds.length === workspace.parsedDocs.length && workspace.parsedDocs.length > 0"
                      @change="workspace.selectedDocIds.length === workspace.parsedDocs.length ? deselectAll() : selectAllParsed()"
                      title="Select / Deselect all parsed documents"
                    />
                  </th>
                  <th>Name</th>
                  <th>Date Modified</th>
                  <th>Type</th>
                  <th>Status</th>
                  <th>Chunks</th>
                  <th style="text-align: right;">Action</th>
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
                  <td class="file-name-cell">
                    <span class="pdf-file-icon">📄</span>
                    <span class="file-name-text">{{ doc.filename }}</span>
                  </td>
                  <td class="cell-muted">{{ new Date(doc.created_at).toLocaleDateString() }}</td>
                  <td class="cell-muted">Adobe Acrobat Document</td>
                  <td>
                    <span class="status-pill" :class="doc.status.toLowerCase()">
                      {{ doc.status }}
                    </span>
                  </td>
                  <td>
                    <span class="chunks-count-tag">{{ doc.chunks?.length || 0 }} chunks</span>
                  </td>
                  <td style="text-align: right;" @click.stop>
                    <button
                      class="btn-row-action"
                      @click="onOpenChunks(doc.id)"
                      title="Inspect extracted chunks"
                    >
                      Inspect Chunks
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- DOCUMENTS: View Mode Grid (Large Icons) -->
          <div v-else-if="viewMode === 'grid' && filteredDocs.length" class="win-files-grid">
            <div
              v-for="doc in filteredDocs"
              :key="doc.id"
              class="win-file-card"
              :class="{ selected: workspace.selectedDocIds.includes(doc.id) }"
              @click="toggleDocSelection(doc.id)"
            >
              <div class="file-card-select" @click.stop>
                <input
                  type="checkbox"
                  :checked="workspace.selectedDocIds.includes(doc.id)"
                  @change="toggleDocSelection(doc.id)"
                />
              </div>

              <div class="file-card-icon">
                <svg width="44" height="44" viewBox="0 0 24 24" fill="none">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" fill="#FFF" stroke="#D13438" stroke-width="1.3"/>
                  <path d="M14 2v6h6" fill="#F4A5A8"/>
                  <rect x="7" y="12" width="10" height="7" rx="1" fill="#D13438"/>
                  <text x="8.5" y="17" fill="#FFF" font-size="5" font-weight="bold">PDF</text>
                </svg>
              </div>

              <span class="file-card-name" :title="doc.filename">{{ doc.filename }}</span>
              <span class="status-pill-sm" :class="doc.status.toLowerCase()">{{ doc.status }}</span>
              <span class="file-card-sub">{{ doc.chunks?.length || 0 }} chunks</span>

              <button
                class="btn-inspect-sm"
                @click.stop="onOpenChunks(doc.id)"
              >
                Inspect
              </button>
            </div>
          </div>

          <!-- Empty Documents Placeholder -->
          <div v-else-if="!filteredDocs.length" class="win-empty-folder">
            <div class="empty-icon">📂</div>
            <h4>This folder is empty</h4>
            <p>Upload contracts, SOWs, or invoices using the dropzone above or the "Upload PDFs" button.</p>
          </div>
        </div>
      </main>
    </div>

    <!-- 5. Windows Status Bar -->
    <div class="win-status-bar">
      <div class="status-left">
        <span>
          {{ currentFolderView === 'projects' ? workspace.projects.length + ' Projects' : filteredDocs.length + ' Documents' }}
        </span>
        <span class="status-sep">|</span>
        <span class="status-selected">
          {{ workspace.selectedDocIds.length }} selected for reconciliation
        </span>
      </div>

      <div class="status-right">
        <button
          v-if="workspace.selectedDocIds.length >= 2"
          class="btn-proceed-stage"
          @click="onProceedToReconcile"
        >
          Proceed to Topic Clustering (Stage 02) →
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.win-explorer-window {
  background: #FFFFFF;
  border: 1px solid #C8C6C4;
  border-radius: 6px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
  color: #1F1F1F;
}

/* 1. Title Bar */
.win-title-bar {
  background: #EAEAEA;
  border-bottom: 1px solid #D1D1D1;
  padding: 6px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  user-select: none;
}
.win-title-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.win-title-text {
  font-size: 12px;
  font-weight: 600;
  color: #333333;
}
.win-controls {
  display: flex;
  gap: 12px;
  font-size: 11px;
  color: #555555;
}
.win-ctrl {
  cursor: pointer;
  padding: 0 4px;
}
.win-ctrl.win-close:hover {
  color: #D13438;
}

/* 2. Ribbon Bar */
.win-ribbon {
  background: #F3F3F3;
  border-bottom: 1px solid #E1DFDD;
  padding: 6px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.ribbon-btn-group {
  display: flex;
  gap: 6px;
}
.ribbon-btn {
  background: #FFFFFF;
  border: 1px solid #D1D1D1;
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 12px;
  display: flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  transition: all 0.15s;
}
.ribbon-btn:hover:not(:disabled) {
  background: #E8EEF5;
  border-color: #0067B8;
}
.ribbon-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.ribbon-view-group {
  display: flex;
  gap: 4px;
}
.view-toggle-btn {
  background: #FFFFFF;
  border: 1px solid #D1D1D1;
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 11px;
  cursor: pointer;
}
.view-toggle-btn.active {
  background: #0067B8;
  color: #FFFFFF;
  border-color: #0067B8;
}
.hidden-file-input {
  display: none;
}

/* 3. Address Bar */
.win-address-bar {
  background: #FAFAFA;
  border-bottom: 1px solid #EDEBE9;
  padding: 6px 12px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.nav-arrow-btn {
  background: #FFFFFF;
  border: 1px solid #D1D1D1;
  border-radius: 4px;
  padding: 3px 8px;
  font-size: 11px;
  cursor: pointer;
}
.nav-arrow-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.breadcrumb-bar {
  flex: 1;
  background: #FFFFFF;
  border: 1px solid #D1D1D1;
  border-radius: 4px;
  padding: 4px 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.crumb-item {
  cursor: pointer;
  color: #0067B8;
}
.crumb-item:hover {
  text-decoration: underline;
}
.crumb-item.active {
  color: #333333;
  font-weight: 600;
  cursor: default;
}
.crumb-item.active:hover {
  text-decoration: none;
}
.crumb-sep {
  color: #8A8886;
}
.search-box {
  background: #FFFFFF;
  border: 1px solid #D1D1D1;
  border-radius: 4px;
  padding: 3px 8px;
  display: flex;
  align-items: center;
  gap: 6px;
  width: 200px;
}
.search-box input {
  border: none;
  outline: none;
  font-size: 12px;
  width: 100%;
}

/* 4. Explorer Body */
.win-explorer-body {
  display: flex;
  height: 480px;
  overflow: hidden;
}

/* Left Sidebar Tree */
.win-tree-pane {
  width: 230px;
  background: #F9F9F9;
  border-right: 1px solid #EDEBE9;
  padding: 10px;
  overflow-y: auto;
  font-size: 12px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 6px;
  border-radius: 4px;
  cursor: pointer;
}
.tree-node:hover {
  background: #EDEBE9;
}
.tree-node.active {
  background: #CCE8FF;
  font-weight: 600;
}
.tree-node.node-warning {
  color: #B88A20;
}
.tree-sub {
  padding-left: 14px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.tree-expander {
  font-size: 9px;
  color: #605E5C;
  width: 10px;
}
.tree-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tree-badge {
  background: #E1DFDD;
  font-size: 10px;
  padding: 1px 5px;
  border-radius: 10px;
  color: #323130;
}

.quick-access-box {
  margin-top: 16px;
  padding-top: 10px;
  border-top: 1px solid #EDEBE9;
}
.quick-title {
  font-size: 10px;
  text-transform: uppercase;
  color: #8A8886;
  font-weight: 700;
  display: block;
  margin-bottom: 6px;
}
.quick-item {
  display: flex;
  justify-content: space-between;
  padding: 4px 6px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 11px;
}
.quick-item:hover {
  background: #EDEBE9;
}
.quick-count {
  color: #605E5C;
}

/* Right Content Pane */
.win-content-pane {
  flex: 1;
  padding: 12px;
  overflow-y: auto;
  background: #FFFFFF;
}

/* Warnings */
.win-alert-banner {
  display: flex;
  gap: 12px;
  padding: 16px;
  border-radius: 6px;
  border: 1px solid #F2C879;
  background: #FFF9E6;
  margin-bottom: 12px;
}
.alert-icon {
  font-size: 24px;
}
.alert-body h4 {
  margin: 0 0 6px 0;
  font-size: 14px;
  color: #7A5700;
}
.alert-body p {
  margin: 0 0 10px 0;
  font-size: 12px;
  color: #4A3A00;
  line-height: 1.4;
}
.inline-org-form {
  display: flex;
  gap: 8px;
}
.input-org {
  flex: 1;
  border: 1px solid #D1D1D1;
  border-radius: 4px;
  padding: 6px 10px;
  font-size: 12px;
}
.btn-win-primary {
  background: #0067B8;
  color: #FFFFFF;
  border: none;
  border-radius: 4px;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}
.btn-win-primary:hover:not(:disabled) {
  background: #005DA6;
}
.btn-win-sm {
  background: #F3F3F3;
  border: 1px solid #D1D1D1;
  border-radius: 4px;
  padding: 4px 10px;
  font-size: 11px;
  cursor: pointer;
}
.err-text {
  color: #D13438;
  font-size: 11px;
  margin-top: 6px;
}

/* Projects Directory Grid */
.folder-header-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.folder-title {
  font-size: 13px;
  font-weight: 600;
  color: #333333;
}
.win-folders-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}
.win-folder-item {
  border: 1px solid transparent;
  border-radius: 4px;
  padding: 12px 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  cursor: pointer;
  transition: all 0.15s;
}
.win-folder-item:hover {
  background: #F3F9FF;
  border-color: #CCE8FF;
}
.win-folder-item.selected {
  background: #CCE8FF;
  border-color: #99D1FF;
}
.folder-graphic {
  position: relative;
  margin-bottom: 8px;
}
.folder-doc-badge {
  position: absolute;
  top: 4px;
  right: -4px;
  background: #0067B8;
  color: #FFF;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 5px;
  border-radius: 8px;
}
.folder-graphic.plus {
  width: 48px;
  height: 48px;
  border: 2px dashed #B88A20;
  border-radius: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}
.folder-name {
  font-size: 12px;
  font-weight: 600;
  color: #1F1F1F;
  word-break: break-word;
}
.folder-sub {
  font-size: 10px;
  color: #605E5C;
  margin-top: 2px;
}

/* Inside Project View */
.project-banner {
  background: #F9F9F9;
  border: 1px solid #EDEBE9;
  border-radius: 6px;
  padding: 10px 14px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.banner-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.banner-title-row h3 {
  margin: 0;
  font-size: 14px;
  color: #201F1E;
}
.badge-folder-id {
  background: #E1DFDD;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 4px;
}
.banner-desc {
  margin: 4px 0 0 0;
  font-size: 11px;
  color: #605E5C;
}
.banner-actions {
  display: flex;
  gap: 8px;
}

/* Dropzone inside folder */
.win-dropzone {
  border: 2px dashed #C8C6C4;
  border-radius: 6px;
  background: #FAFAFA;
  padding: 14px;
  text-align: center;
  margin-bottom: 12px;
  cursor: pointer;
  transition: all 0.2s;
}
.win-dropzone:hover, .win-dropzone.is-dragging {
  border-color: #0067B8;
  background: #F0F6FC;
}
.dropzone-inner {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
}
.drop-icon {
  font-size: 22px;
}
.drop-text {
  display: flex;
  flex-direction: column;
  text-align: left;
  font-size: 12px;
}
.drop-text b {
  color: #0067B8;
}
.drop-text span {
  font-size: 11px;
  color: #605E5C;
}

/* Details Table View */
.win-table-container {
  border: 1px solid #EDEBE9;
  border-radius: 4px;
  overflow: hidden;
}
.win-file-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.win-file-table th {
  background: #F3F3F3;
  text-align: left;
  padding: 6px 10px;
  font-weight: 600;
  color: #605E5C;
  border-bottom: 1px solid #E1DFDD;
}
.win-file-table td {
  padding: 6px 10px;
  border-bottom: 1px solid #F3F3F3;
  vertical-align: middle;
}
.win-file-table tr:hover {
  background: #F5F9FD;
}
.win-file-table tr.selected {
  background: #CCE8FF;
}
.file-name-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 500;
}
.pdf-file-icon {
  font-size: 16px;
}
.cell-muted {
  color: #605E5C;
  font-size: 11px;
}
.status-pill {
  font-size: 10px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 4px;
  text-transform: uppercase;
}
.status-pill.parsed { background: #DFF6DD; color: #107C10; }
.status-pill.queued { background: #FFF4CE; color: #797775; }
.status-pill.failed { background: #FDE7E9; color: #A80000; }
.chunks-count-tag {
  background: #F3F3F3;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 11px;
}
.btn-row-action {
  background: #FFFFFF;
  border: 1px solid #D1D1D1;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
  cursor: pointer;
}
.btn-row-action:hover {
  background: #E8EEF5;
  border-color: #0067B8;
}

/* Grid View for Files */
.win-files-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(130px, 1fr));
  gap: 12px;
}
.win-file-card {
  border: 1px solid #EDEBE9;
  border-radius: 6px;
  padding: 10px 8px;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  position: relative;
  cursor: pointer;
}
.win-file-card:hover {
  background: #F5F9FD;
  border-color: #99D1FF;
}
.win-file-card.selected {
  background: #CCE8FF;
  border-color: #0067B8;
}
.file-card-select {
  position: absolute;
  top: 6px;
  left: 6px;
}
.file-card-name {
  font-size: 11px;
  font-weight: 600;
  margin: 6px 0 2px 0;
  word-break: break-word;
  line-height: 1.2;
}
.status-pill-sm {
  font-size: 9px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 3px;
  margin-bottom: 2px;
}
.status-pill-sm.parsed { background: #DFF6DD; color: #107C10; }
.status-pill-sm.queued { background: #FFF4CE; color: #797775; }
.file-card-sub {
  font-size: 10px;
  color: #605E5C;
  margin-bottom: 6px;
}
.btn-inspect-sm {
  font-size: 10px;
  background: #FFF;
  border: 1px solid #D1D1D1;
  border-radius: 3px;
  padding: 2px 6px;
  cursor: pointer;
}

/* Empty Folder */
.win-empty-folder {
  text-align: center;
  padding: 40px 20px;
  color: #605E5C;
}
.empty-icon {
  font-size: 36px;
  margin-bottom: 8px;
}
.win-empty-folder h4 {
  margin: 0 0 4px 0;
  color: #323130;
}

/* 5. Status Bar */
.win-status-bar {
  background: #F3F3F3;
  border-top: 1px solid #E1DFDD;
  padding: 6px 12px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 11px;
  color: #605E5C;
}
.status-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.status-selected {
  font-weight: 600;
  color: #0067B8;
}
.btn-proceed-stage {
  background: #0067B8;
  color: #FFFFFF;
  border: none;
  border-radius: 4px;
  padding: 4px 12px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}
.btn-proceed-stage:hover {
  background: #005DA6;
}
</style>
