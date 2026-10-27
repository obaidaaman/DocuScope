<script setup>
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useWorkspaceStore } from '../stores/workspace'
import NewProjectModal from '../components/NewProjectModal.vue'
import DocumentChunksModal from '../components/DocumentChunksModal.vue'
import CustomResolutionModal from '../components/CustomResolutionModal.vue'
import FileExplorer from '../components/FileExplorer.vue'

const auth = useAuthStore()
const workspace = useWorkspaceStore()
const router = useRouter()

// UI state
const activeTab = ref('documents') // 'documents' | 'reconcile' | 'review' | 'deliverable'
const showNewProjectModal = ref(false)
const showChunksModal = ref(false)
const inspectedDocId = ref(null)
const inspectedDocName = ref('')
const showCustomModal = ref(false)
const selectedReviewItem = ref(null)
const reportCopied = ref(false)

// File upload state
const fileInput = ref(null)
const isDragging = ref(false)
const uploadMessage = ref('')

// Auto polling interval for in-flight documents
let pollTimer = null

onMounted(async () => {
  await workspace.fetchProjects()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})

function startPolling() {
  if (pollTimer) clearInterval(pollTimer)
  pollTimer = setInterval(async () => {
    const hasInFlight = workspace.currentDocs.some(d => d.status === 'QUEUED' || d.status === 'PROCESSING')
    if (hasInFlight) {
      await workspace.refreshCurrentProject()
    }
  }, 3000)
}

function stopPolling() {
  if (pollTimer) clearInterval(pollTimer)
}

async function handleLogout() {
  stopPolling()
  await auth.logout()
  router.push('/login')
}

// 1. Projects
async function onProjectSelect(e) {
  const pid = Number(e.target.value)
  if (pid) {
    await workspace.selectProject(pid)
  }
}

async function handleCreateProject(name) {
  await workspace.createProject(name, auth.user?.org_id)
}

function openFileDialog() {
  if (workspace.isUploading) return
  if (!workspace.currentProjectId) {
    workspace.actionError = 'Please select or create a project first before uploading documents.'
    showNewProjectModal.value = true
    return
  }
  fileInput.value?.click()
}

// 2. Documents
function onFileSelect(e) {
  const files = Array.from(e.target.files || [])
  triggerUpload(files)
}

function onFileDrop(e) {
  isDragging.value = false
  const files = Array.from(e.dataTransfer?.files || [])
  triggerUpload(files)
}

async function triggerUpload(files) {
  if (!files.length) return
  if (!workspace.currentProjectId) {
    workspace.actionError = 'Please select or create a project first before uploading documents.'
    showNewProjectModal.value = true
    return
  }
  const nonPdfs = files.filter(f => !f.name.toLowerCase().endsWith('.pdf'))
  if (nonPdfs.length > 0) {
    workspace.actionError = 'Only PDF documents are currently supported by the extraction pipeline.'
    return
  }
  try {
    uploadMessage.value = ''
    const res = await workspace.uploadDocuments(files)
    if (res) {
      uploadMessage.value = res.message || `${files.length} document(s) uploaded.`
    }
  } catch {
    // error handled in store
  } finally {
    if (fileInput.value) fileInput.value.value = ''
  }
}

function inspectDoc(doc) {
  inspectedDocId.value = doc.id
  inspectedDocName.value = doc.filename
  showChunksModal.value = true
}

function inspectDocById(docId) {
  const doc = workspace.currentDocs.find(d => d.id === docId)
  inspectedDocId.value = docId
  inspectedDocName.value = doc?.filename || `Document #${docId}`
  showChunksModal.value = true
}

// 3. Reconcile selection helpers
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

async function onPreviewClusters() {
  try {
    await workspace.previewClusters()
  } catch {
    // handled
  }
}

async function onRunReconciliation() {
  try {
    const res = await workspace.runReconciliation()
    if (res.conflicts_count > 0) {
      activeTab.value = 'review'
    } else {
      activeTab.value = 'deliverable'
    }
  } catch {
    // handled
  }
}

// 4. Conflict Resolution
async function resolveAdoptDoc(item, docId) {
  try {
    await workspace.resolveConflict(item.id, 'APPROVE_DOC', docId)
  } catch {
    // handled
  }
}

