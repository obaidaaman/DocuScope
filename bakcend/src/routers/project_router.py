from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from ..database import get_db
from ..models.db_models import User
from ..auth.dependencies import get_current_user
from ..controller.project_controller import (
    create_project_controller,
    list_projects_controller,
    get_project_controller
)

class CreateProjectRequest(BaseModel):
    name: str
    org_id: Optional[int] = None

router = APIRouter(prefix="/projects", tags=["projects"])

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_project(
    data: CreateProjectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    return await create_project_controller(
        name=data.name,
        org_id=data.org_id,
        current_user=current_user,
        db=db
    )

@router.get("")
async def list_projects(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> List[Dict[str, Any]]:
    return await list_projects_controller(current_user=current_user, db=db)

@router.get("/{project_id}")
async def get_project(
    project_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    return await get_project_controller(project_id=project_id, current_user=current_user, db=db)
