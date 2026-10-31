import asyncio
from typing import List, Dict, Any, Optional

from ..websocket.manager import ws_manager
from .graph import reconciliation_graph, ReconciliationState

async def execute_live_pipeline_workflow(
    thread_id: str,
    doc_paths: List[Dict[str, Any]],  # [{"doc_id": 1, "file_path": "...", "filename": "..."}]
    similarity_threshold: float = 0.45
):
    """
    Real-Time WebSocket Orchestration Pipeline powered by LangGraph:
    Executes compiled StateGraph:
    Node 1 (ingest_documents) -> Node 2 (build_clusters) -> Node 3 (llm_judge) -> Node 4 (persist_results)
    All real-time progress events are emitted by the respective LangGraph nodes.
    """
    doc_ids = [d["doc_id"] for d in doc_paths]
    print(f"🚀 [LangGraph Pipeline Started] Thread: {thread_id} | Docs: {doc_ids}")

    # Small delay (800ms) to allow the frontend WebSocket handshake to complete
    await asyncio.sleep(0.8)

    initial_state: ReconciliationState = {
        "thread_id": thread_id,
        "doc_ids": doc_ids,
        "doc_paths": doc_paths,
        "similarity_threshold": similarity_threshold,
        "max_pairs": 500,
        "clusters": [],
        "verdicts": [],
        "review_items": [],
        "error": None
    }

    try:
        final_state = await reconciliation_graph.ainvoke(initial_state)
        if final_state.get("error"):
            print(f"❌ [LangGraph Pipeline Finished With Error] Thread: {thread_id} | Error: {final_state['error']}")
            await ws_manager.broadcast(thread_id, "PIPELINE_ERROR", {
                "message": final_state["error"]
            })
        else:
            verdicts_count = len(final_state.get("verdicts", []))
            review_count = len(final_state.get("review_items", []))
            print(f"✅ [LangGraph Pipeline Succeeded] Thread: {thread_id} | Verdicts: {verdicts_count} | Conflicts: {review_count}")
    except Exception as e:
        print(f"❌ [LangGraph Pipeline Exception] Thread {thread_id}: {e}")
        await ws_manager.broadcast(thread_id, "PIPELINE_ERROR", {
            "message": str(e)
        })
