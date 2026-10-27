from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

from ..database import get_db
from ..models.db_models import User
from .schemas import Register, Login, UserResponse
from .dependencies import get_current_user
from .controller import (
    register_controller,
    login_controller,
    refresh_access_token_controller,
    revoke_refresh_token_controller,
    create_organization_controller
)

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register")
async def register(
    data: Register,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    return await register_controller(data=data, db=db)

@router.post("/login")
async def login(
    data: Login,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    return await login_controller(data=data, db=db, response=response)

@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    return await refresh_access_token_controller(request=request, response=response, db=db)

@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    return await revoke_refresh_token_controller(request=request, response=response, db=db)

@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_user)
) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        first_name=current_user.first_name,
        last_name=current_user.last_name,
        phone=current_user.phone,
        org_id=current_user.org_id
    )

@router.post("/organization")
async def create_organization(
    data: Dict[str, str],
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    return await create_organization_controller(
        org_name=data.get("name", ""),
        current_user=current_user,
        db=db
    )

