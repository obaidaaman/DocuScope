import sys
from typing import Dict, Any
from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.db_models import ComplianceAudit, DeliverableSection, Document, ReviewItem
from ..reconciliation.schemas import ComplianceCheckRequest
from ..reconciliation.compliance import check_and_broadcast_compliance


# get latest compliance audit for thread
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


# validate source doc and run compliance check
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

    rec_ctrl = sys.modules.get("src.controller.reconciliation_controller")
    runner = getattr(rec_ctrl, "check_and_broadcast_compliance", check_and_broadcast_compliance)
    return await runner(
        thread_id,
        request.source_truth_doc_id,
    )


# mark deliverable finalized once all reviews are resolved
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

