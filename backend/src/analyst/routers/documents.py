from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends, status
import os
from typing import List
import shutil
from src.auth.dependencies import get_db, get_current_user
from src.models.db_models import User
from sqlalchemy.ext.asyncio import AsyncSession
from ..controller import controller
from ..ingestion.parser import parse_pdf_document, compute_sha256
router = APIRouter(prefix="/documents", tags=["documents"])

STORAGE_DIR = os.path.join(os.getcwd(), "storage")
os.makedirs(STORAGE_DIR, exist_ok=True)

@router.post("/upload")
async def upload_document(
     background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    project_id: int = 1,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)):
    # if not file.filename.lower().endswith(".pdf"):
    #     raise HTTPException(status_code=400, detail="Only PDF files are supported for now.")
    

    # temp_path = os.path.join(STORAGE_DIR, f"temp_{file.filename}")
    # with open(temp_path, "wb") as buffer:
    #     shutil.copyfileobj(file.file, buffer)
        

    #     # Becasue we dont want duplicate document.
    # file_hash = compute_sha256(temp_path)
    
    # # Checking if we already have it
    # final_path = os.path.join(STORAGE_DIR, f"{file_hash}.pdf")
    # if os.path.exists(final_path):
    #     os.remove(temp_path)
    #     return {"message": "File already exists", "file_hash": file_hash}
        
    # # Move to final destination
    # os.rename(temp_path, final_path)
    
    # # Run parsing pipeline
    # try:
    #     full_text = parse_pdf_document(final_path, file.filename)
    #     preview_text = full_text[:500] + "..." if len(full_text) > 500 else full_text
    #     return {
    #         "message": "File processed successfully",
    #         "file_hash": file_hash,
    #         "filename": file.filename,
    #         "preview": preview_text
    #     }
    # except Exception as e:
    #     raise HTTPException(status_code=500, detail=f"Error parsing document: {str(e)}")
    return await controller.upload_documents_service(
        files=files,
        project_id=project_id,
        db=db,
        background_tasks=background_tasks
    )
