# SuperDocs Developer Guide: Architecture, Workflows & Database

This document explains the end-to-end mechanics of **SuperDocs** for developers. It details how the system runs, how state transitions through PostgreSQL, how database rows mutate at each step, and how the core AI/ML reconciliation pipeline functions.

---

## 1. System High-Level Architecture

The system consists of a Vue 3 SPA frontend and a FastAPI backend with PostgreSQL + `pgvector` for vector storage, Unstructured Cloud for document parsing, and OpenAI for vision enrichment, embeddings, topic discovery, and arbitration.

```mermaid
flowchart TD
    subgraph Client["Frontend (Vue 3 + Pinia)"]
        UI["SPA Views (AppView / LandingView)"]
        Store["Pinia Stores (auth.js, workspace.js)"]
        WSClient["WebSocket Client (/reconciliation/ws/{thread_id})"]
    end

    subgraph Server["Backend (FastAPI)"]
        Router["FastAPI Routers (auth, project, document, reconciliation)"]
        Controller["Controllers & Business Logic"]
        LangGraphPipe["LangGraph Reconciliation Engine (graph.py)"]
        WSManager["WebSocket Connection Manager (ws_manager)"]
    end

    subgraph AI["External AI Services"]
        Unstructured["Unstructured Cloud API (OCR & Elements)"]
        OpenAIVision["OpenAI gpt-4o-mini (Vision / Table Summaries)"]
        OpenAIEmbed["OpenAI text-embedding-3-small (1536-dim)"]
        OpenAIJudge["OpenAI LLM Judge (Structured Reconciliation)"]
    end

    subgraph Data["PostgreSQL + pgvector"]
        DB[(Relational Tables & Vector Index)]
        Disk[("Local Storage (/storage/*.pdf)")]
    end

    UI <--> Store
    Store <--> Router
    WSClient <--> WSManager
    Router --> Controller
    Controller --> LangGraphPipe
    Controller --> DB
    Controller --> Disk
    LangGraphPipe --> DB
    LangGraphPipe --> WSManager
    LangGraphPipe --> OpenAIJudge

    Controller --> Unstructured
    Controller --> OpenAIVision
    Controller --> OpenAIEmbed
```

---

## 2. Database Schema & Entity Relationships

