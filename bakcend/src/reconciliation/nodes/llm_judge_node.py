import asyncio
from typing import Dict, Any, List

from ...websocket.manager import ws_manager
from ..judge import evaluate_single_dabba
from ..schemas import TopicCluster, JudgeVerdict, ReconciliationState


# node 4 - run judge on each dabba and stream verdicts
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
    # track topic -> dabba_id and evidence -> dabba_id so we only drop cross-dabba duplicates
    seen_topics: Dict[str, int] = {}
    seen_evidence: Dict[Any, int] = {}

    async def evaluate_and_stream(c: TopicCluster):
        cluster_verdicts = await evaluate_single_dabba(c, semaphore)
        if not cluster_verdicts:
            return []
        if isinstance(cluster_verdicts, JudgeVerdict):
            cluster_verdicts = [cluster_verdicts]

        kept_verdicts = []
        for verdict in cluster_verdicts:
            topic_key = verdict.topic_name.strip().lower()

            ev_pairs = []
            for e in verdict.evidence:
                ev_pairs.append((e.doc_id, e.exact_quote.strip().lower()[:80]))
            ev_pairs.sort()
            ev_key = tuple(ev_pairs)

            # skip only if a DIFFERENT dabba already reported this exact topic or evidence
            if topic_key in seen_topics and seen_topics[topic_key] != c.dabba_id:
                continue
            if ev_key and ev_key in seen_evidence and seen_evidence[ev_key] != c.dabba_id:
                continue

            seen_topics[topic_key] = c.dabba_id
            if ev_key:
                seen_evidence[ev_key] = c.dabba_id

            verdicts.append(verdict)
            kept_verdicts.append(verdict)
            if thread_id:
                await ws_manager.broadcast(thread_id, "VERDICT_STREAM", {
                    "dabba_id": c.dabba_id,
                    "verdict": verdict.model_dump()
                })
        return kept_verdicts

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

