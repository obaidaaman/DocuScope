import uuid
import hashlib
from typing import Dict, Any, List
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db_models import ComplianceAudit, DeliverableSection, Document, ReviewItem
from ..reconciliation.schemas import (
    ComplianceCheckRequest,
    ReconciliationRequest,
    ReconciliationResponse,
    JudgeVerdict,
    ResolveReviewItemsRequest
)
from ..reconciliation.compliance import check_and_broadcast_compliance
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
        "doc_paths": None,
        "similarity_threshold": request.similarity_threshold,
        "max_pairs": request.max_pairs,
        "clusters": [],
        "verdicts": [],
        "review_items": [],
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


async def get_compliance_audit_controller(
    thread_id: str,
    db: AsyncSession
) -> Dict[str, Any]:
    audit = await db.scalar(
        select(ComplianceAudit).where(ComplianceAudit.run_thread_id == thread_id)
    )
    if not audit:
        return {
            "thread_id": thread_id,
            "source": "Demo grounding-compliance checklist",
            "source_of_truth": "Ingested source documents and cited page text",
            "status": "NOT_RUN",
            "finalized": False,
            "source_truth_doc_id": None,
            "checks": [],
        }

    return {
        **audit.result_json,
        "checked_at": audit.checked_at,
        "finalized": audit.finalized,
        "source_truth_doc_id": audit.source_truth_doc_id,
    }


async def start_compliance_check_controller(
    thread_id: str,
    request: ComplianceCheckRequest,
    db: AsyncSession,
) -> Dict[str, Any]:
    source_document = await db.get(Document, request.source_truth_doc_id)
    if (
        not source_document
        or source_document.status != "PARSED"
        or source_document.project_id != request.project_id
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Select a parsed document from the active project as the source of truth."
        )

    section_count = await db.scalar(
        select(func.count(DeliverableSection.id)).where(
            DeliverableSection.run_thread_id == thread_id
        )
    )
    if not section_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Create a deliverable before starting the source-of-truth comparison."
        )

    pending_conflicts = await db.scalar(
        select(func.count(ReviewItem.id)).where(
            ReviewItem.run_thread_id == thread_id,
            ReviewItem.item_type == "CONFLICT",
            ReviewItem.status == "PENDING",
        )
    )
    if pending_conflicts:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resolve the reconciliation conflicts before selecting the source of truth."
        )

    return await check_and_broadcast_compliance(
        thread_id,
        request.source_truth_doc_id,
    )


