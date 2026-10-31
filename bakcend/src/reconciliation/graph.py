import uuid
import asyncio
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END
from sqlalchemy import select, delete

from ..database import AsyncSessionLocal
from ..models.db_models import Document, DocumentChunk, ReviewItem, DeliverableSection
from ..websocket.manager import ws_manager
from ..ingestion.pipeline import run_document_ingestion
from .clusterer import build_topic_clusters
from .judge import evaluate_single_dabba
from .schemas import TopicCluster, JudgeVerdict

class ReconciliationState(TypedDict):
    thread_id: Optional[str]
    doc_ids: List[int]
    doc_paths: Optional[List[Dict[str, Any]]]
    similarity_threshold: float
    max_pairs: int
    clusters: List[Dict[str, Any]]
    verdicts: List[Dict[str, Any]]
    review_items: Optional[List[Dict[str, Any]]]
    error: Optional[str]

# ============================================================================
# LANGGRAPH NODE 1: Ingest Documents (Chunking & Embedding with Live WS Updates)
# ============================================================================

async def ingest_documents_node(state: ReconciliationState) -> Dict[str, Any]:
    thread_id = state.get("thread_id")
    doc_paths = state.get("doc_paths") or []
    doc_ids = list(state.get("doc_ids") or [])

    if not doc_paths and doc_ids:
        # Documents were already ingested or doc_ids were passed directly
        return {"doc_ids": doc_ids}

    if not doc_paths:
        return {"doc_ids": doc_ids}

    if thread_id:
        await ws_manager.broadcast(thread_id, "STAGE_CHANGED", {
            "stage": "INGESTION",
            "message": f"Ingesting and chunking {len(doc_paths)} documents..."
        })

    async def ingest_with_broadcast(item: Dict[str, Any]):
        d_id = item["doc_id"]
        f_path = item["file_path"]
        f_name = item.get("filename", f"Doc #{d_id}")

        async with AsyncSessionLocal() as session:
            doc = await session.get(Document, d_id)
            if doc and doc.status == "PARSED":
                chunks_res = await session.execute(
                    select(DocumentChunk).where(DocumentChunk.document_id == d_id)
                )
                chunk_count = len(chunks_res.scalars().all())
                if thread_id:
                    await ws_manager.broadcast(thread_id, "DOC_INGESTION_PROGRESS", {
                        "doc_id": d_id,
                        "filename": f_name,
                        "status": "PARSED",
                        "chunks_count": chunk_count
                    })
                return

        if thread_id:
            await ws_manager.broadcast(thread_id, "DOC_INGESTION_START", {
                "doc_id": d_id,
                "filename": f_name,
                "status": "PROCESSING"
            })

        # Run document ingestion (PDF extraction -> chunking -> vector embeddings)
        await run_document_ingestion(doc_id=d_id, file_path=f_path)

        async with AsyncSessionLocal() as session:
            chunks_res = await session.execute(
                select(DocumentChunk).where(DocumentChunk.document_id == d_id)
            )
            chunk_count = len(chunks_res.scalars().all())

        if thread_id:
            await ws_manager.broadcast(thread_id, "DOC_INGESTION_PROGRESS", {
                "doc_id": d_id,
                "filename": f_name,
                "status": "PARSED",
                "chunks_count": chunk_count
            })

    # Run ingestions concurrently
    await asyncio.gather(*[ingest_with_broadcast(item) for item in doc_paths], return_exceptions=True)

    final_doc_ids = [d["doc_id"] for d in doc_paths]

    if thread_id:
        await ws_manager.broadcast(thread_id, "INGESTION_COMPLETE", {
            "message": "All documents successfully ingested and embedded.",
            "doc_ids": final_doc_ids
        })

    return {"doc_ids": final_doc_ids}

# ============================================================================
# LANGGRAPH NODE 2: Build Topic Clusters (Anchors + pgvector + Window Expansion)
# ============================================================================

async def build_topic_clusters_node(state: ReconciliationState) -> Dict[str, Any]:
    thread_id = state.get("thread_id")
    doc_ids = state.get("doc_ids", [])
    threshold = state.get("similarity_threshold", 0.45)
    max_pairs = state.get("max_pairs", 500)

    if not doc_ids or len(doc_ids) < 2:
        error_msg = f"At least 2 documents are required for reconciliation. Found {len(doc_ids)}."
        if thread_id:
            await ws_manager.broadcast(thread_id, "PIPELINE_ERROR", {"message": error_msg})
        return {"clusters": [], "error": error_msg}

    if thread_id:
        await ws_manager.broadcast(thread_id, "STAGE_CHANGED", {
            "stage": "CLUSTERING",
            "message": "Extracting section outlines & discovering topic anchors across documents..."
        })

    async with AsyncSessionLocal() as session:
        try:
            clusters = await build_topic_clusters(
                db=session,
                doc_ids=doc_ids,
                similarity_threshold=threshold,
                max_pairs=max_pairs
            )

            if not clusters:
                error_msg = "No overlapping topic clusters could be formed between these documents."
                if thread_id:
                    await ws_manager.broadcast(thread_id, "PIPELINE_ERROR", {"message": error_msg})
                return {"clusters": [], "error": error_msg}

            # Broadcast discovered topics & formed clusters live over WebSocket
            if thread_id:
                topic_names = [c.topic_hint for c in clusters if c.topic_hint]
                await ws_manager.broadcast(thread_id, "TOPICS_DISCOVERED", {
                    "topics": topic_names,
                    "count": len(topic_names)
                })
                await ws_manager.broadcast(thread_id, "CLUSTERS_READY", {
                    "total_clusters": len(clusters),
                    "clusters": [c.model_dump() for c in clusters]
                })

            return {
                "clusters": [c.model_dump() for c in clusters],
                "error": None
            }
        except Exception as e:
            error_msg = f"Clustering error: {str(e)}"
            if thread_id:
                await ws_manager.broadcast(thread_id, "PIPELINE_ERROR", {"message": error_msg})
            return {
                "clusters": [],
                "error": error_msg
            }

