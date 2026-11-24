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
const sourceTruthDocId = ref('')
const selectedSourceTruthDocument = computed(() =>
  workspace.currentDocs.find(doc => String(doc.id) === sourceTruthDocId.value)
)

const isPipelineBusy = computed(() =>
  workspace.livePipelineActive || workspace.isReconciling || workspace.isPreviewing
)

const pipelineProgress = computed(() => {
  if (workspace.isPreviewing) {
    return { percent: 45, label: 'Extracting atomic claims & aligning topic clusters…', step: 'PREVIEW' }
  }
  const st = (workspace.liveStatusStage || '').toUpperCase()
  if (st.includes('INGEST') || st.includes('UPLOAD')) {
    return { percent: 18, label: workspace.liveStatusMessage || 'Ingesting & parsing documents…', step: '01 INGEST' }
  }
  if (st.includes('EXTRACT')) {
    return { percent: 42, label: workspace.liveStatusMessage || 'Extracting atomic claims & governance rules…', step: '02 EXTRACT' }
  }
  if (st.includes('CLUSTER') || st.includes('ALIGN') || st.includes('DABBA')) {
    return { percent: 65, label: workspace.liveStatusMessage || 'Building cross-document topic clusters…', step: '03 CLUSTER' }
  }
  if (st.includes('JUDGE') || st.includes('VERDICT') || st.includes('EVAL')) {
    return { percent: 86, label: workspace.liveStatusMessage || 'Evaluating conflicts & verifying citations…', step: '04 JUDGE' }
  }
  if (st.includes('PERSIST') || st.includes('COMPLETE') || st.includes('READY')) {
    return { percent: 98, label: workspace.liveStatusMessage || 'Finalizing reconciliation report…', step: '05 FINALIZE' }
  }
  return { percent: 24, label: workspace.liveStatusMessage || 'Starting reconciliation pipeline…', step: 'RUNNING' }
})

// Auto polling interval for in-flight documents
let pollTimer = null

onMounted(async () => {
  await workspace.fetchProjects()
  startPolling()
})

onUnmounted(() => {
  stopPolling()
})

watch(activeTab, async (newTab) => {
  if (newTab === 'review' && workspace.activeThreadId) {
    await workspace.fetchReviewItems(workspace.activeThreadId)
  } else if (newTab === 'deliverable' && workspace.activeThreadId) {
    await workspace.fetchDeliverables(workspace.activeThreadId)
  }
})

watch(
  () => workspace.complianceAudit,
  (audit) => {
    sourceTruthDocId.value = audit?.source_truth_doc_id
      ? String(audit.source_truth_doc_id)
      : ''
  }
)

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
  workspace.resetState()
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

function inspectDocById(docId) {
  const doc = workspace.currentDocs.find(d => d.id === docId)
  inspectedDocId.value = docId
  inspectedDocName.value = doc?.filename || `Document #${docId}`
  showChunksModal.value = true
}

// 3. Reconcile selection helpers
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

async function onRunLiveReconciliation() {
  try {
    await workspace.startLiveReconciliation((nextTab) => {
      activeTab.value = nextTab
    })
  } catch {
    // handled in store
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
    returnToDeliverableWhenReviewsComplete()
  } catch {
    // handled
  }
}

async function resolveReject(item) {
  try {
    await workspace.resolveConflict(item.id, 'REJECT')
    returnToDeliverableWhenReviewsComplete()
  } catch {
    // handled
  }
}

async function resolveCompliance(item, action) {
  try {
    await workspace.resolveConflict(item.id, action)
    returnToDeliverableWhenReviewsComplete()
  } catch {
    // handled in store
  }
}

async function finalizeUltimateDeliverable() {
  try {
    await workspace.finalizeDeliverable()
  } catch {
    // handled in store
  }
}

async function startSourceTruthComparison() {
  if (!sourceTruthDocId.value) return
  try {
    const result = await workspace.startComplianceCheck(sourceTruthDocId.value)
    if (result.pending_compliance_reviews > 0) activeTab.value = 'review'
  } catch {
    // handled in store
  }
}

async function onSourceTruthDocumentSelected() {
  if (selectedSourceTruthDocument.value?.status === 'FAILED') {
    await workspace.retryDocument(selectedSourceTruthDocument.value.id)
  }
}

function returnToDeliverableWhenReviewsComplete() {
  if (workspace.pendingReviewCount === 0) activeTab.value = 'deliverable'
}

function openCustomResolution(item) {
  selectedReviewItem.value = item
  showCustomModal.value = true
}

async function handleCustomResolution({ reviewItemId, action, customText }) {
  await workspace.resolveConflict(reviewItemId, action, null, customText)
  returnToDeliverableWhenReviewsComplete()
}