async function resolveReject(item) {
  try {
    await workspace.resolveConflict(item.id, 'REJECT')
  } catch {
    // handled
  }
}

function openCustomResolution(item) {
  selectedReviewItem.value = item
  showCustomModal.value = true
}

async function handleCustomResolution({ reviewItemId, action, customText }) {
  await workspace.resolveConflict(reviewItemId, action, null, customText)
}

// 5. Deliverables & Full Report Export
const compiledReportMarkdown = computed(() => {
  if (!workspace.deliverables.length) return ''
  const lines = []
  lines.push(`# SuperDocs Reconciled Deliverable Report`)
  lines.push(`**Run Thread ID:** \`${workspace.activeThreadId || 'N/A'}\``)
  lines.push(`**Project:** ${workspace.currentProject?.name || 'Untitled'}`)
  lines.push(`**Generated:** ${new Date().toLocaleString()}`)
  lines.push(`---\n`)

  lines.push(`## Reconciled Contractual Terms\n`)
  for (const s of workspace.deliverables) {
    lines.push(`### ${s.title || s.category}`)
    lines.push(s.committed_markdown)
    if (s.citations && s.citations.length) {
      lines.push(`\n> **Verified Grounded Citations:**`)
      for (const c of s.citations) {
        lines.push(`> * \`[Doc ${c.doc_id} | Page ${c.page_number}]\`: "${c.exact_quote}"`)
      }
    }
    lines.push(`\n`)
  }
  return lines.join('\n')
})

function copyReport() {
  if (!compiledReportMarkdown.value) return
  navigator.clipboard.writeText(compiledReportMarkdown.value)
  reportCopied.value = true
  setTimeout(() => { reportCopied.value = false }, 3000)
}

