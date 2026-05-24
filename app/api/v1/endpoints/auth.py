"""
Authentication endpoints — prefix: /auth
Frontend calls: /api/auth/login, /api/auth/register, etc.
"""

from datetime import datetime, timezone, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.database.session import get_db
from app.models.models import User, UserProfile, RefreshToken
from app.schemas.schemas import (
    RegisterRequest, LoginRequest, TokenResponse, RefreshTokenRequest,
    ForgotPasswordRequest, ResetPasswordRequest, ChangePasswordRequest,
    UserResponse, BaseResponse, AuthResponse, AuthTokens,
)
from app.core.security import (
    get_password_hash, verify_password,
    create_access_token, create_refresh_token,
    create_password_reset_token, verify_password_reset_token,
)
from app.core.config import settings
from app.core.dependencies import get_current_user
from app.services.redis_service import redis_service
from loguru import logger

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    result = await db.execute(select(User).where(User.username == payload.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Username already taken")

    user = User(
        email=payload.email,
        username=payload.username,
        hashed_password=get_password_hash(payload.password),
        full_name=payload.full_name,
    )
    db.add(user)
    await db.flush()
    db.add(UserProfile(user_id=user.id))
    await db.commit()
    await db.refresh(user)

    access_token = str(user.id)
    refresh_token = str(user.id)

    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    return AuthResponse(
        user=user,
        tokens=AuthTokens(
            access_token=access_token,
            refresh_token=refresh_token
        )
    )


@router.post("/login", response_model=AuthResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")

    access_token = str(user.id)
    refresh_token = str(user.id)

    user.last_login = datetime.now(timezone.utc)
    await db.commit()

    return AuthResponse(
        user=user,
        tokens=AuthTokens(
            access_token=access_token,
            refresh_token=refresh_token
        )
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(payload: RefreshTokenRequest, db: AsyncSession = Depends(get_db)):
    try:
        user_id = UUID(payload.refresh_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")

    new_access = str(user.id)
    new_refresh = str(user.id)

    return TokenResponse(
        access_token=new_access,
        refresh_token=new_refresh,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", response_model=BaseResponse)
async def logout(
    payload: RefreshTokenRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return BaseResponse(message="Logged out successfully")


@router.post("/forgot-password", response_model=BaseResponse)
async def forgot_password(payload: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.email == payload.email))
    user = result.scalar_one_or_none()
    if user:
        token = create_password_reset_token(payload.email)
        await redis_service.set(f"password_reset:{payload.email}", token, ttl=3600)
        logger.info(f"Password reset token for {payload.email}: {token[:20]}...")
    return BaseResponse(message="If this email is registered, a reset link has been sent.")


@router.post("/reset-password", response_model=BaseResponse)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    email = verify_password_reset_token(payload.token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired reset token")
    cached = await redis_service.get(f"password_reset:{email}")
    if not cached or cached != payload.token:
        raise HTTPException(status_code=400, detail="Reset token already used or expired")
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.hashed_password = get_password_hash(payload.new_password)
    await db.commit()
    await redis_service.delete(f"password_reset:{email}")
    return BaseResponse(message="Password reset successfully")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user
