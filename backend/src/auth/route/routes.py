from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import AsyncSessionLocal

from src.auth.models.auth_model import Login, Register
from src.auth.controller.auth_controller import (
    login_controller,
    refresh_access_token_controller,
    revoke_refresh_token_controller,
    register_controller
)

# API Router setup
router = APIRouter(prefix="/auth", tags=["Auth"])

from src.auth.dependencies import get_db

@router.post("/register")
async def register(data: Register, db: AsyncSession = Depends(get_db)):
    return await register_controller(data, db)

@router.post("/login")
async def login(data: Login, response: Response, db: AsyncSession = Depends(get_db)):
   
    return await login_controller(data, db, response)


@router.post("/refresh")
async def refresh_token(request: Request, response: Response, db: AsyncSession = Depends(get_db)):

    return await refresh_access_token_controller(request, response, db)


@router.post("/logout")
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    return await revoke_refresh_token_controller(request, response, db)