async def resolve_review_items_controller(
    request: ResolveReviewItemsRequest,
    db: AsyncSession
) -> Dict[str, Any]:
    resolved_count = 0
    resolved_compliance_item = False
    for res_action in request.resolutions:
        item = await db.get(ReviewItem, res_action.review_item_id)
        if not item or item.run_thread_id != request.thread_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Review item {res_action.review_item_id} was not found for this run."
            )

        item.status = "RESOLVED"
        if item.item_type == "COMPLIANCE":
            resolved_compliance_item = True
            section_result = await db.execute(
                select(DeliverableSection).where(
                    DeliverableSection.run_thread_id == request.thread_id,
                    DeliverableSection.category == item.category,
                )
            )
            section = section_result.scalar_one_or_none()
            if not section:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Deliverable section {item.category} was not found."
                )

            if res_action.action == "APPROVE_AS_IS":
                content_hash = hashlib.sha256(
                    section.committed_markdown.encode("utf-8")
                ).hexdigest()
                item.resolution_notes = (
                    f"Action: APPROVE_AS_IS | SHA256:{content_hash}"
                )
            elif res_action.action == "CUSTOM_RESOLUTION" and res_action.custom_text:
                section.title = item.category
                section.committed_markdown = (
                    "**Analyst Approved Compliance Resolution:**\n\n"
                    f"{res_action.custom_text}"
                )
                section.citations_json = []
                content_hash = hashlib.sha256(
                    section.committed_markdown.encode("utf-8")
                ).hexdigest()
                item.resolution_notes = (
                    f"Action: CUSTOM_RESOLUTION | SHA256:{content_hash}"
                )
            elif res_action.action == "REJECT":
                section.title = f"{item.category} (Rejected)"
                section.committed_markdown = (
                    "**Clause Rejected / Omitted:**\n\n"
                    "An analyst rejected this section during compliance review and omitted "
                    "it from the final deliverable."
                )
                section.citations_json = []
                content_hash = hashlib.sha256(
                    section.committed_markdown.encode("utf-8")
                ).hexdigest()
                item.resolution_notes = f"Action: REJECT | SHA256:{content_hash}"
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Choose approve as-is, provide a custom resolution, or reject the section."
                )

            resolved_count += 1
            continue

        if res_action.action == "APPROVE_AS_IS":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Approve-as-is is only available for compliance review items."
            )

        section_title = item.category
        matching_citations = []
        committed_text = ""

        # 1. APPROVE_DOC: Dynamically extract adopted document's verbatim clause & filter citations
        if res_action.action == "APPROVE_DOC" and res_action.chosen_doc_id:
            chosen_doc = await db.get(Document, res_action.chosen_doc_id)
            doc_name = chosen_doc.filename if chosen_doc else f"Doc #{res_action.chosen_doc_id}"

            # Keep only the citations from the winning approved document
            matching_citations = [
                c for c in (item.citations_json or [])
                if c.get("doc_id") == res_action.chosen_doc_id
            ]

            if matching_citations:
                quotes_text = "\n\n".join([f'"{c.get("exact_quote")}"' for c in matching_citations if c.get("exact_quote")])
                committed_text = f"**Adopted Term from {doc_name}:**\n\n{quotes_text}"
            else:
                committed_text = f"**Adopted Term from {doc_name}**"

            item.resolution_notes = f"Action: APPROVE_DOC | Adopted: {doc_name}"

        # 2. CUSTOM_RESOLUTION: Analyst provided explicit negotiated clause
        elif res_action.action == "CUSTOM_RESOLUTION" and res_action.custom_text:
            committed_text = f"**Analyst Negotiated Resolution:**\n\n{res_action.custom_text}"
            matching_citations = []
            item.resolution_notes = f"Action: CUSTOM_RESOLUTION | {res_action.custom_text}"

        # 3. REJECT: Explicit rejection note with audit trail (no silent deletion)
        elif res_action.action == "REJECT":
            section_title = f"{item.category} (Rejected)"
            committed_text = (
                f"**Clause Rejected / Omitted:**\n\n"
                f"The contradictory terms for *{item.category}* across documents were explicitly "
                f"rejected during legal review and are excluded from the reconciled agreement."
            )
            matching_citations = []
            item.resolution_notes = "Action: REJECT"

        else:
            committed_text = item.summary
            matching_citations = item.citations_json or []

        # Idempotent: Update existing DeliverableSection or insert a new one
        stmt = select(DeliverableSection).where(
            DeliverableSection.run_thread_id == request.thread_id,
            DeliverableSection.category == item.category
        )
        res = await db.execute(stmt)
        existing_section = res.scalar_one_or_none()

        if existing_section:
            existing_section.title = section_title
            existing_section.committed_markdown = committed_text
            existing_section.citations_json = matching_citations
        else:
            new_section = DeliverableSection(
                run_thread_id=request.thread_id,
                category=item.category,
                title=section_title,
                committed_markdown=committed_text,
                citations_json=matching_citations
            )
            db.add(new_section)

        resolved_count += 1

    await db.commit()
    audit = await db.scalar(
        select(ComplianceAudit).where(
            ComplianceAudit.run_thread_id == request.thread_id
        )
    )
    compliance_audit = None
    if resolved_compliance_item and audit and audit.source_truth_doc_id:
        review_result = await db.execute(
            select(ReviewItem).where(
                ReviewItem.run_thread_id == request.thread_id,
                ReviewItem.item_type.in_(["CONFLICT", "COMPLIANCE"]),
            )
        )
        review_items = review_result.scalars().all()
        pending_conflicts = sum(
            item.status == "PENDING" and item.item_type == "CONFLICT"
            for item in review_items
        )
        pending_compliance = sum(
            item.status == "PENDING" and item.item_type == "COMPLIANCE"
            for item in review_items
        )
        audit.status = (
            "PENDING_REVIEW" if pending_conflicts
            else "PENDING_COMPLIANCE_REVIEW" if pending_compliance
            else "HUMAN_APPROVED"
        )
        audit.finalized = False
        audit.result_json = {
            **audit.result_json,
            "status": audit.status,
            "finalized": False,
            "pending_conflicts": pending_conflicts,
            "pending_compliance_reviews": pending_compliance,
            "compliance_review_items": [
                {
                    "id": item.id,
                    "category": item.category,
                    "summary": item.summary,
                    "status": item.status,
                    "resolution_notes": item.resolution_notes,
                }
                for item in review_items
                if item.item_type == "COMPLIANCE"
            ],
        }
        await db.commit()
        compliance_audit = audit.result_json
    return {
        "thread_id": request.thread_id,
        "resolved_items_count": resolved_count,
        "status": "COMPLETED",
        "compliance_audit": compliance_audit,
    }


async def finalize_deliverable_controller(
    thread_id: str,
    db: AsyncSession,
) -> Dict[str, Any]:
    audit = await db.scalar(
        select(ComplianceAudit).where(ComplianceAudit.run_thread_id == thread_id)
    )
    if not audit:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Run the compliance check before finalizing the deliverable."
        )
    if not audit.source_truth_doc_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Select a source-of-truth document before finalizing."
        )

    pending_count = await db.scalar(
        select(func.count(ReviewItem.id)).where(
            ReviewItem.run_thread_id == thread_id,
            ReviewItem.item_type.in_(["CONFLICT", "COMPLIANCE"]),
            ReviewItem.status == "PENDING",
        )
    )
    if pending_count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Resolve all {pending_count} pending review item(s) before finalizing."
        )

    if audit.status not in ("COMPLIANT", "HUMAN_APPROVED"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Deliverable cannot be finalized while compliance status is {audit.status}."
        )

    audit.finalized = True
    audit.result_json = {**audit.result_json, "finalized": True}
    await db.commit()
    return {
        "thread_id": thread_id,
        "status": audit.status,
        "finalized": True,
    }
