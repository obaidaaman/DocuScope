import uuid
from typing import Dict, Any, Set, Tuple
from sqlalchemy import delete, select

from ...database import AsyncSessionLocal
from ...models.db_models import ComplianceAudit, ReviewItem, DeliverableSection, DocumentChunk
from ...websocket.manager import ws_manager
from ..schemas import ReconciliationState


# node 5 - save conflicts to review_items, agreements and baseline clauses to deliverable_sections
async def persist_results_node(state: ReconciliationState) -> Dict[str, Any]:
    thread_id = state.get("thread_id") or str(uuid.uuid4())
    if state.get("error"):
        return {"thread_id": thread_id, "review_items": []}

    verdicts = state.get("verdicts", [])
    doc_ids = state.get("doc_ids", [])

    created_review_items = []
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(delete(ReviewItem).where(ReviewItem.run_thread_id == thread_id))
            await session.execute(delete(DeliverableSection).where(DeliverableSection.run_thread_id == thread_id))
            await session.execute(delete(ComplianceAudit).where(ComplianceAudit.run_thread_id == thread_id))

            clustered_keys: Set[Tuple[int, int]] = set()
            clusters = state.get("clusters", [])
            for cl in clusters:
                for p in cl.get("passages", []):
                    clustered_keys.add((p.get("doc_id"), p.get("chunk_index")))

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
                    quote_lines = [
                        e.get("exact_quote").strip()
                        for e in evidence
                        if isinstance(e, dict) and e.get("exact_quote")
                    ]
                    if quote_lines:
                        formatted_quotes = "\n\n".join(f'"{q}"' for q in quote_lines)
                        body = f"**Agreed Term:**\n\n{formatted_quotes}\n\n*{explanation}*"
                    else:
                        body = explanation

                    section = DeliverableSection(
                        run_thread_id=thread_id,
                        category=topic_name,
                        title=topic_name,
                        committed_markdown=body,
                        citations_json=evidence
                    )
                    session.add(section)

            # include base document uncontested clauses so deliverable is a full report
            if doc_ids:
                base_doc_id = doc_ids[0]
                chunk_stmt = (
                    select(DocumentChunk)
                    .where(DocumentChunk.document_id == base_doc_id)
                    .order_by(DocumentChunk.chunk_index)
                )
                chunk_res = await session.execute(chunk_stmt)
                base_chunks = chunk_res.scalars().all()

                for c in base_chunks:
                    if (base_doc_id, c.chunk_index) in clustered_keys:
                        continue
                    text_content = (c.raw_text or "").strip()
                    if not text_content or len(text_content) < 30:
                        continue

                    first_line = text_content.splitlines()[0][:80].strip()
                    sec_title = first_line if first_line else f"Section {c.chunk_index + 1}"

                    base_citation = [{
                        "doc_id": base_doc_id,
                        "page_number": c.page_number,
                        "exact_quote": text_content[:150]
                    }]

                    section = DeliverableSection(
                        run_thread_id=thread_id,
                        category=sec_title,
                        title=sec_title,
                        committed_markdown=text_content,
                        citations_json=base_citation
                    )
                    session.add(section)

            await session.commit()

            conflicts_count = len(created_review_items)
            agreements_count = len(verdicts) - conflicts_count

            if thread_id:
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