// 5. Deliverables & Full Report Export
const compiledReportMarkdown = computed(() => {
  if (!workspace.deliverables.length) return ''
  const lines = []
  lines.push(
    workspace.complianceAudit?.finalized
      ? '# SuperDocs Ultimate Final Deliverable'
      : '# SuperDocs Reconciled Deliverable Draft'
  )
  lines.push(`**Run Thread ID:** \`${workspace.activeThreadId || 'N/A'}\``)
  lines.push(`**Project:** ${workspace.currentProject?.name || 'Untitled'}`)
  lines.push(`**Generated:** ${new Date().toLocaleString()}`)
  lines.push(`---\n`)

  if (workspace.complianceAudit?.finalized) {
    lines.push(`## Compliance Review Sign-off\n`)
    lines.push(`**Status:** ${workspace.complianceAudit.status}`)
    lines.push(`**Source of Truth:** ${workspace.complianceAudit.source_of_truth}`)
    lines.push(`**Sections Checked:** ${workspace.complianceAudit.checked_sections}`)
    lines.push(`\n`)
  }

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
  <div class="studio-shell">
    <!-- Left Sidebar (Reducto Studio Style) -->
    <aside class="studio-sidebar">
      <div class="sidebar-top">
        <div class="sidebar-brand-row">
          <RouterLink to="/" class="brand" aria-label="SuperDocs home">
            <svg width="20" height="20" viewBox="0 0 26 26" fill="none" aria-hidden="true">
              <rect x="3" y="2" width="14" height="18" rx="2" stroke="#09090B" stroke-width="1.8"/>
              <rect x="9" y="6" width="14" height="18" rx="2" fill="#FAFAFA" stroke="#09090B" stroke-width="1.8"/>
              <path d="M12.5 12h7M12.5 15.5h7M12.5 19h4" stroke="#09090B" stroke-width="1.5" stroke-linecap="round"/>
            </svg>
            <span class="brand-title">SuperDocs</span>
          </RouterLink>
          <button class="sidebar-icon-btn" @click="showNewProjectModal = true" title="Create New Project">
            +
          </button>
        </div>

        <nav class="sidebar-nav" aria-label="Workspace Navigation">
          <button
            class="snav-item"
            :class="{ active: activeTab === 'documents' }"
            @click="activeTab = 'documents'"
          >
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M2.5 6.8L8 2.5l5.5 4.3V13.5H10V9.5H6v4H2.5V6.8z" stroke="currentColor" stroke-width="1.35" stroke-linejoin="round"/>
            </svg>
            <span>Home</span>
            <span class="snav-count" v-if="workspace.currentDocs.length">{{ workspace.currentDocs.length }}</span>
          </button>

          <button
            class="snav-item"
            :class="{ active: activeTab === 'reconcile' }"
            @click="activeTab = 'reconcile'"
          >
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <circle cx="4.5" cy="4.5" r="2" stroke="currentColor" stroke-width="1.35"/>
              <circle cx="11.5" cy="4.5" r="2" stroke="currentColor" stroke-width="1.35"/>
              <circle cx="8" cy="11.5" r="2" stroke="currentColor" stroke-width="1.35"/>
              <path d="M6.2 5.5l1.2 4.2M9.8 5.5L8.6 9.7" stroke="currentColor" stroke-width="1.2"/>
            </svg>
            <span>Reconcile</span>
            <span class="snav-dot" v-if="isPipelineBusy"></span>
          </button>

          <button
            class="snav-item"
            :class="{ active: activeTab === 'review' }"
            @click="activeTab = 'review'"
          >
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M3 4h10M3 8h7M3 12h5" stroke="currentColor" stroke-width="1.35" stroke-linecap="round"/>
              <circle cx="12" cy="11" r="2.2" stroke="currentColor" stroke-width="1.35"/>
            </svg>
            <span>Review Gate</span>
            <span class="snav-badge alert" v-if="workspace.pendingReviewCount > 0">
              {{ workspace.pendingReviewCount }}
            </span>
          </button>

          <button
            class="snav-item"
            :class="{ active: activeTab === 'deliverable' }"
            @click="activeTab = 'deliverable'"
          >
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <rect x="3" y="2" width="10" height="12" rx="1.5" stroke="currentColor" stroke-width="1.35"/>
              <path d="M5.5 6h5M5.5 9h5M5.5 11.5h3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/>
            </svg>
            <span>Deliverables</span>
            <span class="snav-count" v-if="workspace.deliverables.length">{{ workspace.deliverables.length }}</span>
          </button>
        </nav>

        <!-- Sidebar Projects Quick-Switcher -->
        <div v-if="workspace.projects.length" class="sidebar-projects">
          <div class="sidebar-sec-head">
            <span>Projects</span>
            <button class="sidebar-add-link" @click="showNewProjectModal = true">+ New</button>
          </div>
          <ul class="sidebar-proj-list">
            <li
              v-for="p in workspace.projects"
              :key="p.id"
              class="sidebar-proj-item"
              :class="{ active: workspace.currentProjectId === p.id }"
              @click="workspace.selectProject(p.id)"
            >
              <span class="proj-name">{{ p.name }}</span>
              <span class="proj-cnt">{{ p.documents?.length || 0 }}</span>
            </li>
          </ul>
        </div>
      </div>

      <!-- Bottom User Profile & Logout -->
      <div class="sidebar-footer">
        <div class="sidebar-user">
          <span class="avatar-sq">{{ auth.user?.first_name?.charAt(0) || 'U' }}</span>
          <div class="user-meta">
            <span class="uname">{{ auth.user?.first_name }} {{ auth.user?.last_name }}</span>
            <span class="uemail">{{ auth.user?.email }}</span>
          </div>
        </div>
        <button class="sidebar-logout" @click="handleLogout" id="app-nav-logout" title="Log out">
          Log out
        </button>
      </div>
    </aside>

    <!-- Main Workspace Area -->
    <main class="app-main">
      <!-- Animated Reconciliation Loading Bar (visible whenever reconciliation / preview runs) -->
      <div v-if="isPipelineBusy" class="reconcile-loader-card" role="status" aria-live="polite">
        <div class="loader-top">
          <div class="loader-left">
            <span class="loader-pulse"></span>
            <span class="loader-step-pill">{{ pipelineProgress.step }}</span>
            <span class="loader-msg">{{ pipelineProgress.label }}</span>
          </div>
          <span class="loader-pct">{{ pipelineProgress.percent }}%</span>
        </div>
        <div class="loader-track">
          <div class="loader-fill" :style="{ width: pipelineProgress.percent + '%' }">
            <div class="loader-shimmer"></div>
          </div>
        </div>
      </div>

      <!-- Global Error Banner -->
      <div v-if="workspace.actionError" class="error-banner">
        <span>⚠ {{ workspace.actionError }}</span>
        <button @click="workspace.actionError = ''">✕</button>
      </div>

      <!-- ========================================================================= -->
      <!-- TAB 1: Home Dashboard (Reducto Studio Style) -->
      <!-- ========================================================================= -->
      <section v-if="activeTab === 'documents'" class="tab-content">
        <FileExplorer
          :on-open-chunks="inspectDocById"
          :on-proceed-to-reconcile="(tab) => { activeTab = (tab || 'reconcile') }"
          @open-new-project-modal="showNewProjectModal = true"
        />
      </section>

      <!-- ========================================================================= -->
      <!-- TAB 2: Topic Clusters & Reconcile (Threshold Removed) -->
      <!-- ========================================================================= -->
      <section v-if="activeTab === 'reconcile'" class="tab-content">
        <div class="content-header">
          <div>
            <span class="label faint">Stage 02 · Reconciliation</span>
            <h2>Topic Clusters & Judge</h2>
            <p class="soft">
              Extracts atomic claims, aligns cross-document topic clusters, and evaluates every contradiction with grounded page citations.
            </p>
          </div>
        </div>

        <!-- Clean Setup & Action Bar (Threshold removed) -->
        <div class="reconcile-controls frame">
          <div class="reconcile-top-bar">
            <div class="doc-selection-summary">
              <span class="label">Selected Documents ({{ workspace.selectedDocIds.length }})</span>
              <p v-if="workspace.selectedDocIds.length < 2" class="warning-text">
                Select at least 2 parsed documents to run reconciliation.
              </p>
              <p v-else class="success-text">
                ✓ Ready across Document IDs: {{ workspace.selectedDocIds.join(', ') }}
              </p>
              <div class="selection-actions">
                <button class="btn-link" @click="selectAllParsed">Select all parsed</button>
                <button class="btn-link" @click="deselectAll">Deselect all</button>
              </div>
            </div>

            <div class="reconcile-actions">
              <button
                class="btn btn-outline"
                :disabled="workspace.selectedDocIds.length < 2 || workspace.isPreviewing || workspace.livePipelineActive"
                @click="onPreviewClusters"
              >
                {{ workspace.isPreviewing ? 'Aligning Clusters…' : 'Preview Clusters' }}
              </button>

              <button
                class="btn btn-ink"
                :disabled="workspace.selectedDocIds.length < 2 || workspace.livePipelineActive || workspace.isReconciling"
                @click="onRunLiveReconciliation"
              >
                {{ workspace.livePipelineActive ? 'Reconciling…' : 'Run Reconciliation →' }}
              </button>
            </div>
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
            <h2>Human-in-the-Loop Review Gate</h2>
            <p class="soft">
              Review source conflicts and compliance findings. Approve a cited source, accept a section as-is, rewrite it, or reject it.
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
                  <template v-if="item.item_type === 'COMPLIANCE'">
                    <button
                      class="btn btn-outline sm"
                      :disabled="workspace.isResolving"
                      @click="resolveCompliance(item, 'APPROVE_AS_IS')"
                    >
                      Approve Section As-Is
                    </button>
                    <button
                      class="btn btn-outline sm"
                      :disabled="workspace.isResolving"
                      @click="openCustomResolution(item)"
                    >
                      Rewrite Section…
                    </button>
                    <button
                      class="btn btn-outline sm alert"
                      :disabled="workspace.isResolving"
                      @click="resolveReject(item)"
                    >
                      Reject Section
                    </button>
                  </template>
                  <template v-else>
                    <button
                      v-for="docId in [...new Set((item.citations || []).map(c => c.doc_id))]"
                      :key="'adopt-' + docId"
                      class="btn btn-outline sm"
                      :disabled="workspace.isResolving"
                      @click="resolveAdoptDoc(item, docId)"
                    >
                      Adopt Doc {{ docId }} Terms
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
                  </template>
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
            <h2>{{ workspace.complianceAudit?.finalized ? 'Ultimate Final Deliverable' : 'Deliverable Draft' }}</h2>
            <p class="soft">
              Synthesized report combining source agreements and human-reviewed decisions.
              {{ workspace.complianceAudit?.finalized ? 'This version passed the compliance review gate and is finalized.' : 'Complete compliance review and finalize before exporting the ultimate deliverable.' }}
            </p>
          </div>
          <div class="deliverable-actions">
            <button class="btn btn-outline sm" :disabled="!workspace.complianceAudit?.finalized" @click="copyReport">
              {{ reportCopied ? '✓ Copied Markdown' : 'Copy Report MD' }}
            </button>
            <button class="btn btn-ink sm" :disabled="!workspace.complianceAudit?.finalized" @click="downloadReport">
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

        <div v-if="workspace.deliverables.length" class="source-truth-selector frame">
          <div>
            <span class="label faint">Next: Source-of-Truth Review</span>
            <h3>Select the authoritative document</h3>
            <p class="soft">
              Compare this draft with one parsed project document. Any differences return to the Human Review Gate before finalization.
            </p>
          </div>
          <div class="field">
            <label for="source-truth-document">Source of truth</label>
            <select
              id="source-truth-document"
              v-model="sourceTruthDocId"
              class="input"
              :disabled="workspace.isCheckingCompliance || workspace.pendingReviewCount > 0"
              @change="onSourceTruthDocumentSelected"
            >
              <option value="" disabled>Select a project document</option>
              <option v-for="doc in workspace.currentDocs" :key="doc.id" :value="String(doc.id)">
                {{ doc.filename }} ({{ doc.status }})
              </option>
            </select>
          </div>
          <p
            v-if="selectedSourceTruthDocument && selectedSourceTruthDocument.status !== 'PARSED'"
            class="warning-text"
          >
            {{
              selectedSourceTruthDocument.status === 'FAILED'
                ? 'Parsing failed. A retry has been queued; comparison will be available when parsing succeeds.'
                : `This document is ${selectedSourceTruthDocument.status.toLowerCase()}. It must finish parsing before comparison.`
            }}
          </p>
          <p v-else-if="selectedSourceTruthDocument" class="success-text">
            Source document is parsed and ready to compare.
          </p>
          <p v-if="workspace.pendingReviewCount" class="warning-text">
            Resolve all {{ workspace.pendingReviewCount }} pending review item(s) before starting or changing the source-of-truth comparison.
          </p>
          <button
            class="btn btn-ink"
            :disabled="
              selectedSourceTruthDocument?.status !== 'PARSED'
              || workspace.pendingReviewCount > 0
              || workspace.isCheckingCompliance
            "
            @click="startSourceTruthComparison"
          >
            {{ workspace.isCheckingCompliance ? 'Comparing Deliverable…' : 'Compare Deliverable' }}
          </button>
        </div>

        <div v-if="workspace.complianceAudit && workspace.complianceAudit.status !== 'NOT_RUN'" class="compliance-audit frame">
          <div class="compliance-summary">
            <div>
              <span class="label faint">Audit Status</span>
              <h3>{{ workspace.complianceAudit.status }}</h3>
            </div>
            <div>
              <span class="label faint">Source of Truth</span>
              <p>{{ workspace.complianceAudit.source_of_truth }}</p>
            </div>
            <div>
              <span class="label faint">Sections Checked</span>
              <p>{{ workspace.complianceAudit.checked_sections ?? 0 }}</p>
            </div>
            <div v-if="workspace.complianceAudit.pending_conflicts">
              <span class="label faint">Pending Conflicts</span>
              <p>{{ workspace.complianceAudit.pending_conflicts }}</p>
            </div>
          </div>

          <div v-if="workspace.complianceAudit.status === 'PENDING_REVIEW'" class="warning-text">
            Resolve all conflicts before the deliverable can receive a final compliance status.
          </div>
          <div v-else-if="workspace.complianceAudit.status === 'NOT_READY'" class="warning-text">
            There are no committed sections to check yet.
          </div>
          <div
            v-if="workspace.complianceAudit.pending_compliance_reviews"
            class="warning-text"
          >
            {{ workspace.complianceAudit.pending_compliance_reviews }} compliance finding(s) need analyst review before finalization.
            <button class="btn-link" @click="activeTab = 'review'">Open Human Review Gate</button>
          </div>

          <article
            v-for="check in workspace.complianceAudit.checks"
            :key="check.rule_id"
            class="compliance-rule"
          >
            <div class="compliance-rule-header">
              <h3>{{ check.requirement }}</h3>
              <span :class="['compliance-result', check.status.toLowerCase()]">{{ check.status }}</span>
            </div>
            <ul v-if="check.findings.length">
              <li v-for="(finding, index) in check.findings" :key="index">
                <strong>{{ finding.section }}</strong>
                <span v-if="finding.doc_id"> — Doc {{ finding.doc_id }}, page {{ finding.page_number }}:</span>
                {{ finding.message || finding.explanation }}
                <ul v-if="finding.unsupported_claims?.length">
                  <li v-for="(claim, claimIndex) in finding.unsupported_claims" :key="claimIndex">
                    {{ claim }}
                  </li>
                </ul>
              </li>
            </ul>
            <p
              v-if="!check.findings.length && !check.section_results?.length"
              class="success-text"
            >
              No findings.
            </p>
            <ul v-if="check.section_results?.length">
              <li v-for="(result, index) in check.section_results" :key="index">
                <strong>{{ result.section }}</strong> — {{ result.status }}:
                {{ result.explanation }}
                <ul v-if="result.unsupported_claims.length">
                  <li v-for="(claim, claimIndex) in result.unsupported_claims" :key="claimIndex">
                    {{ claim }}
                  </li>
                </ul>
              </li>
            </ul>
          </article>
          <div class="finalize-deliverable">
            <p v-if="workspace.complianceAudit.finalized" class="success-text">
              Ultimate final deliverable is finalized and ready to export.
            </p>
            <button
              v-else-if="['COMPLIANT', 'HUMAN_APPROVED'].includes(workspace.complianceAudit.status)"
              class="btn btn-ink"
              :disabled="
                workspace.isFinalizingDeliverable
                || workspace.pendingReviewCount > 0
                || !['COMPLIANT', 'HUMAN_APPROVED'].includes(workspace.complianceAudit.status)
              "
              @click="finalizeUltimateDeliverable"
            >
              {{ workspace.isFinalizingDeliverable ? 'Finalizing…' : 'Finalize Ultimate Deliverable' }}
            </button>
          </div>
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
/* =========================================================
   REDUCTO STUDIO SHELL (LEFT SIDEBAR + WHITE CANVAS)
   ========================================================= */
.studio-shell {
  min-height: 100vh;
  display: grid;
  grid-template-columns: 236px minmax(0, 1fr);
  background: var(--surface);
  color: var(--ink);
}

.studio-sidebar {
  background: var(--paper);
  border-right: 1px solid var(--hairline);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 16px 12px;
  position: sticky;
  top: 0;
  height: 100vh;
  overflow-y: auto;
}

.sidebar-top {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.sidebar-brand-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 8px;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 15.5px;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--ink);
}

.sidebar-icon-btn {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  border: 1px solid var(--hairline);
  background: var(--surface);
  color: var(--ink-soft);
  font-size: 16px;
  line-height: 1;
  cursor: pointer;
  display: grid;
  place-items: center;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.sidebar-icon-btn:hover {
  background: var(--dark);
  color: #FFFFFF;
  border-color: var(--dark);
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.snav-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: none;
  border-radius: 7px;
  background: transparent;
  color: var(--ink-soft);
  font-size: 13.5px;
  font-weight: 500;
  cursor: pointer;
  text-align: left;
  transition: background 0.14s, color 0.14s;
}

.snav-item:hover {
  background: #EFEFF1;
  color: var(--ink);
}

.snav-item.active {
  background: #EAEAEF;
  color: var(--ink);
  font-weight: 600;
}

.snav-count {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 10.5px;
  color: var(--ink-faint);
}

.snav-badge.alert {
  margin-left: auto;
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  background: var(--dark);
  color: #FFFFFF;
  padding: 2px 7px;
  border-radius: 999px;
}

.snav-dot {
  margin-left: auto;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--dark);
  animation: pulse 1.2s infinite;
}

/* Sidebar Projects */
.sidebar-projects {
  border-top: 1px solid var(--hairline);
  padding-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sidebar-sec-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 8px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--ink-faint);
}

