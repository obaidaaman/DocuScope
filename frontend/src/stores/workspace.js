import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import api, { errorMessage } from '../api/client'

export const useWorkspaceStore = defineStore('workspace', () => {
  const projects = ref([])
  const currentProjectId = ref(null)
  const currentProject = ref(null)
  const loadingProjects = ref(false)
  const loadingDocs = ref(false)

  // Reconciliation state
  const selectedDocIds = ref([])
  const similarityThreshold = ref(0.45)
  const maxPairs = ref(300)
  const activeThreadId = ref('')
  const clustersPreview = ref(null)
  const reconciliationResult = ref(null)
  const reviewItems = ref([])
  const deliverables = ref([])

  // Loading flags
  const isPreviewing = ref(false)
  const isReconciling = ref(false)
  const isResolving = ref(false)
  const isUploading = ref(false)
  const actionError = ref('')

  const currentDocs = computed(() => currentProject.value?.documents || [])
  const parsedDocs = computed(() => currentDocs.value.filter(d => d.status === 'PARSED'))
  const pendingReviewCount = computed(() => reviewItems.value.filter(i => i.status === 'PENDING').length)

  // 1. Projects
  async function fetchProjects() {
    loadingProjects.value = true
    try {
      const { data } = await api.get('/projects')
      projects.value = data
      if (data.length > 0 && !currentProjectId.value) {
        await selectProject(data[0].id)
      }
    } catch (err) {
      actionError.value = errorMessage(err)
    } finally {
      loadingProjects.value = false
    }
  }

  async function createProject(name, orgId = null) {
    try {
      const { data } = await api.post('/projects', { name, org_id: orgId })
      await fetchProjects()
      if (data?.project?.id) {
        await selectProject(data.project.id)
      }
      return data.project
    } catch (err) {
      throw new Error(errorMessage(err))
    }
  }

  async function selectProject(projectId) {
    currentProjectId.value = projectId
    loadingDocs.value = true
    try {
      const { data } = await api.get(`/projects/${projectId}`)
      currentProject.value = data
      // auto select first 3 parsed docs by default if available
      const parsed = data.documents?.filter(d => d.status === 'PARSED') || []
      selectedDocIds.value = parsed.slice(0, 3).map(d => d.id)
    } catch (err) {
      actionError.value = errorMessage(err)
    } finally {
      loadingDocs.value = false
    }
  }

  async function refreshCurrentProject() {
    if (!currentProjectId.value) return
    try {
      const { data } = await api.get(`/projects/${currentProjectId.value}`)
      currentProject.value = data
    } catch {
      // silent refresh
    }
  }

  // 2. Document upload & management
  async function uploadDocuments(files) {
    if (!currentProjectId.value) {
      const msg = 'Please select or create a project before uploading documents.'
      actionError.value = msg
      throw new Error(msg)
    }
    if (!files || files.length === 0) return
    isUploading.value = true
    actionError.value = ''
    try {
      const formData = new FormData()
      for (const file of files) {
        formData.append('files', file)
      }
      const { data } = await api.post(`/documents/upload?project_id=${currentProjectId.value}`, formData)
      await refreshCurrentProject()
      return data
    } catch (err) {
      actionError.value = errorMessage(err)
      throw new Error(errorMessage(err))
    } finally {
      isUploading.value = false
    }
  }

  async function retryDocument(docId) {
    try {
      await api.post(`/documents/${docId}/retry`)
      await refreshCurrentProject()
    } catch (err) {
      actionError.value = errorMessage(err)
    }
  }

  async function fetchDocumentChunks(docId) {
    try {
      const { data } = await api.get(`/documents/${docId}/chunks`)
      return data
    } catch (err) {
      throw new Error(errorMessage(err))
    }
  }

  // 3. Reconciliation
  async function previewClusters() {
    if (selectedDocIds.value.length < 2) {
      actionError.value = 'Please select at least 2 parsed documents to cluster.'
      return
    }
    isPreviewing.value = true
    actionError.value = ''
    try {
      const payload = {
        doc_ids: selectedDocIds.value,
        similarity_threshold: Number(similarityThreshold.value),
        max_pairs: Number(maxPairs.value),
        thread_id: activeThreadId.value || undefined
      }
      const { data } = await api.post('/reconciliation/clusters-preview', payload)
      clustersPreview.value = data
      return data
    } catch (err) {
      actionError.value = errorMessage(err)
      throw new Error(errorMessage(err))
    } finally {
      isPreviewing.value = false
    }
  }

  async function runReconciliation() {
    if (selectedDocIds.value.length < 2) {
      actionError.value = 'Please select at least 2 parsed documents to reconcile.'
      return
    }
    isReconciling.value = true
    actionError.value = ''
    try {
      const thread = activeThreadId.value || 'thread_' + Math.floor(Math.random() * 100000000)
      activeThreadId.value = thread

      const payload = {
        doc_ids: selectedDocIds.value,
        similarity_threshold: Number(similarityThreshold.value),
        max_pairs: Number(maxPairs.value),
        thread_id: thread
      }
      const { data } = await api.post('/reconciliation/reconcile', payload)
      reconciliationResult.value = data
      activeThreadId.value = data.thread_id

      // Fetch review items and deliverables immediately
      await fetchReviewItems(data.thread_id)
      await fetchDeliverables(data.thread_id)
      return data
    } catch (err) {
      actionError.value = errorMessage(err)
      throw new Error(errorMessage(err))
    } finally {
      isReconciling.value = false
    }
  }

  async function fetchReviewItems(threadId = null) {
    const tid = threadId || activeThreadId.value
    if (!tid) return
    try {
      const { data } = await api.get(`/reconciliation/${tid}/review-items`)
      reviewItems.value = data
    } catch (err) {
      actionError.value = errorMessage(err)
    }
  }

  async function fetchDeliverables(threadId = null) {
    const tid = threadId || activeThreadId.value
    if (!tid) return
    try {
      const { data } = await api.get(`/reconciliation/${tid}/deliverables`)
      deliverables.value = data
    } catch (err) {
      actionError.value = errorMessage(err)
    }
  }

  async function resolveConflict(reviewItemId, action, chosenDocId = null, customText = null) {
    if (!activeThreadId.value) return
    isResolving.value = true
    actionError.value = ''
    try {
      const payload = {
        thread_id: activeThreadId.value,
        resolutions: [
          {
            review_item_id: reviewItemId,
            action,
            chosen_doc_id: chosenDocId,
            custom_text: customText
          }
        ]
      }
      await api.post('/reconciliation/resolve-gate', payload)
      // re-sync review items and deliverables
      await fetchReviewItems(activeThreadId.value)
      await fetchDeliverables(activeThreadId.value)
    } catch (err) {
      actionError.value = errorMessage(err)
      throw new Error(errorMessage(err))
    } finally {
      isResolving.value = false
    }
  }

  return {
    projects,
    currentProjectId,
    currentProject,
    currentDocs,
    parsedDocs,
    selectedDocIds,
    similarityThreshold,
    maxPairs,
    activeThreadId,
    clustersPreview,
    reconciliationResult,
    reviewItems,
    deliverables,
    pendingReviewCount,
    loadingProjects,
    loadingDocs,
    isUploading,
    isPreviewing,
    isReconciling,
    isResolving,
    actionError,
    fetchProjects,
    createProject,
    selectProject,
    refreshCurrentProject,
    uploadDocuments,
    retryDocument,
    fetchDocumentChunks,
    previewClusters,
    runReconciliation,
    fetchReviewItems,
    fetchDeliverables,
    resolveConflict
  }
})