# Node 3
async def llm_judge_node(state: ReconciliationState) -> Dict[str, Any]:
    thread_id = state.get("thread_id")
    if state.get("error"):
        return {"verdicts": []}

    raw_clusters = state.get("clusters", [])
    if not raw_clusters:
        return {"verdicts": []}

    clusters = [TopicCluster(**c) for c in raw_clusters]

    if thread_id:
        await ws_manager.broadcast(thread_id, "STAGE_CHANGED", {
            "stage": "LLM_JUDGE",
            "message": f"Evaluating {len(clusters)} topic clusters with LLM Judge..."
        })

    semaphore = asyncio.Semaphore(5)
    verdicts: List[JudgeVerdict] = []

    async def evaluate_and_stream(c: TopicCluster):
        verdict = await evaluate_single_dabba(c, semaphore)
        if verdict:
            verdicts.append(verdict)
            if thread_id:
                await ws_manager.broadcast(thread_id, "VERDICT_STREAM", {
                    "dabba_id": c.dabba_id,
                    "verdict": verdict.model_dump()
                })
        return verdict

    try:
        await asyncio.gather(*[evaluate_and_stream(c) for c in clusters], return_exceptions=True)
        return {
            "verdicts": [v.model_dump() for v in verdicts]
        }
    except Exception as e:
        error_msg = f"Judge error: {str(e)}"
        if thread_id:
            await ws_manager.broadcast(thread_id, "PIPELINE_ERROR", {"message": error_msg})
        return {
            "verdicts": [],
            "error": error_msg
        }

# Node 4
async def persist_results_node(state: ReconciliationState) -> Dict[str, Any]:
    thread_id = state.get("thread_id") or str(uuid.uuid4())
    if state.get("error"):
        return {"thread_id": thread_id, "review_items": []}

    verdicts = state.get("verdicts", [])
    if not verdicts:
        return {"thread_id": thread_id, "review_items": []}

    created_review_items = []
    async with AsyncSessionLocal() as session:
        try:
            # Delete any existing review items or deliverable sections for this thread (idempotency)
            await session.execute(delete(ReviewItem).where(ReviewItem.run_thread_id == thread_id))
            await session.execute(delete(DeliverableSection).where(DeliverableSection.run_thread_id == thread_id))

            for v in verdicts:
                status = v.get("status")
                topic_name = v.get("topic_name", "Untitled Topic")
                explanation = v.get("explanation", "")
                evidence = v.get("evidence", [])
                severity = v.get("severity", "NONE")

                if status == "CONFLICT":
                    item = ReviewItem(
                        run_thread_id=thread_id,
                        item_type="CONFLICT",
                        category=topic_name,
                        severity=severity,
                        summary=explanation,
                        citations_json=evidence,
                        status="PENDING"
                    )
                    session.add(item)
                    await session.flush()
                    created_review_items.append({
                        "id": item.id,
                        "category": item.category,
                        "severity": item.severity,
                        "summary": item.summary,
                        "citations": item.citations_json,
                        "status": item.status
                    })
                else:
                    section = DeliverableSection(
                        run_thread_id=thread_id,
                        category=topic_name,
                        title=topic_name,
                        committed_markdown=explanation,
                        citations_json=evidence
                    )
                    session.add(section)

            await session.commit()

            conflicts_count = len(created_review_items)
            agreements_count = len(verdicts) - conflicts_count

            if thread_id:
                # Broadcast that Human-in-the-Loop Review Gate is ready!
                await ws_manager.broadcast(thread_id, "STAGE_CHANGED", {
                    "stage": "REVIEW_GATE",
                    "message": f"Reconciliation graph finished. {conflicts_count} conflicts awaiting review."
                })
                await ws_manager.broadcast(thread_id, "REVIEW_GATE_READY", {
                    "thread_id": thread_id,
                    "conflicts_count": conflicts_count,
                    "agreements_count": agreements_count,
                    "review_items": created_review_items,
                    "verdicts": verdicts
                })

            return {
                "thread_id": thread_id,
                "review_items": created_review_items
            }
        except Exception as e:
            await session.rollback()
            error_msg = f"Persistence error: {str(e)}"
            if thread_id:
                await ws_manager.broadcast(thread_id, "PIPELINE_ERROR", {"message": error_msg})
            return {"error": error_msg}


workflow = StateGraph(ReconciliationState)
workflow.add_node("ingest_documents", ingest_documents_node)
workflow.add_node("build_clusters", build_topic_clusters_node)
workflow.add_node("llm_judge", llm_judge_node)
workflow.add_node("persist_results", persist_results_node)

workflow.add_edge(START, "ingest_documents")
workflow.add_edge("ingest_documents", "build_clusters")
workflow.add_edge("build_clusters", "llm_judge")
workflow.add_edge("llm_judge", "persist_results")
workflow.add_edge("persist_results", END)

reconciliation_graph = workflow.compile()
