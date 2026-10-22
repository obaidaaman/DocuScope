import os
import shutil
import asyncio
from typing import List, Dict, Any
from fastapi import UploadFile, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from src.models.db_models import Document, Block
from ..ingestion.parser import compute_sha256
from ..ingestion.pipeline import ingestion_graph

STORAGE_DIR = os.path.join(os.getcwd(), "storage")
os.makedirs(STORAGE_DIR, exist_ok=True)


async def process_single_doc(doc_id: int, file_path: str, filename: str):
    """Har document ke liye azaad LangGraph invocation"""
    try:
        await ingestion_graph.ainvoke(
            {
                "doc_id": doc_id,
                "file_path": file_path,
                "filename": filename,
                "blocks": [],
                "full_text": "",
                "error": None
            },
            config={"configurable": {"thread_id": f"doc_{doc_id}"}}
        )
    except Exception as e:
        print(f"[WORKER ERROR] Doc {doc_id} failed completely: {e}")


async def dispatch_parallel_ingestion(tasks_data: List[Dict[str, Any]]):
    """10 documents ko ek sath asyncio event loop me fire karta hai"""
    coroutines = [
        process_single_doc(t["doc_id"], t["file_path"], t["filename"])
        for t in tasks_data
    ]
    await asyncio.gather(*coroutines, return_exceptions=True)




async def upload_documents_service(
    files: List[UploadFile],
    project_id: int,
    db: AsyncSession,
    background_tasks: BackgroundTasks
) -> Dict[str, Any]:
    
    queued_tasks = []
    response_items = []

    for file in files:
        # Format validation
        if not file.filename.lower().endswith(".pdf"):
            response_items.append({
                "filename": file.filename, 
                "status": "REJECTED", 
                "reason": "Only PDF files supported"
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
                "document_id": existing_doc.id
            })
            continue

        os.rename(temp_path, final_path)

        # Step 4: DB Entry (Status: QUEUED)
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
            "file_path": final_path,
            "filename": file.filename
        })
        response_items.append({
            "filename": file.filename,
            "status": "QUEUED",
            "document_id": new_doc.id
        })

    # Step 5: Background Parallel Fan-out trigger
    if queued_tasks:
        background_tasks.add_task(dispatch_parallel_ingestion, queued_tasks)

    return {
        "message": f"{len(queued_tasks)} files queued for background parsing",
        "documents": response_items
    }


async def get_document_status_service(
    document_id: int, 
    db: AsyncSession
) -> Dict[str, Any]:
    """Document ka current status aur block count return karta hai"""
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    blocks_count = 0
    if doc.status == "PARSED":
        result = await db.execute(select(Block).where(Block.document_id == document_id))
        blocks_count = len(result.scalars().all())

    return {
        "id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "blocks_count": blocks_count,
        "error_message": doc.error_message,
        "created_at": doc.created_at
    }


async def retry_document_service(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession
) -> Dict[str, Any]:
    """Crash ya failure ke baad document ko wahi se resume karta hai"""
    doc = await db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if doc.status not in ["FAILED", "QUEUED"]:
        return {"message": f"Document is already {doc.status}, no retry needed."}

    doc.status = "QUEUED"
    doc.error_message = None
    await db.commit()

    background_tasks.add_task(
        process_single_doc,
        doc_id=doc.id,
        file_path=doc.storage_path,
        filename=doc.filename
    )

    return {"message": f"Document {doc.id} successfully queued for retry"}
