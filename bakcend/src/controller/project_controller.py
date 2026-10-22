from typing import List, Dict, Any, Optional
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.db_models import Project, Organization, User, Document

async def create_project_controller(
    name: str,
    org_id: Optional[int],
    current_user: User,
    db: AsyncSession
) -> Dict[str, Any]:
    target_org_id = org_id or current_user.org_id

    if target_org_id:
        org = await db.get(Organization, target_org_id)
        if not org:
            raise HTTPException(status_code=404, detail="Organization not found")

    new_project = Project(
        name=name,
        org_id=target_org_id,
        created_by_id=current_user.id
    )
    db.add(new_project)
    await db.commit()
    await db.refresh(new_project)

    return {
        "success": True,
        "message": "Project created successfully",
        "project": {
            "id": new_project.id,
            "name": new_project.name,
            "org_id": new_project.org_id,
            "created_by_id": new_project.created_by_id,
            "created_at": new_project.created_at
        }
    }

async def list_projects_controller(
    current_user: User,
    db: AsyncSession
) -> List[Dict[str, Any]]:
    query = select(Project)
    if current_user.org_id:
        query = query.where(
            (Project.org_id == current_user.org_id) | (Project.created_by_id == current_user.id)
        )
    else:
        query = query.where(Project.created_by_id == current_user.id)

    query = query.order_by(Project.created_at.desc())
    res = await db.execute(query)
    projects = res.scalars().all()

    return [
        {
            "id": p.id,
            "name": p.name,
            "org_id": p.org_id,
            "created_by_id": p.created_by_id,
            "created_at": p.created_at
        }
        for p in projects
    ]

async def get_project_controller(
    project_id: int,
    current_user: User,
    db: AsyncSession
) -> Dict[str, Any]:
    project = await db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    docs_query = select(Document).where(Document.project_id == project_id).order_by(Document.created_at.desc())
    docs_res = await db.execute(docs_query)
    docs = docs_res.scalars().all()

    return {
        "id": project.id,
        "name": project.name,
        "org_id": project.org_id,
        "created_by_id": project.created_by_id,
        "created_at": project.created_at,
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "status": d.status,
                "created_at": d.created_at
            }
            for d in docs
        ]
    }
