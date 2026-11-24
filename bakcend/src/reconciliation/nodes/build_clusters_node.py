from typing import Dict, Any

from ...database import AsyncSessionLocal
from ...websocket.manager import ws_manager
from ..clusterer import build_topic_clusters
from ..schemas import ReconciliationState


# node 3 - group claims into topic clusters
async def build_topic_clusters_node(state: ReconciliationState) -> Dict[str, Any]:
    thread_id = state.get("thread_id")
    if state.get("error"):
        return {"clusters": []}

    doc_ids = state.get("doc_ids", [])
    threshold = state.get("similarity_threshold", 0.45)
    max_pairs = state.get("max_pairs", 500)
    raw_extractions = state.get("doc_extractions")

    if not doc_ids or len(doc_ids) < 2:
        error_msg = f"At least 2 documents are required for reconciliation. Found {len(doc_ids)}."
        if thread_id:
            await ws_manager.broadcast(thread_id, "PIPELINE_ERROR", {"message": error_msg})
        return {"clusters": [], "error": error_msg}

    if thread_id:
        await ws_manager.broadcast(thread_id, "STAGE_CHANGED", {
            "stage": "CLUSTERING",
            "message": "Aligning extracted claims into topic clusters..."
        })

    async with AsyncSessionLocal() as session:
        try:
            clusters = await build_topic_clusters(
                db=session,
                doc_ids=doc_ids,
                similarity_threshold=threshold,
                max_pairs=max_pairs,
                doc_extractions=raw_extractions
            )

            if not clusters:
                error_msg = "No overlapping topic clusters could be formed between these documents."
                if thread_id:
                    await ws_manager.broadcast(thread_id, "PIPELINE_ERROR", {"message": error_msg})
                return {"clusters": [], "error": error_msg}

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

