# The Analyst That Never Sleeps

An agentic document-analysis system that understands a growing collection of related documents, produces a grounded report, checks it against user-defined rules, and continuously updates it when new documents arrive.

The system is designed around one core idea:

> **Documents are the source of truth. The agent reasons over them, but never invents unsupported information.**

## What it does

Organizations often have multiple documents describing the same project, contract, case, or process. These documents can contain overlapping information, contradictions, and new updates over time.

This system provides an agent that manages that document collection end to end.

### 1. Understand

The system accepts related documents in supported formats and:

* extracts relevant facts,
* identifies relationships between documents,
* detects conflicting information,
* generates a grounded report, brief, or register,
* links claims back to their exact source locations.

### 2. Reconcile and review

The existing reconciliation pipeline generates a draft deliverable and routes conflicts through its human review gate. Once conflicts are resolved, the user selects a document from the active project as the source of truth. If it is still processing, the user waits for parsing to finish; failed parsing is retried. The user then explicitly starts the comparison.

The source-of-truth comparison checks the deliverable against the selected document and applies a demo grounding checklist:

* every source-derived section must include a citation,
* each citation must match text on the cited document page,
* each material deliverable claim is checked against the selected source of truth.

Findings enter the same human review gate as conflicts: analysts can approve a section as-is, rewrite it, or reject it. The audit reruns after compliance decisions. The ultimate final report can only be finalized and exported after every conflict and compliance item has been resolved. This demo checklist verifies source grounding; it is not a legal or regulatory compliance assessment.

A clean document set can legitimately produce **no findings**.

### 3. Stay up to date

When a new document arrives, the system determines what existing information it affects.

Instead of rebuilding the entire deliverable, it:

* identifies affected claims or sections,
* updates only those parts,
* preserves unaffected content,
* detects new contradictions,
* records what changed and which document caused the change.

All changes require human approval before they are committed.

## Agentic behavior

The system is not a single LLM call wrapped in a UI.

The agent works through visible stages and can change its path based on what it finds.

For example:

```text
Document
   ↓
Understand
   ↓
Extract facts
   ↓
Evidence check
   ├── sufficient → continue
   ├── insufficient → retry
   └── conflict → escalate
   ↓
Generate / update
   ↓
Human review
   ↓
Approve / Reject
   ↓
Commit
```

The workflow is durable, resumable, and designed to prevent unsupported claims.

## Key capabilities

* Grounded document analysis
* Source-level citations
* Conflict detection
* Rule/checklist evaluation
* Incremental document updates
* Human approval at item level
* Final deliverable comparison against cited source documents
* Resumable workflows
* Machine-driven execution through MCP
* Concurrent run isolation
* Prompt-injection protection for source documents
* Run timing and cost tracking

## Architecture

```text
                    React Review UI
                          │
                          ▼
                    FastAPI Backend
                          │
                          ▼
                  Agent Orchestrator
                  (LangGraph/LangChain)
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
        Document       Retrieval     Policy /
        Processing      + Evidence   Validation
             │            │            │
             └────────────┼────────────┘
                          ▼
                 PostgreSQL + Vector Search
                          │
                          ▼
                     MCP Server
                 (machine interface)
```

The LLM is responsible for reasoning and decisions where needed. Deterministic application code handles validation, persistence, state transitions, approvals, and commits.

## Technology Stack

| Component           | Technology                         |
| ------------------- | ---------------------------------- |
| Backend             | Python, FastAPI                    |
| Agent orchestration | LangGraph / LangChain              |
| Database            | PostgreSQL                         |
| Vector search       | PostgreSQL vector search           |
| Review interface    | React                              |
| Machine interface   | MCP                                |
| Document processing | Python-based parsers               |
| Testing             | Automated unit + integration tests |

The system is intentionally designed at **startup scale**, targeting approximately **600–1,000 users and 100 requests/sec**, rather than enterprise-scale distributed infrastructure.

## Reliability

The system is designed around several important guarantees:

### Resumability

A workflow can be interrupted and restarted without losing completed work.

### Human gate

Conflicts, findings, and proposed updates are reviewed before they become committed changes.

### Grounded output

Every important claim must have supporting evidence. When evidence is insufficient, the system reports that instead of guessing.

### Incremental updates

New documents should update only the parts affected by the new information, while unaffected content remains unchanged.

### Concurrency

Independent runs must remain isolated and must not corrupt shared state.

## Example use case

A contract-management corpus might contain:

```text
master_contract.pdf
amendment_01.pdf
amendment_02.pdf
invoice_001.pdf
invoice_002.pdf
```

The agent could produce a contract summary containing:

```text
Contract Value: ₹12,00,000
Source: amendment_02.pdf, page 4

Payment Terms: Net 30
Source: master_contract.pdf, page 7

Finding:
Invoice_002 conflicts with the latest payment terms.
Source: invoice_002.pdf, page 2
```

If another amendment arrives, the agent determines which parts of the report are affected, proposes the necessary updates, and sends those changes for review.

## Project goal

The goal is not to build a large document-management platform.

The goal is to demonstrate a **complete agentic workflow** that can:

> **Understand → Examine → Update → Review → Commit**

while remaining grounded, resumable, auditable, and practical to operate.

## Status

This project is being developed as part of the **SuperDocs Engineer Task — Task 1: The Analyst That Never Sleeps**.