function downloadReport() {
  if (!compiledReportMarkdown.value) return
  const blob = new Blob([compiledReportMarkdown.value], { type: 'text/markdown;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.setAttribute('href', url)
  link.setAttribute('download', `Reconciliation_Report_${workspace.activeThreadId || 'deliverable'}.md`)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}
</script>

<template>
  <div class="workspace">
    <!-- Top Bar -->
    <header class="app-nav">
      <div class="nav-left">
        <RouterLink to="/" class="brand" aria-label="SuperDocs home">
          <svg width="24" height="24" viewBox="0 0 26 26" fill="none" aria-hidden="true">
            <rect x="3" y="2" width="14" height="18" rx="1.5" stroke="#F0EBE1" stroke-width="1.5"/>
            <rect x="9" y="6" width="14" height="18" rx="1.5" fill="#14130F" stroke="#C2A45C" stroke-width="1.5"/>
            <path d="M12.5 12h7M12.5 15.5h7M12.5 19h4" stroke="#F0EBE1" stroke-width="1.3" stroke-linecap="round"/>
          </svg>
          <span class="brand-title">SuperDocs</span>
        </RouterLink>

        <!-- Project Selector -->
        <div class="project-selector">
          <label for="project-dropdown" class="label gold">Project</label>
          <select
            id="project-dropdown"
            class="project-select"
            :value="workspace.currentProjectId"
            @change="onProjectSelect"
          >
            <option v-if="!workspace.projects.length" disabled value="">No Projects Created</option>
            <option v-for="p in workspace.projects" :key="p.id" :value="p.id">
              {{ p.name }}
            </option>
          </select>
          <button class="btn-new-proj" @click="showNewProjectModal = true" title="Create New Project">
            + New
          </button>
        </div>
      </div>

      <div class="nav-right">
        <div class="user-pill">
          <span class="avatar">{{ auth.user?.first_name?.charAt(0) || 'U' }}</span>
          <div class="user-meta">
            <span class="uname">{{ auth.user?.first_name }} {{ auth.user?.last_name }}</span>
            <span class="uemail">{{ auth.user?.email }}</span>
          </div>
        </div>
        <button class="btn btn-outline sm" @click="handleLogout">Log out</button>
      </div>
    </header>

    <!-- Main Workspace Container -->
    <main class="app-main">
      <!-- Stage Tabs Navigation -->
      <nav class="stage-tabs" aria-label="Reconciliation Workflow">
        <button
          class="stage-tab"
          :class="{ active: activeTab === 'documents' }"
          @click="activeTab = 'documents'"
        >
          <span class="stage-num">01</span>
          <span class="stage-label">Documents & Ingestion</span>
          <span class="badge">{{ workspace.currentDocs.length }}</span>
        </button>

        <button
          class="stage-tab"
          :class="{ active: activeTab === 'reconcile' }"
          @click="activeTab = 'reconcile'"
        >
          <span class="stage-num">02</span>
          <span class="stage-label">Topic Clusters & Reconcile</span>
          <span class="badge" v-if="workspace.parsedDocs.length">{{ workspace.parsedDocs.length }} Ready</span>
        </button>

        <button
          class="stage-tab"
          :class="{ active: activeTab === 'review' }"
          @click="activeTab = 'review'"
        >
          <span class="stage-num">03</span>
          <span class="stage-label">Conflict Review Gate</span>
          <span class="badge alert" v-if="workspace.pendingReviewCount > 0">
            {{ workspace.pendingReviewCount }} Pending
          </span>
        </button>

        <button
          class="stage-tab"
          :class="{ active: activeTab === 'deliverable' }"
          @click="activeTab = 'deliverable'"
        >
          <span class="stage-num">04</span>
          <span class="stage-label">Grounded Deliverable</span>
          <span class="badge" v-if="workspace.deliverables.length">{{ workspace.deliverables.length }} Clauses</span>
        </button>
      </nav>

      <!-- Global Error Banner -->
      <div v-if="workspace.actionError" class="error-banner">
        <span>⚠ {{ workspace.actionError }}</span>
        <button @click="workspace.actionError = ''">✕</button>
      </div>

      <!-- ========================================================================= -->
      <!-- TAB 1: Documents & Ingestion (Windows OS Folder & File Explorer) -->
      <!-- ========================================================================= -->
      <section v-if="activeTab === 'documents'" class="tab-content">
        <div class="content-header">
          <div>
            <span class="label faint">Pipeline Stage 01</span>
            <h2>Workspace Explorer & Ingestion Gateway</h2>
            <p class="soft">
              Hierarchical folder system structured by Organization, Project Folders, and Documents. Organizations and Projects are strictly required before ingestion.
            </p>
          </div>
        </div>

        <!-- Windows Operating System Style File Explorer -->
        <FileExplorer
          :on-open-chunks="inspectDocById"
          :on-proceed-to-reconcile="() => { activeTab = 'clustering' }"
          @open-new-project-modal="showNewProjectModal = true"
        />
      </section>

      <!-- ========================================================================= -->
      <!-- TAB 2: Topic Clusters & Reconcile -->
      <!-- ========================================================================= -->
      <section v-if="activeTab === 'reconcile'" class="tab-content">
        <div class="content-header">
          <div>
            <span class="label faint">Pipeline Stage 02</span>
            <h2>Topic Clustering & LLM Judge Reconciliation</h2>
            <p class="soft">
              pgvector cross-document vector joins match similar chunks, NetworkX clusters them into topic "Dabbe", and OpenAI evaluates agreements vs conflicts.
            </p>
          </div>
        </div>

        <!-- Setup & Parameter Controls -->
        <div class="reconcile-controls frame">
          <div class="control-row">
            <div class="doc-selection-summary">
              <span class="label gold">Selected Documents ({{ workspace.selectedDocIds.length }})</span>
              <p v-if="workspace.selectedDocIds.length < 2" class="warning-text">
                ⚠️ Select at least 2 parsed documents to find contradictions.
              </p>
              <p v-else class="success-text">
                ✓ Ready to reconcile across Document IDs: {{ workspace.selectedDocIds.join(', ') }}
              </p>
              <div class="selection-actions">
                <button class="btn-link" @click="selectAllParsed">Select All Parsed</button>
                <button class="btn-link" @click="deselectAll">Deselect All</button>
              </div>
            </div>

            <!-- Parameters -->
            <div class="params-group">
              <div class="param-item">
                <label for="thresh">Similarity Threshold: <b>{{ workspace.similarityThreshold }}</b></label>
                <input
                  id="thresh"
                  type="range"
                  min="0.30"
                  max="0.80"
                  step="0.05"
                  v-model="workspace.similarityThreshold"
                />
              </div>

              <div class="param-item">
                <label for="max-pairs">Max Graph Pairs: <b>{{ workspace.maxPairs }}</b></label>
                <input
                  id="max-pairs"
                  type="number"
                  min="50"
                  max="1000"
                  step="50"
                  class="input-sm"
                  v-model="workspace.maxPairs"
                />
              </div>
            </div>
          </div>

          <div class="reconcile-actions">
            <button
              class="btn btn-outline"
              :disabled="workspace.selectedDocIds.length < 2 || workspace.isPreviewing"
              @click="onPreviewClusters"
            >
              {{ workspace.isPreviewing ? 'Extracting Topics & Aligning…' : 'Preview Clusters (Topic Anchors)' }}
            </button>

            <button
              class="btn btn-ink"
              :disabled="workspace.selectedDocIds.length < 2 || workspace.isReconciling"
              @click="onRunReconciliation"
            >
              {{ workspace.isReconciling ? 'Running LLM Judge Pipeline…' : 'Run Full Reconciliation ⚡' }}
            </button>
          </div>
        </div>

        <!-- Clusters Preview Display (Dabbe) -->
        <div v-if="workspace.clustersPreview" class="clusters-section">
          <div class="section-title">
            <span class="label gold">Semantic Topic Topology</span>
            <h3>Discovered Topic Clusters ({{ workspace.clustersPreview.total_clusters }} Dabbe)</h3>
          </div>

          <div class="dabbe-grid">
            <div
              v-for="cluster in workspace.clustersPreview.clusters"
              :key="cluster.dabba_id"
              class="dabba-card frame"
            >
              <div class="dabba-head">
                <span class="dabba-badge">{{ cluster.topic_hint || ('Dabba #' + cluster.dabba_id) }}</span>
                <span class="docs-tag">Docs: {{ cluster.document_ids.join(', ') }}</span>
                <span class="chunks-tag">{{ cluster.total_chunks }} Chunks (±1 Context)</span>
              </div>

              <div class="passages-stack">
                <div v-for="(p, pidx) in cluster.passages" :key="pidx" class="passage-box">
                  <span class="passage-doc">Doc {{ p.doc_id }} · Page {{ p.page_number }}</span>
                  <p class="passage-snippet">{{ p.text }}</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Reconciliation Results Banner -->
        <div v-if="workspace.reconciliationResult" class="result-summary frame">
          <div class="summary-left">
            <span class="label gold">Reconciliation Run Complete</span>
            <h3>Run Thread: <code>{{ workspace.reconciliationResult.thread_id }}</code></h3>
            <div class="stats-row">
              <span class="stat-pill danger">
                <b>{{ workspace.reconciliationResult.conflicts_count }}</b> Conflicts Detected
              </span>
              <span class="stat-pill success">
                <b>{{ workspace.reconciliationResult.agreements_count }}</b> Direct Agreements
              </span>
            </div>
          </div>
          <div class="summary-right">
            <button class="btn btn-ink" @click="activeTab = 'review'">
              Review Conflicts Queue →
            </button>
            <button class="btn btn-outline" @click="activeTab = 'deliverable'">
              View Deliverable Register →
            </button>
          </div>
        </div>
      </section>

      <!-- ========================================================================= -->
      <!-- TAB 3: Conflict Review Gate -->
      <!-- ========================================================================= -->
      <section v-if="activeTab === 'review'" class="tab-content">
        <div class="content-header">
          <div>
            <span class="label faint">Pipeline Stage 03</span>
            <h2>Human-in-the-Loop Conflict Review Gate</h2>
            <p class="soft">
              Every identified conflict requires an analyst decision. Adopt a specific document's clause, reject the claim, or write a custom contractual resolution.
            </p>
          </div>
        </div>

        <div v-if="!workspace.reviewItems.length" class="empty-state frame">
          <p class="h3">No Pending Conflicts Found</p>
          <small>Either the corpus is in full agreement, or no reconciliation run has been executed yet.</small>
          <button class="btn btn-ink sm" style="margin-top: 14px" @click="activeTab = 'reconcile'">
            Go to Reconcile Stage
          </button>
        </div>

        <div v-else class="review-items-stack">
          <article
            v-for="item in workspace.reviewItems"
            :key="item.id"
            class="conflict-card frame"
            :class="{ resolved: item.status === 'RESOLVED' }"
          >
            <!-- Card Header -->
            <div class="card-top">
              <div class="topic-info">
                <div class="badges">
                  <span class="tag tag-danger">{{ item.item_type }}</span>
                  <span class="tag tag-sev" :class="item.severity.toLowerCase()">
                    {{ item.severity }} SEVERITY
                  </span>
                  <span class="tag tag-status" :class="item.status.toLowerCase()">
                    {{ item.status }}
                  </span>
                </div>
                <h3>{{ item.category }}</h3>
              </div>
              <span class="thread-info">Thread: {{ item.run_thread_id }}</span>
            </div>

            <!-- Explanation -->
            <p class="conflict-summary">{{ item.summary }}</p>

            <!-- Evidence Citations Grid -->
            <div class="citations-container" v-if="item.citations && item.citations.length">
              <span class="label faint">Grounded Evidence per Document</span>
              <div class="citations-grid">
                <div v-for="(cit, cidx) in item.citations" :key="cidx" class="cit-box">
                  <div class="cit-head">
                    <span class="cit-doc">Doc {{ cit.doc_id }}</span>
                    <span class="cit-page">Page {{ cit.page_number }}</span>
                  </div>
                  <blockquote class="cit-quote">“{{ cit.exact_quote }}”</blockquote>
                </div>
              </div>
            </div>

            <!-- Resolution Action Buttons -->
            <div class="card-bottom">
              <div v-if="item.status === 'PENDING'" class="actions-group">
                <span class="label faint">Analyst Decision:</span>
                <div class="buttons-row">
                  <!-- Quick adopt buttons for each cited doc -->
                  <button
                    v-for="cit in item.citations"
                    :key="'adopt-' + cit.doc_id"
                    class="btn btn-outline sm"
                    :disabled="workspace.isResolving"
                    @click="resolveAdoptDoc(item, cit.doc_id)"
                  >
                    Adopt Doc {{ cit.doc_id }} Terms
                  </button>

                  <button
                    class="btn btn-outline sm"
                    :disabled="workspace.isResolving"
                    @click="openCustomResolution(item)"
                  >
                    Custom Resolution…
                  </button>

                  <button
                    class="btn btn-outline sm alert"
                    :disabled="workspace.isResolving"
                    @click="resolveReject(item)"
                  >
                    Reject Claim
                  </button>
                </div>
              </div>

              <div v-else class="resolution-badge">
                <span>✓ {{ item.resolution_notes || 'Resolved & Committed to Deliverable' }}</span>
              </div>
            </div>
          </article>
        </div>
      </section>

      <!-- ========================================================================= -->
      <!-- TAB 4: Grounded Deliverable Register & Report -->
      <!-- ========================================================================= -->
      <section v-if="activeTab === 'deliverable'" class="tab-content">
        <div class="content-header deliverable-header">
          <div>
            <span class="label faint">Pipeline Stage 04</span>
            <h2>Grounded Deliverable & Reconciliation Register</h2>
            <p class="soft">
              Synthesized legal report combining direct agreements and resolved human decisions. Every statement is traceable to its verified citation.
            </p>
          </div>
          <div class="deliverable-actions">
            <button class="btn btn-outline sm" @click="copyReport">
              {{ reportCopied ? '✓ Copied Markdown' : 'Copy Report MD' }}
            </button>
            <button class="btn btn-ink sm" @click="downloadReport">
              Download Report (.md)
            </button>
          </div>
        </div>

        <div v-if="!workspace.deliverables.length" class="empty-state frame">
          <p class="h3">No Committed Deliverables Yet</p>
          <small>Run reconciliation and resolve any conflicts to compile the final deliverable register.</small>
        </div>

        <div v-else class="deliverables-stack">
          <!-- Committed Clauses Cards -->
          <article
            v-for="s in workspace.deliverables"
            :key="s.id"
            class="deliverable-card frame"
          >
            <div class="deliv-head">
              <div>
                <span class="label gold">Committed Clause</span>
                <h3>{{ s.title || s.category }}</h3>
              </div>
              <span class="deliv-date">{{ new Date(s.created_at).toLocaleDateString() }}</span>
            </div>

            <div class="deliv-text">
              <p>{{ s.committed_markdown }}</p>
            </div>

            <div class="deliv-citations" v-if="s.citations && s.citations.length">
              <span class="label faint">Grounding Citations:</span>
              <div class="citations-row">
                <div v-for="(c, cidx) in s.citations" :key="cidx" class="deliv-cit-chip">
                  <code>[Doc {{ c.doc_id }} | Page {{ c.page_number }}]</code>
                  <span>“{{ c.exact_quote }}”</span>
                </div>
              </div>
            </div>
          </article>
        </div>
      </section>
    </main>

    <!-- Modals -->
    <NewProjectModal
      :show="showNewProjectModal"
      :user-org-id="auth.user?.org_id"
      @close="showNewProjectModal = false"
      @create="handleCreateProject"
    />

    <DocumentChunksModal
      :show="showChunksModal"
      :doc-id="inspectedDocId"
      :doc-filename="inspectedDocName"
      @close="showChunksModal = false"
    />

    <CustomResolutionModal
      :show="showCustomModal"
      :item="selectedReviewItem"
      @close="showCustomModal = false"
      @resolve="handleCustomResolution"
    />
  </div>
</template>

<style scoped>
.workspace {
  min-height: 100vh;
  background: var(--paper);
  color: var(--ink);
  display: flex;
  flex-direction: column;
}

/* Header */
.app-nav {
  height: 64px;
  background: var(--dark);
  color: var(--cream);
  border-bottom: 1px solid var(--hairline-dark);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 clamp(20px, 3vw, 40px);
}

.nav-left {
  display: flex;
  align-items: center;
  gap: 32px;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  font-size: 18px;
  font-weight: 500;
  color: var(--cream);
}

.project-selector {
  display: flex;
  align-items: center;
  gap: 10px;
}

.project-select {
  background: #24231C;
  color: var(--cream);
  border: 1px solid var(--hairline-dark);
  padding: 6px 12px;
  border-radius: 2px;
  font-family: var(--font-body);
  font-size: 13.5px;
  cursor: pointer;
}

.project-select:focus {
  outline: none;
  border-color: var(--gold);
}

.btn-new-proj {
  background: transparent;
  color: var(--gold);
  border: 1px solid var(--hairline-dark);
  padding: 5px 10px;
  border-radius: 2px;
  font-size: 12px;
  font-family: var(--font-mono);
  cursor: pointer;
  transition: all 0.2s;
}

.btn-new-proj:hover {
  background: rgba(194, 164, 92, 0.15);
  border-color: var(--gold);
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 20px;
}

.user-pill {
  display: flex;
  align-items: center;
  gap: 10px;
}

.avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--gold);
  color: var(--dark);
  display: grid;
  place-items: center;
  font-weight: 600;
  font-size: 13px;
}

