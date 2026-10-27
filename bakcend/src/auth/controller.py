import os
import uuid
import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from fastapi import HTTPException, status, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from ..models.db_models import Organization, User, RefreshToken
from .schemas import Register, Login

SECRET_KEY = os.getenv("SECRET_KEY", "superdocs-secret-key-change-in-production")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 15

def get_utc_now():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = get_utc_now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def create_refresh_token_db(user_id: int, db: AsyncSession) -> str:
    now = get_utc_now()
    jti = str(uuid.uuid4())
    expires_at = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": str(user_id),
        "jti": jti,
        "type": "refresh",
        "exp": expires_at
    }

    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    db_token = RefreshToken(
        jti=jti,
        user_id=user_id,
        expires_at=expires_at
    )
    db.add(db_token)
    await db.commit()

    return token

async def register_controller(data: Register, db: AsyncSession) -> Dict[str, Any]:
    query = select(User).where(User.email == data.email)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Email is already registered")

    org_id_to_use = data.org_id

    if data.org_name and not org_id_to_use:
        new_org = Organization(name=data.org_name)
        db.add(new_org)
        await db.flush()
        org_id_to_use = new_org.id

    hashed_pw = hash_password(data.password)
    new_user = User(
        email=data.email,
        password_hash=hashed_pw,
        first_name=data.first_name,
        last_name=data.last_name,
        phone=data.phone,
        org_id=org_id_to_use
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return {
        "success": True,
        "message": "User registered successfully",
        "user_id": new_user.id,
        "org_id": org_id_to_use
    }

async def login_controller(data: Login, db: AsyncSession, response: Response) -> Dict[str, Any]:
    query = select(User).where(User.email == data.email)
    result = await db.execute(query)
    user = result.scalar_one_or_none()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "org_id": user.org_id}
    )
    refresh_token = await create_refresh_token_db(user.id, db)

    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )

    return {
        "success": True,
        "message": "Login successful",
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "org_id": user.org_id
        }
    }

async def refresh_access_token_controller(request: Request, response: Response, db: AsyncSession) -> Dict[str, Any]:
    token = request.cookies.get("refresh_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]

    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token missing")

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Refresh token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    jti = payload.get("jti")
    user_id_str = payload.get("sub")
    if not jti or not user_id_str:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")

    user_id = int(user_id_str)

    query = select(RefreshToken).where(RefreshToken.jti == jti)
    result = await db.execute(query)
    db_token = result.scalar_one_or_none()

    if not db_token or db_token.user_id != user_id or db_token.revoked_at is not None or db_token.expires_at < get_utc_now():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired refresh token")

    db_token.revoked_at = get_utc_now()

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")

    new_access_token = create_access_token(
        data={"sub": str(user.id), "email": user.email, "org_id": user.org_id}
    )
    new_refresh_token = await create_refresh_token_db(user.id, db)

    response.set_cookie(
        key="access_token",
        value=new_access_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60
    )
    response.set_cookie(
        key="refresh_token",
        value=new_refresh_token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
    )

    return {
        "success": True,
        "message": "Tokens refreshed successfully",
        "access_token": new_access_token
    }

async def revoke_refresh_token_controller(request: Request, response: Response, db: AsyncSession) -> Dict[str, Any]:
    token = request.cookies.get("refresh_token")
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            jti = payload.get("jti")
            if jti:
                query = select(RefreshToken).where(RefreshToken.jti == jti)
                result = await db.execute(query)
                db_token = result.scalar_one_or_none()
                if db_token and not db_token.revoked_at:
                    db_token.revoked_at = get_utc_now()
                    await db.commit()
        except Exception:
            pass

    response.delete_cookie(key="access_token")
    response.delete_cookie(key="refresh_token")
    return {"success": True, "message": "Logged out successfully"}

async def create_organization_controller(org_name: str, current_user: User, db: AsyncSession) -> Dict[str, Any]:
    if not org_name or not org_name.strip():
        raise HTTPException(status_code=400, detail="Organization name is required")
        
    new_org = Organization(name=org_name.strip())
    db.add(new_org)
    await db.flush()
    
    current_user.org_id = new_org.id
    await db.commit()
    await db.refresh(new_org)
    await db.refresh(current_user)
    
    return {
        "success": True,
        "message": "Organization created and linked successfully",
        "organization": {
            "id": new_org.id,
            "name": new_org.name
        }
    }