.sidebar-add-link {
  border: none;
  background: none;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-soft);
  cursor: pointer;
}
.sidebar-add-link:hover { color: var(--ink); }

.sidebar-proj-list {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sidebar-proj-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 7px 10px;
  border-radius: 6px;
  font-size: 13px;
  color: var(--ink-soft);
  cursor: pointer;
  transition: background 0.14s, color 0.14s;
}
.sidebar-proj-item:hover {
  background: #EFEFF1;
  color: var(--ink);
}
.sidebar-proj-item.active {
  background: var(--dark);
  color: #FFFFFF;
  font-weight: 500;
}
.proj-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.proj-cnt {
  font-family: var(--font-mono);
  font-size: 10.5px;
  opacity: 0.65;
}

/* Sidebar Footer */
.sidebar-footer {
  border-top: 1px solid var(--hairline);
  padding-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.sidebar-user {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 4px;
}

.avatar-sq {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: var(--dark);
  color: #FFFFFF;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

.user-meta {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.uname {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--ink);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.uemail {
  font-size: 11px;
  color: var(--ink-faint);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.sidebar-logout {
  width: 100%;
  padding: 7px 10px;
  border-radius: 7px;
  border: 1px solid var(--hairline);
  background: var(--surface);
  color: var(--ink-soft);
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.sidebar-logout:hover {
  background: var(--dark);
  color: #FFFFFF;
  border-color: var(--dark);
}

/* =========================================================
   MAIN WORKSPACE AREA
   ========================================================= */
.app-main {
  flex: 1;
  width: 100%;
  max-width: 1120px;
  margin: 0 auto;
  padding: 32px clamp(20px, 4vw, 48px) 72px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.tab-content {
  display: flex;
  flex-direction: column;
  gap: 22px;
  animation: fadeSlideUp 0.25s cubic-bezier(.22, 1, .36, 1);
}

.content-header h2 {
  font-family: var(--font-body);
  font-size: clamp(1.5rem, 2.2vw, 1.85rem);
  font-weight: 600;
  letter-spacing: -0.025em;
  margin: 4px 0 6px;
  color: var(--ink);
}

.soft {
  color: var(--ink-soft);
  max-width: 720px;
  font-size: 14px;
}

.gold { color: var(--ink); }
.faint { color: var(--ink-faint); }

/* =========================================================
   ANIMATED RECONCILIATION LOADING BAR
   ========================================================= */
.reconcile-loader-card {
  background: var(--surface);
  border: 1px solid var(--hairline-strong);
  border-radius: var(--radius-md);
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  box-shadow: var(--shadow-md);
  animation: fadeSlideUp 0.2s ease;
}

.loader-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.loader-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.loader-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--dark);
  animation: pulse 1.2s infinite;
}

.loader-step-pill {
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.08em;
  background: var(--dark);
  color: #FFFFFF;
  padding: 3px 9px;
  border-radius: 999px;
}

.loader-msg {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--ink);
}

.loader-pct {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--ink);
}

.loader-track {
  width: 100%;
  height: 7px;
  border-radius: 999px;
  background: var(--paper-deep);
  overflow: hidden;
  position: relative;
}

.loader-fill {
  height: 100%;
  border-radius: 999px;
  background: var(--dark);
  position: relative;
  overflow: hidden;
  transition: width 0.55s cubic-bezier(.22, 1, .36, 1);
}

.loader-shimmer {
  position: absolute;
  inset: 0;
  width: 45%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.35), transparent);
  animation: shimmerSlide 1.4s ease-in-out infinite;
}