.user-meta {
  display: flex;
  flex-direction: column;
}

.uname {
  font-size: 13px;
  font-weight: 500;
  color: var(--cream);
}

.uemail {
  font-size: 11px;
  color: var(--cream-soft);
}

/* Tabs */
.stage-tabs {
  background: var(--paper-deep);
  border-bottom: 1px solid var(--hairline);
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  padding: 0 clamp(20px, 3vw, 40px);
}

.stage-tab {
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 16px 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  cursor: pointer;
  transition: all 0.2s;
  color: var(--ink-soft);
}

.stage-tab:hover {
  color: var(--ink);
  background: rgba(26, 25, 23, 0.02);
}

.stage-tab.active {
  color: var(--ink);
  border-bottom-color: var(--ink);
  font-weight: 600;
}

.stage-num {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--gold);
}

.stage-label {
  font-size: 14px;
}

.badge {
  font-family: var(--font-mono);
  font-size: 10px;
  background: rgba(26, 25, 23, 0.08);
  padding: 2px 7px;
  border-radius: 999px;
}

.badge.alert {
  background: #B5532A;
  color: #fff;
}

/* Content Main */
.app-main {
  flex: 1;
  max-width: 1240px;
  width: 100%;
  margin: 0 auto;
  padding: 36px clamp(20px, 3vw, 40px) 60px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.content-header h2 {
  font-size: 1.8rem;
  margin: 6px 0 4px;
}

.soft {
  color: var(--ink-soft);
  max-width: 680px;
  font-size: 14.5px;
}

.error-banner {
  background: rgba(181, 83, 42, 0.1);
  border-left: 3px solid #B5532A;
  padding: 12px 18px;
  color: #8A3B1B;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 14px;
}
.error-banner button {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 16px;
  color: inherit;
}

/* Dropzone */
.dropzone {
  border: 2px dashed var(--hairline-strong);
  background: rgba(255, 255, 255, 0.4);
  padding: 44px 24px;
  border-radius: 2px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  cursor: pointer;
  transition: all 0.2s;
}

.dropzone:hover, .dropzone.dragging {
  border-color: var(--ink);
  background: #fff;
}

.drop-icon {
  font-size: 32px;
}

.drop-text strong {
  display: block;
  font-size: 15px;
}

.drop-text small {
  color: var(--ink-faint);
  font-size: 12px;
}

.hidden-file-input {
  display: none;
}

.upload-success {
  padding: 12px 16px;
  background: rgba(94, 122, 74, 0.12);
  color: #4D6B3A;
  border-radius: 2px;
  font-size: 14px;
}

/* Table Card */
.table-card {
  background: var(--paper);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.table-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.table-card-head h3 {
  font-size: 1.25rem;
}

.table-responsive {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
}

th, td {
  padding: 14px 18px;
  text-align: left;
  border-bottom: 1px solid var(--hairline);
  font-size: 14px;
}

th {
  font-family: var(--font-mono);
  font-size: 10.5px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--ink-faint);
}

.filename-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: 999px;
  font-family: var(--font-mono);
  font-size: 10px;
  letter-spacing: 0.06em;
}

