import os
import shutil
import hashlib
import uuid
from typing import Dict, Any, List, Optional
from fastapi import (
    APIRouter, Depends, WebSocket, WebSocketDisconnect,
    UploadFile, File, Form, BackgroundTasks, HTTPException, status
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..database import get_db, AsyncSessionLocal
from ..models.db_models import Project, Document
from ..websocket.manager import ws_manager
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
from ..reconciliation.live_pipeline import execute_live_pipeline_workflow

STORAGE_DIR = os.path.join(os.getcwd(), "storage")
os.makedirs(STORAGE_DIR, exist_ok=True)

def compute_sha256(file_path: str) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

router = APIRouter(prefix="/reconciliation", tags=["reconciliation"])

# ============================================================================
# WEBSOCKET REAL-TIME EVENT STREAM
# ============================================================================

@router.websocket("/ws/{thread_id}")
async def websocket_reconciliation_stream(websocket: WebSocket, thread_id: str):
    """
    Subscribes UI to real-time events for a specific reconciliation thread.
    Streams: DOC_INGESTION -> TOPICS_DISCOVERED -> CLUSTERS_READY -> VERDICT_STREAM -> REVIEW_GATE_READY
    """
    await ws_manager.connect(thread_id, websocket)
    try:
        while True:

            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"event":"pong"}')
    except WebSocketDisconnect:
        await ws_manager.disconnect(thread_id, websocket)
    except Exception as e:
        print(f"[WS ERROR] WebSocket exception on thread {thread_id}: {e}")
        await ws_manager.disconnect(thread_id, websocket)


# ============================================================================
# UNIFIED UPLOAD & START LIVE PIPELINE
# ============================================================================

@router.post("/start-live-pipeline", status_code=status.HTTP_202_ACCEPTED)
async def start_live_pipeline(
    background_tasks: BackgroundTasks,
    project_id: int = Form(...),
    similarity_threshold: float = Form(0.45),
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Single unified API call:
    Accepts files -> Validates project & organization -> Creates thread_id ->
    Dispatches asynchronous live pipeline -> Returns thread_id for WebSocket connection.
    """
    if not project_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Project ID is required before starting the live pipeline."
        )

    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not project.org_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization is required before starting ingestion."
        )

    if not files:
        raise HTTPException(status_code=400, detail="At least 2 PDF documents are required.")

    thread_id = f"thread_{uuid.uuid4().hex[:8]}"
    doc_items: List[Dict[str, Any]] = []

    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            continue

        temp_path = os.path.join(STORAGE_DIR, f"temp_{thread_id}_{file.filename}")
        with open(temp_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        file_hash = compute_sha256(temp_path)
        final_path = os.path.join(STORAGE_DIR, f"{file_hash}.pdf")

        existing_doc = await db.scalar(
            select(Document).where(Document.file_hash == file_hash)
        )
        if existing_doc:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            if existing_doc.project_id is None:
                existing_doc.project_id = project_id
                await db.commit()
                await db.refresh(existing_doc)

            doc_items.append({
                "doc_id": existing_doc.id,
                "file_path": existing_doc.storage_path,
                "filename": file.filename
            })
            continue

        os.rename(temp_path, final_path)
        new_doc = Document(
            filename=file.filename,
            file_hash=file_hash,
            storage_path=final_path,
            status="QUEUED",
            project_id=project_id
        )
        db.add(new_doc)
        await db.commit()
        await db.refresh(new_doc)

        doc_items.append({
            "doc_id": new_doc.id,
            "file_path": final_path,
            "filename": file.filename
        })

    if len(doc_items) < 2:
        raise HTTPException(
            status_code=400,
            detail=f"At least 2 valid PDF documents are required for reconciliation. Found {len(doc_items)}."
        )

  
    background_tasks.add_task(
        execute_live_pipeline_workflow,
        thread_id=thread_id,
        doc_paths=doc_items,
        similarity_threshold=similarity_threshold
    )

    return {
        "success": True,
        "thread_id": thread_id,
        "doc_ids": [d["doc_id"] for d in doc_items],
        "message": "Live pipeline initialized. Connect to WebSocket to stream updates."
    }


@router.post("/start-live-from-docs", status_code=status.HTTP_202_ACCEPTED)
async def start_live_from_existing_docs(
    request: ReconciliationRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Starts live WebSocket pipeline for documents that are already uploaded in the project.
    """
    stmt = select(Document).where(Document.id.in_(request.doc_ids))
    res = await db.execute(stmt)
    docs = res.scalars().all()

    if len(docs) < 2:
        raise HTTPException(status_code=400, detail="At least 2 valid documents must be provided.")

    thread_id = request.thread_id or f"thread_{uuid.uuid4().hex[:8]}"
    doc_items = [
        {"doc_id": d.id, "file_path": d.storage_path, "filename": d.filename}
        for d in docs
    ]

    background_tasks.add_task(
        execute_live_pipeline_workflow,
        thread_id=thread_id,
        doc_paths=doc_items,
        similarity_threshold=request.similarity_threshold
    )

    return {
        "success": True,
        "thread_id": thread_id,
        "doc_ids": request.doc_ids,
        "message": "Live reconciliation pipeline started."
    }


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
