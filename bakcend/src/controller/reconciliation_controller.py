import uuid
from typing import Dict, Any, List
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db_models import Document, ReviewItem, DeliverableSection
from ..reconciliation.schemas import (
    ReconciliationRequest,
    ReconciliationResponse,
    JudgeVerdict,
    ResolveReviewItemsRequest
)
from ..reconciliation.clusterer import build_topic_clusters
from ..reconciliation.graph import reconciliation_graph

async def preview_clusters_controller(
    request: ReconciliationRequest,
    db: AsyncSession
) -> Dict[str, Any]:
    stmt = select(Document.id, Document.filename, Document.status).where(Document.id.in_(request.doc_ids))
    res = await db.execute(stmt)
    found_docs = res.fetchall()

    if len(found_docs) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"At least 2 valid documents must be provided. Found: {[d[0] for d in found_docs]}"
        )

    clusters = await build_topic_clusters(
        db=db,
        doc_ids=request.doc_ids,
        similarity_threshold=request.similarity_threshold,
        max_pairs=request.max_pairs
    )

    return {
        "doc_ids": request.doc_ids,
        "total_clusters": len(clusters),
        "clusters": [c.model_dump() for c in clusters]
    }

async def run_reconciliation_controller(
    request: ReconciliationRequest,
    db: AsyncSession
) -> ReconciliationResponse:
    stmt = select(Document.id, Document.filename, Document.status).where(Document.id.in_(request.doc_ids))
    res = await db.execute(stmt)
    found_docs = res.fetchall()

    if len(found_docs) < 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"At least 2 valid documents must be provided. Found: {[d[0] for d in found_docs]}"
        )

    thread_id = request.thread_id or str(uuid.uuid4())

    initial_state = {
        "thread_id": thread_id,
        "doc_ids": request.doc_ids,
        "similarity_threshold": request.similarity_threshold,
        "max_pairs": request.max_pairs,
        "clusters": [],
        "verdicts": [],
        "error": None
    }

    final_state = await reconciliation_graph.ainvoke(initial_state)

    if final_state.get("error"):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=final_state["error"]
        )

    raw_verdicts = final_state.get("verdicts", [])
    verdicts = [JudgeVerdict(**v) for v in raw_verdicts]
    clusters = final_state.get("clusters", [])

    conflicts = sum(1 for v in verdicts if v.status == "CONFLICT")
    agreements = sum(1 for v in verdicts if v.status == "AGREEMENT")
    final_thread_id = final_state.get("thread_id") or thread_id

    return ReconciliationResponse(
        thread_id=final_thread_id,
        total_dabbe=len(clusters),
        conflicts_count=conflicts,
        agreements_count=agreements,
        verdicts=verdicts,
        dabbe_preview=clusters
    )

async def get_review_items_controller(
    thread_id: str,
    db: AsyncSession
) -> List[Dict[str, Any]]:
    stmt = (
        select(ReviewItem)
        .where(ReviewItem.run_thread_id == thread_id)
        .order_by(ReviewItem.id)
    )
    res = await db.execute(stmt)
    items = res.scalars().all()
    return [
        {
            "id": item.id,
            "run_thread_id": item.run_thread_id,
            "item_type": item.item_type,
            "category": item.category,
            "severity": item.severity,
            "summary": item.summary,
            "citations": item.citations_json,
            "status": item.status,
            "resolution_notes": item.resolution_notes,
            "created_at": item.created_at
        }
        for item in items
    ]

async def get_deliverable_sections_controller(
    thread_id: str,
    db: AsyncSession
) -> List[Dict[str, Any]]:
    stmt = (
        select(DeliverableSection)
        .where(DeliverableSection.run_thread_id == thread_id)
        .order_by(DeliverableSection.id)
    )
    res = await db.execute(stmt)
    sections = res.scalars().all()
    return [
        {
            "id": s.id,
            "run_thread_id": s.run_thread_id,
            "category": s.category,
            "title": s.title,
            "committed_markdown": s.committed_markdown,
            "citations": s.citations_json,
            "created_at": s.created_at
        }
        for s in sections
    ]

async def resolve_review_items_controller(
    request: ResolveReviewItemsRequest,
    db: AsyncSession
) -> Dict[str, Any]:
    resolved_count = 0
    for res_action in request.resolutions:
        item = await db.get(ReviewItem, res_action.review_item_id)
        if not item:
            continue

        item.status = "RESOLVED"
        resolution_note = f"Action: {res_action.action}"
        if res_action.chosen_doc_id:
            resolution_note += f" | Adopted Doc ID: {res_action.chosen_doc_id}"
        if res_action.custom_text:
            resolution_note += f" | Custom Resolution: {res_action.custom_text}"
        item.resolution_notes = resolution_note

        if res_action.action in ["APPROVE_DOC", "CUSTOM_RESOLUTION"]:
            committed_text = res_action.custom_text or item.summary
            new_section = DeliverableSection(
                run_thread_id=request.thread_id,
                category=item.category,
                title=item.category,
                committed_markdown=committed_text,
                citations_json=item.citations_json
            )
            db.add(new_section)

        resolved_count += 1

    await db.commit()
    return {
        "thread_id": request.thread_id,
        "resolved_items_count": resolved_count,
        "status": "COMPLETED"
    }
