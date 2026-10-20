from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any, List

from ..database import get_db
from ..reconciliation.schemas import (
    ReconciliationRequest,
    ReconciliationResponse,
    ResolveReviewItemsRequest
)
from ..controller.reconciliation_controller import (
    preview_clusters_controller,
    run_reconciliation_controller,
    get_review_items_controller,
    get_deliverable_sections_controller,
    resolve_review_items_controller
)

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

@router.post("/clusters-preview")
async def preview_clusters(
    request: ReconciliationRequest,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    return await preview_clusters_controller(request=request, db=db)

@router.post("/reconcile", response_model=ReconciliationResponse)
async def run_reconciliation(
    request: ReconciliationRequest,
    db: AsyncSession = Depends(get_db)
) -> ReconciliationResponse:
    return await run_reconciliation_controller(request=request, db=db)

@router.get("/{thread_id}/review-items")
async def get_review_items(
    thread_id: str,
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    return await get_review_items_controller(thread_id=thread_id, db=db)

@router.get("/{thread_id}/deliverables")
async def get_deliverable_sections(
    thread_id: str,
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    return await get_deliverable_sections_controller(thread_id=thread_id, db=db)

@router.post("/resolve-gate")
async def resolve_review_items(
    request: ResolveReviewItemsRequest,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    return await resolve_review_items_controller(request=request, db=db)