.error-banner {
  background: var(--danger-soft);
  border-left: 3px solid var(--danger);
  border-radius: var(--radius-sm);
  padding: 12px 16px;
  color: var(--danger);
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13.5px;
  font-weight: 500;
}
.error-banner button {
  background: none;
  border: none;
  cursor: pointer;
  font-size: 15px;
  color: inherit;
}

.empty-state {
  text-align: center;
  padding: 52px 24px;
  color: var(--ink-soft);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
}

/* =========================================================
   TAB 2: RECONCILE & CLUSTERS (CLEAN, NO THRESHOLD)
   ========================================================= */
.reconcile-controls {
  background: var(--surface);
  padding: 22px 24px;
  border: 1px solid var(--hairline);
}

.reconcile-top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  flex-wrap: wrap;
}

.doc-selection-summary {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.warning-text {
  color: var(--danger);
  font-size: 13px;
  font-weight: 500;
  margin: 4px 0;
}

.success-text {
  color: var(--success);
  font-size: 13px;
  font-weight: 500;
  margin: 4px 0;
}

.selection-actions {
  display: flex;
  gap: 14px;
  margin-top: 4px;
}

.btn-link {
  background: none;
  border: none;
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-soft);
  border-bottom: 1px solid var(--hairline-strong);
  cursor: pointer;
  padding-bottom: 1px;
}
.btn-link:hover {
  color: var(--ink);
  border-color: var(--ink);
}