.status-badge .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

.status-badge.parsed {
  background: rgba(94, 122, 74, 0.15);
  color: #4D6B3A;
}
.status-badge.parsed .dot { background: #4D6B3A; }

.status-badge.processing {
  background: rgba(2, 113, 254, 0.12);
  color: #0271FE;
}
.status-badge.processing .dot {
  background: #0271FE;
  animation: pulse 1.2s infinite;
}

.status-badge.queued {
  background: rgba(194, 164, 92, 0.2);
  color: #7A6028;
}
.status-badge.queued .dot { background: #7A6028; }

.status-badge.failed {
  background: rgba(181, 83, 42, 0.15);
  color: #B5532A;
}
.status-badge.failed .dot { background: #B5532A; }

.btn-text {
  background: none;
  border: none;
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--ink);
  cursor: pointer;
  text-decoration: underline;
  padding: 4px 6px;
}

.btn-text.alert {
  color: #B5532A;
}

.empty-state {
  text-align: center;
  padding: 50px 20px;
  color: var(--ink-soft);
}

/* Reconcile Tab */
.reconcile-controls {
  background: var(--paper);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.control-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 32px;
}

.warning-text {
  color: #B5532A;
  font-size: 13px;
  margin: 6px 0;
}

.success-text {
  color: #4D6B3A;
  font-size: 13px;
  margin: 6px 0;
}

.selection-actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
}

.btn-link {
  background: none;
  border: none;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-soft);
  text-decoration: underline;
  cursor: pointer;
}