The database is built on PostgreSQL with the `pgvector` extension. All primary tables and relations are declared in [`bakcend/src/models/db_models.py`](file:///Users/obaidaccount/Project/SuperDocs-Engineering/bakcend/src/models/db_models.py).

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ USERS : "has members"
    ORGANIZATIONS ||--o{ PROJECTS : "owns"
    USERS ||--o{ REFRESH_TOKENS : "issues"
    USERS ||--o{ PROJECTS : "creates"
    PROJECTS ||--o{ DOCUMENTS : "contains"
    DOCUMENTS ||--o{ DOCUMENT_CHUNKS : "partitioned into"
    
    ORGANIZATIONS {
        int id PK
        string name
        datetime created_at
    }

    USERS {
        int id PK
        string email UK
        string password_hash
        string first_name
        string last_name
        int org_id FK
        datetime created_at
    }

    PROJECTS {
        int id PK
        string name
        int org_id FK
        int created_by_id FK
        datetime created_at
    }

    DOCUMENTS {
        int id PK
        string filename
        string file_hash UK
        string storage_path
        string status "QUEUED | PROCESSING | PARSED | FAILED"
        text error_message
        int project_id FK
        datetime created_at
    }

    DOCUMENT_CHUNKS {
        int id PK
        int document_id FK
        int chunk_index
        int page_number
        text searchable_content
        vector embedding "1536 dimensions"
        text raw_text
        jsonb tables_html
        boolean has_images
        jsonb metadata_info
        datetime created_at
    }

    REVIEW_ITEMS {
        int id PK
        string run_thread_id
        string item_type "CONFLICT"
        string category
        string severity "HIGH | MEDIUM | LOW | NONE"
        text summary
        jsonb citations_json
        string status "PENDING | RESOLVED"
        text resolution_notes
        datetime created_at
    }

    DELIVERABLE_SECTIONS {
        int id PK
        string run_thread_id
        string category
        string title
        text committed_markdown
        jsonb citations_json
        datetime created_at
    }
```

### Table Roles & Key Columns

1. **`organizations`**: Multi-tenant barrier. A project cannot be created without an `org_id`.
2. **`users` & `refresh_tokens`**: Authentication & JWT lifecycle (HMAC SHA-256 access tokens + database-backed revocable refresh tokens).
3. **`projects`**: The workspace folder grouping related contracts, amendments, and invoices.
4. **`documents`**: Tracks file status (`QUEUED` $\to$ `PROCESSING` $\to$ `PARSED` or `FAILED`). `file_hash` (SHA-256) enforces deduplication.
5. **`document_chunks`**: The atomic unit of text, tables, and embeddings.
   - `searchable_content`: Text enriched with AI table descriptions and image descriptions.
   - `embedding`: 1536-dimension vector for cosine similarity searches (`embedding <=> query`).
   - `tables_html`: Preserved HTML tables extracted during OCR.
   - `page_number`: Crucial for grounded source verification.
6. **`review_items`**: Unresolved conflicts produced by the LLM Judge awaiting human decision.
   - `citations_json`: Array of `{ doc_id, page_number, exact_quote }`.
   - `status`: `PENDING` $\to$ `RESOLVED`.
7. **`deliverable_sections`**: The finalized clauses committed to the final report (both direct agreements and human-resolved conflicts).

---

## 3. End-to-End Lifecycle & Database Updates

The application lifecycle proceeds through four core stages.

### Stage 1: Ingestion & Enrichment Flow

When a user uploads files (e.g. `POST /documents/upload?project_id=1`):

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Frontend as Frontend (FileExplorer)
    participant DocController as Document Controller
    participant DB as PostgreSQL
    participant Worker as Background Task (pipeline.py)
    participant Unstructured as Unstructured Cloud API
    participant OpenAI as OpenAI APIs

    User->>Frontend: Drag & drop PDF files
    Frontend->>DocController: POST /documents/upload (files, project_id)
    DocController->>DB: Check file_hash (SHA-256)
    DocController->>DB: INSERT into documents (status='QUEUED')
    DocController-->>Frontend: Return queued documents list
    DocController->>Worker: Dispatch background ingestion task

    Worker->>DB: UPDATE documents SET status='PROCESSING'
    Worker->>Unstructured: Upload PDF for serverless OCR & partitioning
    Unstructured-->>Worker: Atomic layout elements (Text, Tables, Images)
    Worker->>Worker: Pure-Python chunk_by_title (2400-3000 chars)

    loop For Each Chunk
        alt Contains Table or Image
            Worker->>OpenAI: gpt-4o-mini Vision (generate descriptive summary)
            OpenAI-->>Worker: Enriched searchable_content
        else Plain Text
            Worker->>Worker: searchable_content = raw_text
        end
    end

    Worker->>OpenAI: text-embedding-3-small (Batch embedding of searchable_content)
    OpenAI-->>Worker: 1536-dim vectors
    Worker->>DB: INSERT into document_chunks (text, embedding, tables_html, page_number)
    Worker->>DB: UPDATE documents SET status='PARSED'
```

---

### Stage 2: Reconciliation & LLM Judge Engine

Reconciliation can be started synchronously (`POST /reconciliation/reconcile`) or via the streaming WebSocket pipeline (`POST /reconciliation/start-live-pipeline`):

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Frontend as Frontend (Reconcile Tab)
    participant WS as WebSocket Channel
    participant Graph as LangGraph Engine (graph.py)
    participant Clusterer as clusterer.py
    participant Judge as judge.py (gpt-4o-mini)
    participant DB as PostgreSQL

    User->>Frontend: Click "Run Live Reconciliation"
    Frontend->>WS: Connect ws://.../reconciliation/ws/{thread_id}
    Frontend->>Graph: Execute Reconciliation Graph

    Note over Graph,Clusterer: Node 1: Ingestion verification (ensures PARSED)
    Note over Graph,Clusterer: Node 2: Build Topic Clusters

    Graph->>Clusterer: build_topic_clusters(doc_ids)
    Clusterer->>DB: extract_document_outlines(doc_ids)
    Clusterer->>Judge: discover_dynamic_topic_anchors(outlines)
    Judge-->>Clusterer: 3-6 TopicAnchors + search_query
    
    loop For Each TopicAnchor
        Clusterer->>DB: pgvector cosine match on (1 - (embedding <=> topic_vec))
        Clusterer->>DB: Expand window to [k-1, k, k+1] chunks
        Clusterer->>Clusterer: Form TopicCluster ("Dabba")
    end
    Clusterer-->>Graph: Return TopicClusters
    Graph->>WS: Broadcast CLUSTERS_READY

    Note over Graph,Judge: Node 3: LLM Judge Arbitration
    loop For Each TopicCluster (Concurrency: 5)
        Graph->>Judge: evaluate_single_dabba(cluster)
        Judge-->>Graph: JudgeVerdict (CONFLICT or AGREEMENT, evidence quotes)
        Graph->>WS: Broadcast VERDICT_STREAM
    end

    Note over Graph,DB: Node 4: Persist Results
    alt Verdict == 'CONFLICT'
        Graph->>DB: INSERT into review_items (status='PENDING', citations_json)
    else Verdict == 'AGREEMENT'
        Graph->>DB: INSERT into deliverable_sections (committed_markdown, citations_json)
    end

    Graph->>WS: Broadcast REVIEW_GATE_READY
```

---

### Stage 3: Human-in-the-Loop Review Gate & Deliverable Compilation

When conflicts are detected, they appear in Tab 3 ("Conflict Review Gate").

```mermaid
flowchart TD
    ReviewItem["ReviewItem in DB (status='PENDING')\nCitations: Doc 27 (Quote A) vs Doc 28 (Quote B)"] --> UI["Frontend Card with Dynamic Action Buttons"]
    
    UI --> OptA["Action: APPROVE_DOC\nUser clicks 'Adopt Doc 28 Terms'"]
    UI --> OptB["Action: CUSTOM_RESOLUTION\nUser inputs custom legal clause"]
    UI --> OptC["Action: REJECT\nUser rejects conflicting claims"]

    OptA --> API["POST /reconciliation/resolve-gate\n(thread_id, resolutions)"]
    OptB --> API
    OptC --> API

    subgraph DBUpdate["reconciliation_controller.py Execution"]
        API --> Step1["UPDATE review_items SET status='RESOLVED', resolution_notes=..."]
        API --> Step2["UPSERT into deliverable_sections:"]
        Step2 --> ResA["For APPROVE_DOC: Extract adopted quote and keep only chosen doc's citations"]
        Step2 --> ResB["For CUSTOM_RESOLUTION: Commit custom markdown clause"]
        Step2 --> ResC["For REJECT: Commit explicit audit rejection note"]
    end

    DBUpdate --> Deliv["Final Grounded Deliverable Register\n(deliverable_sections table)"]
```

---

## 4. Grounded Deliverable Register & Export Mechanics

The deliverable is the final synthesis fulfilling the core requirement: **"produces one grounded deliverable... Every claim in the deliverable traces to the exact place in the sources it came from."**

### 4.1 How Deliverables Are Stored in Database

Deliverables are persisted in the `deliverable_sections` table. A deliverable section is created in two ways:
1. **Automated Agreements**: Directly committed when the LLM Judge identifies unanimous alignment across documents.
2. **Resolved Conflicts**: Inserted or updated when a human analyst makes a decision in Stage 03 (`APPROVE_DOC`, `CUSTOM_RESOLUTION`, or `REJECT`).

```sql
-- Schema of deliverable_sections
CREATE TABLE deliverable_sections (
    id SERIAL PRIMARY KEY,
    run_thread_id VARCHAR(100) NOT NULL,
    category VARCHAR(255) NOT NULL,
    title VARCHAR(255) NOT NULL,
    committed_markdown TEXT NOT NULL,
    citations_json JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);
```

#### Example Row in `deliverable_sections`:
```json
{
  "id": 14,
  "run_thread_id": "thread_83920194",
  "category": "Hourly Billing Rates & Role Pricing",
  "title": "Hourly Billing Rates & Role Pricing",
  "committed_markdown": "**Adopted Term from Amendment_1.pdf:**\n\n\"The billing ceiling for Principal Cloud Architect is hereby updated to $220/hr, superseding Exhibit A of the Original Agreement.\"",
  "citations_json": [
    {
      "doc_id": 28,
      "page_number": 1,
      "exact_quote": "The billing ceiling for Principal Cloud Architect is hereby updated to $220/hr"
    }
  ],
  "created_at": "2026-11-01T09:15:32"
}
```

---

### 4.2 How the Deliverable Looks in the UI

In Tab 04 (`Grounded Deliverable`), the frontend loops through `workspace.deliverables` and renders individual cards:

```
+---------------------------------------------------------------------------------------+
|  COMMITTED CLAUSE                                                         Nov 1, 2026  |
|  Hourly Billing Rates & Role Pricing                                                  |
|                                                                                       |
|  **Adopted Term from Amendment_1.pdf:**                                               |
|  "The billing ceiling for Principal Cloud Architect is hereby updated to $220/hr..."  |
|                                                                                       |
|  Grounding Citations:                                                                 |
|  [Doc 28 | Page 1]  "The billing ceiling for Principal Cloud Architect is hereby..."   |
+---------------------------------------------------------------------------------------+
```

---

### 4.3 How the Deliverable is Exported / Downloaded

Exporting doesn't require a server roundtrip; it is compiled dynamically in the browser from the verified deliverable sections via Vue's `computed` property in [`AppView.vue`](file:///Users/obaidaccount/Project/SuperDocs-Engineering/frontend/src/views/AppView.vue#L151-L192):

```mermaid
flowchart LR
    A["workspace.deliverables\n(Array of DeliverableSection)"] --> B["computed: compiledReportMarkdown\nGenerates Full GitHub-Flavored Markdown"]
    B --> C["Button: 'Copy Report MD'\nnavigator.clipboard.writeText(...)"]
    B --> D["Button: 'Download Report (.md)'\nBlob -> objectURL -> <a> click -> auto download"]
```

#### Client-side Export Code (`AppView.vue`):
```javascript
// 1. Markdown Compilation
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

// 2. Browser File Download Trigger
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
```

---

### 4.4 Example Downloaded Report (`.md` File)

When the user clicks **"Download Report (.md)"**, a standalone markdown file (`Reconciliation_Report_thread_xxx.md`) is downloaded:

````markdown
# SuperDocs Reconciled Deliverable Report
**Run Thread ID:** `thread_83920194`
**Project:** Q3 Vendor MSA & Invoices Audit
**Generated:** 11/1/2026, 2:45:00 PM
---

## Reconciled Contractual Terms

### Hourly Billing Rates & Role Pricing
**Adopted Term from Amendment_1.pdf:**

"The billing ceiling for Principal Cloud Architect is hereby updated to $220/hr, superseding Exhibit A of the Original Agreement."

> **Verified Grounded Citations:**
> * `[Doc 28 | Page 1]`: "The billing ceiling for Principal Cloud Architect is hereby updated to $220/hr"

### Invoicing & Payment Window
Invoices shall be payable within Net 30 days of receipt. Late fees of 1.0% per month apply to undisputed overdue balances.

> **Verified Grounded Citations:**
> * `[Doc 28 | Page 1]`: "Payment terms are hereby revised to Net 30 days"
> * `[Doc 27 | Page 3]`: "Late fees of 1.0% per month apply to undisputed overdue balances"
````

---

## 5. Key Files and Code References

| Path | Purpose |
| :--- | :--- |
| [`bakcend/src/models/db_models.py`](file:///Users/obaidaccount/Project/SuperDocs-Engineering/bakcend/src/models/db_models.py) | SQLAlchemy Declarative models (`Organization`, `Project`, `Document`, `DocumentChunk`, `ReviewItem`, `DeliverableSection`). |
| [`bakcend/src/ingestion/pipeline.py`](file:///Users/obaidaccount/Project/SuperDocs-Engineering/bakcend/src/ingestion/pipeline.py) | Background ingestion dispatcher coordinating partitioning, AI vision summarization, batch embeddings, and chunk persistence. |
| [`bakcend/src/ingestion/partitioner.py`](file:///Users/obaidaccount/Project/SuperDocs-Engineering/bakcend/src/ingestion/partitioner.py) | Unstructured Transform Serverless API integration and title-based chunking (`chunk_by_title`). |
| [`bakcend/src/ingestion/summarizer.py`](file:///Users/obaidaccount/Project/SuperDocs-Engineering/bakcend/src/ingestion/summarizer.py) | Mixed-content handler; sends tables and images to `gpt-4o-mini` to generate searchable text summaries. |
| [`bakcend/src/reconciliation/graph.py`](file:///Users/obaidaccount/Project/SuperDocs-Engineering/bakcend/src/reconciliation/graph.py) | LangGraph `StateGraph` defining the 4-node execution workflow (`ingest_documents` $\to$ `build_clusters` $\to$ `llm_judge` $\to$ `persist_results`). |
| [`bakcend/src/reconciliation/clusterer.py`](file:///Users/obaidaccount/Project/SuperDocs-Engineering/bakcend/src/reconciliation/clusterer.py) | Topic Anchor discovery, semantic outline extraction, and `pgvector` chunk matching with context window expansion. |
| [`bakcend/src/reconciliation/judge.py`](file:///Users/obaidaccount/Project/SuperDocs-Engineering/bakcend/src/reconciliation/judge.py) | Structured LLM Judge evaluating topic clusters for `CONFLICT` vs `AGREEMENT`, extracting verbatim quotes and page references. |
| [`bakcend/src/controller/reconciliation_controller.py`](file:///Users/obaidaccount/Project/SuperDocs-Engineering/bakcend/src/controller/reconciliation_controller.py) | Endpoints controller for running reconciliation, fetching review items, and committing human resolution decisions into deliverables. |
| [`bakcend/src/websocket/manager.py`](file:///Users/obaidaccount/Project/SuperDocs-Engineering/bakcend/src/websocket/manager.py) | Live event broadcasting mechanism powering the real-time pipeline status ribbon on the client. |

---

## 5. Developer Cheat Sheet: Common Actions & State Invariants

- **Idempotency**: Reconciliation runs use unique `thread_id`s. Running reconciliation on the same `thread_id` deletes previous `review_items` and `deliverable_sections` before regenerating results to avoid duplicate rows.
- **Deduplication**: Files are SHA-256 hashed prior to upload. If a duplicate file hash is uploaded to a project, it reuses the existing `documents` record without reprocessing.
- **Grounding Requirement**: All deliverable sections store citations in JSON format (`[{"doc_id": int, "page_number": int, "exact_quote": str}]`). Grounding guarantees that every committed statement references a verified quote and page number in the source corpus.