.reconcile-actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}

/* Dabbe Grid */
.clusters-section {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.section-title h3 {
  font-size: 1.25rem;
  font-weight: 600;
  margin-top: 4px;
}

.dabbe-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
  gap: 16px;
}

.dabba-card {
  background: var(--surface);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}

.dabba-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--shadow-md);
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
  font-weight: 500;
  background: var(--dark);
  color: #FFFFFF;
  padding: 3px 9px;
  border-radius: 6px;
}

.docs-tag, .chunks-tag {
  font-family: var(--font-mono);
  font-size: 10.5px;
  background: var(--paper-deep);
  color: var(--ink-soft);
  padding: 3px 8px;
  border-radius: 6px;
}

.passages-stack {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.passage-box {
  background: var(--paper);
  border-left: 2.5px solid var(--ink);
  border-radius: 0 6px 6px 0;
  padding: 10px 12px;
}

.passage-doc {
  display: block;
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 600;
  color: var(--ink);
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

/* Result Summary Banner */
.result-summary {
  background: var(--dark);
  color: #FFFFFF;
  padding: 24px 28px;
  border-color: var(--hairline-dark);
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 18px;
}

.result-summary .gold { color: #A1A1AA; }

.result-summary h3 {
  font-size: 1.25rem;
  font-weight: 600;
  margin: 6px 0 12px;
}

.result-summary code {
  font-family: var(--font-mono);
  font-size: 0.9em;
  background: rgba(255, 255, 255, 0.1);
  padding: 2px 8px;
  border-radius: 4px;
  color: #FFFFFF;
}

.stats-row { display: flex; gap: 10px; flex-wrap: wrap; }

.stat-pill {
  padding: 5px 12px;
  border-radius: 999px;
  font-family: var(--font-mono);
  font-size: 11.5px;
}

.stat-pill.danger {
  background: rgba(185, 28, 28, 0.25);
  color: #FCA5A5;
}

.stat-pill.success {
  background: rgba(21, 128, 61, 0.25);
  color: #86EFAC;
}

.summary-right { display: flex; gap: 10px; flex-wrap: wrap; }

.result-summary .btn-ink {
  background: #FFFFFF;
  color: var(--dark);
}
.result-summary .btn-ink:hover { background: #E4E4E7; }
.result-summary .btn-outline {
  background: transparent;
  color: #FFFFFF;
  border-color: var(--hairline-dark);
}
.result-summary .btn-outline:hover {
  border-color: #71717A;
  background: rgba(255, 255, 255, 0.08);
}

/* =========================================================
   TAB 3: HUMAN REVIEW GATE
   ========================================================= */
.review-items-stack {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.conflict-card {
  background: var(--surface);
  padding: 24px 26px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  border-left: 3.5px solid var(--dark);
  transition: box-shadow 0.2s ease, opacity 0.2s ease;
}

.conflict-card:hover { box-shadow: var(--shadow-md); }

.conflict-card.resolved {
  opacity: 0.8;
  border-left-color: var(--success);
  background: #FCFEFD;
}

.card-top {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 14px;
  flex-wrap: wrap;
}

.topic-info h3 {
  font-size: 1.2rem;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: var(--ink);
}

.badges { display: flex; gap: 6px; margin-bottom: 8px; flex-wrap: wrap; }

.tag {
  font-family: var(--font-mono);
  font-size: 10px;
  font-weight: 600;
  padding: 3px 8px;
  border-radius: 999px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.tag-danger { background: var(--danger-soft); color: var(--danger); }
.tag-sev.high { background: var(--paper-deep); color: var(--ink); }
.tag-sev.medium { background: var(--paper-deep); color: var(--ink-soft); }
.tag-status.pending { background: var(--dark); color: #FFFFFF; }
.tag-status.resolved { background: var(--success); color: #FFFFFF; }

.thread-info {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-faint);
  background: var(--paper);
  padding: 3px 9px;
  border-radius: 6px;
}

.conflict-summary {
  font-size: 14px;
  line-height: 1.65;
  color: var(--ink);
}

.citations-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.citations-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
  gap: 12px;
}

.cit-box {
  background: var(--paper);
  padding: 13px 15px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--hairline);
  border-left: 2.5px solid var(--ink);
}

.cit-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 600;
  color: var(--ink);
  margin-bottom: 6px;
}

.cit-page {
  background: var(--surface);
  color: var(--ink-soft);
  padding: 2px 7px;
  border-radius: 999px;
  border: 1px solid var(--hairline);
}

.cit-quote {
  font-family: var(--font-mono);
  font-size: 12px;
  color: var(--ink-soft);
  line-height: 1.55;
}

.card-bottom {
  border-top: 1px solid var(--hairline);
  padding-top: 14px;
}

.actions-group { display: flex; flex-direction: column; gap: 8px; }
.buttons-row { display: flex; gap: 8px; flex-wrap: wrap; }
.buttons-row .btn.sm { padding: 7px 14px; font-size: 12.5px; }

.buttons-row .btn-outline.alert {
  color: var(--danger);
  border-color: rgba(185, 28, 28, 0.3);
}
.buttons-row .btn-outline.alert:hover {
  background: var(--danger-soft);
  border-color: var(--danger);
}

.resolution-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  background: var(--success-soft);
  color: var(--success);
  padding: 7px 13px;
  border-radius: 6px;
  font-weight: 500;
  font-size: 13px;
}

/* =========================================================
   TAB 4: DELIVERABLES & COMPLIANCE
   ========================================================= */
.deliverable-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 16px;
}

.deliverable-actions { display: flex; gap: 8px; }
.deliverables-stack { display: flex; flex-direction: column; gap: 16px; }

.deliverable-card {
  background: var(--surface);
  padding: 24px 28px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  border-top: 2.5px solid var(--dark);
}

.deliv-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.deliv-head h3 {
  font-size: 1.25rem;
  font-weight: 600;
  margin-top: 4px;
}

.deliv-date {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--ink-faint);
}

.deliv-text {
  font-size: 14.5px;
  line-height: 1.65;
  color: var(--ink);
  white-space: pre-wrap;
}

.deliv-citations {
  background: var(--paper);
  padding: 14px 16px;
  border-radius: 6px;
  border-left: 2.5px solid var(--dark);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.citations-row { display: flex; flex-direction: column; gap: 6px; }

.deliv-cit-chip {
  display: flex;
  gap: 10px;
  align-items: baseline;
  font-size: 12.5px;
  color: var(--ink-soft);
}

.deliv-cit-chip code {
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 600;
  color: var(--ink);
  background: var(--paper-deep);
  padding: 2px 7px;
  border-radius: 4px;
  white-space: nowrap;
}

.source-truth-selector {
  align-items: flex-end;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  justify-content: space-between;
  padding: 22px 24px;
  background: var(--surface);
}
.source-truth-selector h3 { font-size: 1.15rem; font-weight: 600; margin: 4px 0; }
.source-truth-selector .field { flex: 1; min-width: 240px; }

.compliance-audit {
  display: flex;
  flex-direction: column;
  gap: 18px;
  padding: 24px;
  background: var(--surface);
}

.compliance-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  justify-content: space-between;
  padding: 16px 18px;
  background: var(--paper);
  border-radius: 6px;
  border: 1px solid var(--hairline);
}
.compliance-summary h3 { font-family: var(--font-mono); font-size: 1rem; color: var(--ink); margin-top: 4px; }
.compliance-summary p { margin-top: 4px; font-weight: 500; }

.compliance-rule { border-top: 1px solid var(--hairline); padding-top: 16px; }
.finalize-deliverable { border-top: 1px solid var(--hairline); display: flex; justify-content: flex-end; padding-top: 18px; }
.compliance-rule-header { display: flex; gap: 14px; justify-content: space-between; align-items: flex-start; }
.compliance-rule-header h3 { font-size: 0.98rem; font-weight: 600; }
.compliance-rule ul { margin-top: 10px; padding-left: 20px; }
.compliance-rule li { margin-top: 6px; font-size: 13.5px; color: var(--ink-soft); }

.compliance-result {
  border-radius: 999px;
  font-family: var(--font-mono);
  font-size: 10.5px;
  font-weight: 600;
  padding: 3px 9px;
}
.compliance-result.pass { background: var(--success-soft); color: var(--success); }
.compliance-result.fail { background: var(--danger-soft); color: var(--danger); }
.compliance-result.needs_review { background: var(--paper-deep); color: var(--ink); }
.compliance-result.not_applicable { background: var(--paper-deep); color: var(--ink-soft); }

@media (max-width: 860px) {
  .studio-shell { grid-template-columns: 1fr; }
  .studio-sidebar {
    position: static;
    height: auto;
    border-right: none;
    border-bottom: 1px solid var(--hairline);
  }
  .sidebar-nav { flex-direction: row; flex-wrap: wrap; }
  .snav-item { width: auto; }
  .sidebar-projects { display: none; }
}
</style>