.params-group {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.param-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
}

.input-sm {
  width: 120px;
  padding: 6px 10px;
  border: 1px solid var(--hairline-strong);
  font-family: var(--font-mono);
}

.reconcile-actions {
  display: flex;
  gap: 14px;
  justify-content: flex-end;
  border-top: 1px solid var(--hairline);
  padding-top: 18px;
}

/* Dabbe Grid */
.dabbe-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
  gap: 18px;
  margin-top: 14px;
}

.dabba-card {
  background: var(--paper);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.dabba-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.dabba-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  background: var(--olive);
  color: var(--cream);
  padding: 3px 8px;
  border-radius: 2px;
}

.docs-tag, .chunks-tag {
  font-family: var(--font-mono);
  font-size: 11px;
  background: rgba(26, 25, 23, 0.06);
  padding: 3px 8px;
  border-radius: 2px;
}

.passages-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.passage-box {
  background: rgba(26, 25, 23, 0.03);
  border-left: 2px solid var(--gold);
  padding: 10px 12px;
}

.passage-doc {
  display: block;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--copper);
  margin-bottom: 4px;
}

.passage-snippet {
  font-size: 12.5px;
  line-height: 1.5;
  color: var(--ink-soft);
  max-height: 90px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Result Summary */
.result-summary {
  background: var(--dark);
  color: var(--cream);
  padding: 28px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 20px;
}

.result-summary h3 {
  font-size: 1.3rem;
  margin: 6px 0 12px;
}

.stats-row {
  display: flex;
  gap: 12px;
}

.stat-pill {
  padding: 6px 12px;
  border-radius: 2px;
  font-family: var(--font-mono);
  font-size: 12px;
}

.stat-pill.danger {
  background: rgba(181, 83, 42, 0.25);
  color: #FFA585;
}

.stat-pill.success {
  background: rgba(94, 122, 74, 0.25);
  color: #A3D485;
}

.summary-right {
  display: flex;
  gap: 12px;
}

/* Review Stage Cards */
.review-items-stack {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.conflict-card {
  background: var(--paper);
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.conflict-card.resolved {
  opacity: 0.75;
  border-color: #5E7A4A;
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.badges {
  display: flex;
  gap: 8px;
  margin-bottom: 8px;
}

.tag {
  font-family: var(--font-mono);
  font-size: 10px;
  padding: 3px 8px;
  border-radius: 2px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.tag-danger {
  background: rgba(181, 83, 42, 0.15);
  color: #B5532A;
}

.tag-sev.high {
  background: rgba(201, 129, 87, 0.2);
  color: var(--copper);
}

.tag-sev.medium {
  background: rgba(194, 164, 92, 0.2);
  color: #7A6028;
}

.tag-status.pending {
  background: #B5532A;
  color: #fff;
}

.tag-status.resolved {
  background: #5E7A4A;
  color: #fff;
}

.thread-info {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-faint);
}

.conflict-summary {
  font-size: 14.5px;
  line-height: 1.6;
  color: var(--ink);
}

.citations-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  margin-top: 8px;
}

.cit-box {
  background: rgba(26, 25, 23, 0.04);
  padding: 12px 14px;
  border-left: 2px solid var(--copper);
}

.cit-head {
  display: flex;
  justify-content: space-between;
  font-family: var(--font-mono);
  font-size: 10px;
  color: var(--ink-faint);
  margin-bottom: 6px;
}

.cit-quote {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--ink-soft);
  line-height: 1.5;
}

.card-bottom {
  border-top: 1px solid var(--hairline);
  padding-top: 14px;
}

.actions-group {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.buttons-row {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

.resolution-badge {
  color: #4D6B3A;
  font-weight: 500;
  font-size: 13.5px;
}

/* Deliverable Tab */
.deliverable-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 16px;
}

.deliverable-actions {
  display: flex;
  gap: 10px;
}

.deliverables-stack {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.deliverable-card {
  background: var(--paper);
  padding: 28px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.deliv-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
}

.deliv-head h3 {
  font-size: 1.4rem;
  margin-top: 4px;
}

.deliv-date {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-faint);
}

.deliv-text {
  font-size: 15px;
  line-height: 1.6;
  color: var(--ink);
}

.deliv-citations {
  background: rgba(26, 25, 23, 0.03);
  padding: 16px 18px;
  border-left: 2px solid var(--olive);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.citations-row {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.deliv-cit-chip {
  display: flex;
  gap: 10px;
  font-size: 12.5px;
  line-height: 1.5;
}

.deliv-cit-chip code {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--copper);
  white-space: nowrap;
}

@media (max-width: 900px) {
  .stage-tabs {
    grid-template-columns: repeat(2, 1fr);
  }
  .control-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 600px) {
  .stage-tabs {
    grid-template-columns: 1fr;
  }
  .nav-left {
    gap: 14px;
  }
  .user-meta {
    display: none;
  }
}
</style>
