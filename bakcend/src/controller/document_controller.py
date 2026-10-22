import os
import shutil
import hashlib
import asyncio
from typing import List, Dict, Any, Optional
from fastapi import UploadFile, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from ..models.db_models import Document, DocumentChunk
from ..ingestion.pipeline import run_document_ingestion

STORAGE_DIR = os.path.join(os.getcwd(), "storage")
os.makedirs(STORAGE_DIR, exist_ok=True)

def compute_sha256(file_path: str) -> str:
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hasher.update(chunk)
    return hasher.hexdigest()

async def dispatch_parallel_ingestion(tasks: List[Dict[str, Any]]):
    coroutines = [
        run_document_ingestion(doc_id=t["doc_id"], file_path=t["file_path"])
        for t in tasks
    ]
    await asyncio.gather(*coroutines, return_exceptions=True)

async def upload_documents_controller(
    files: List[UploadFile],
    background_tasks: BackgroundTasks,
    db: AsyncSession,
    project_id: Optional[int] = None
) -> Dict[str, Any]:
    queued_tasks: List[Dict[str, Any]] = []
    response_items: List[Dict[str, Any]] = []

    for file in files:
        if not file.filename.lower().endswith(".pdf"):
            response_items.append({
                "filename": file.filename,
                "status": "REJECTED",
                "reason": "Only PDF documents are supported"
            })
            continue

        temp_path = os.path.join(STORAGE_DIR, f"temp_{file.filename}")
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
            response_items.append({
                "filename": file.filename,
                "status": "ALREADY_EXISTS",
                "document_id": existing_doc.id,
                "current_status": existing_doc.status
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

        queued_tasks.append({
            "doc_id": new_doc.id,
            "file_path": final_path
        })
        response_items.append({
            "filename": file.filename,
            "status": "QUEUED",
            "document_id": new_doc.id
        })

    if queued_tasks:
        background_tasks.add_task(dispatch_parallel_ingestion, queued_tasks)

    return {
        "message": f"{len(queued_tasks)} document(s) accepted and queued for ingestion",
        "documents": response_items
    }

async def get_document_status_controller(
    document_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks_query = select(DocumentChunk).where(DocumentChunk.document_id == document_id)
    result = await db.execute(chunks_query)
    chunks_count = len(result.scalars().all())

    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "chunks_count": chunks_count,
        "error_message": doc.error_message,
        "created_at": doc.created_at
    }

async def get_document_chunks_controller(
    document_id: int,
    db: AsyncSession
) -> Dict[str, Any]:
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    chunks_query = (
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
        .order_by(DocumentChunk.chunk_index)
    )
    result = await db.execute(chunks_query)
    chunks = result.scalars().all()

    return {
        "document_id": doc.id,
        "filename": doc.filename,
        "total_chunks": len(chunks),
        "chunks": [
            {
                "chunk_index": c.chunk_index,
                "page_number": c.page_number,
                "raw_text_preview": c.raw_text[:200] + "..." if len(c.raw_text) > 200 else c.raw_text,
                "has_tables": bool(c.tables_html),
                "has_images": c.has_images,
                "searchable_content_preview": c.searchable_content[:200] + "..."
            }
            for c in chunks
        ]
    }

async def retry_document_controller(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession
) -> Dict[str, Any]:
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status not in ["FAILED", "QUEUED"]:
        return {"message": f"Document is in status '{doc.status}', retry not required."}

    doc.status = "QUEUED"
    doc.error_message = None
    await db.commit()

    background_tasks.add_task(
        run_document_ingestion,
        doc_id=doc.id,
        file_path=doc.storage_path
    )

    return {"message": f"Document ID {doc.id} queued for retry."}
