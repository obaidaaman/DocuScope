import uuid
from typing import TypedDict, List, Dict, Any, Optional
from langgraph.graph import StateGraph, START, END

from ..database import AsyncSessionLocal
from ..models.db_models import ReviewItem, DeliverableSection
from .clusterer import build_topic_clusters
from .judge import run_llm_judge_pipeline
from .schemas import TopicCluster, JudgeVerdict

class ReconciliationState(TypedDict):
    thread_id: Optional[str]
    doc_ids: List[int]
    similarity_threshold: float
    max_pairs: int
    clusters: List[Dict[str, Any]]
    verdicts: List[Dict[str, Any]]
    error: Optional[str]

async def build_topic_clusters_node(state: ReconciliationState) -> Dict[str, Any]:
    doc_ids = state.get("doc_ids", [])
    threshold = state.get("similarity_threshold", 0.78)
    max_pairs = state.get("max_pairs", 500)

    async with AsyncSessionLocal() as session:
        try:
            clusters = await build_topic_clusters(
                db=session,
                doc_ids=doc_ids,
                similarity_threshold=threshold,
                max_pairs=max_pairs
            )
            return {
                "clusters": [c.model_dump() for c in clusters],
                "error": None
            }
        except Exception as e:
            return {
                "clusters": [],
                "error": f"Clustering error: {str(e)}"
            }

async def llm_judge_node(state: ReconciliationState) -> Dict[str, Any]:
    raw_clusters = state.get("clusters", [])
    if not raw_clusters:
        return {"verdicts": []}

    clusters = [TopicCluster(**c) for c in raw_clusters]
    try:
        verdicts = await run_llm_judge_pipeline(clusters=clusters, max_concurrency=5)
        return {
            "verdicts": [v.model_dump() for v in verdicts]
        }
    except Exception as e:
        return {
            "verdicts": [],
            "error": f"Judge error: {str(e)}"
        }

async def persist_results_node(state: ReconciliationState) -> Dict[str, Any]:
    verdicts = state.get("verdicts", [])
    thread_id = state.get("thread_id") or str(uuid.uuid4())

    if not verdicts:
        return {"thread_id": thread_id}

    async with AsyncSessionLocal() as session:
        try:
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
            return {"thread_id": thread_id}
        except Exception as e:
            await session.rollback()
            return {"error": f"Persistence error: {str(e)}"}

workflow = StateGraph(ReconciliationState)
workflow.add_node("build_clusters", build_topic_clusters_node)
workflow.add_node("llm_judge", llm_judge_node)
workflow.add_node("persist_results", persist_results_node)

workflow.add_edge(START, "build_clusters")
workflow.add_edge("build_clusters", "llm_judge")
workflow.add_edge("llm_judge", "persist_results")
workflow.add_edge("persist_results", END)

reconciliation_graph = workflow.compile()
