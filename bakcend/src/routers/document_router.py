from fastapi import APIRouter, UploadFile, File, BackgroundTasks, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any

from ..database import get_db
from ..controller import (
    upload_documents_controller,
    get_document_status_controller,
    get_document_chunks_controller,
    retry_document_controller
)

router = APIRouter(prefix="/documents", tags=["documents"])

@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_documents(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    return await upload_documents_controller(
        files=files,
        background_tasks=background_tasks,
        db=db
    )

@router.get("/{document_id}")
async def get_document_status(
    document_id: int,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    return await get_document_status_controller(
        document_id=document_id,
        db=db
    )

@router.get("/{document_id}/chunks")
async def get_document_chunks(
    document_id: int,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    return await get_document_chunks_controller(
        document_id=document_id,
        db=db
    )

@router.post("/{document_id}/retry")
async def retry_document(
    document_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    return await retry_document_controller(
        document_id=document_id,
        background_tasks=background_tasks,
        db=db
    )
