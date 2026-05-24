"""
Admin endpoints — prefix: /admin
Matches frontend: /api/admin/users, /api/admin/workouts, /api/admin/foods,
                  /api/admin/analytics, /api/admin/notifications
"""

from uuid import UUID
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.session import get_db
from app.models.models import User, WorkoutPlan, DietPlan, ChatMessage, Exercise, FoodItem, Notification
from app.schemas.schemas import (
    AdminUserResponse, AdminStatsResponse,
    ExerciseCreate, ExerciseResponse,
    FoodItemCreate, FoodItemResponse,
    BaseResponse,
)
from app.core.dependencies import require_admin

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/analytics", response_model=AdminStatsResponse)
async def get_analytics(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)

    total_users = (await db.execute(select(func.count(User.id)))).scalar()
    active_users = (await db.execute(select(func.count(User.id)).where(User.is_active == True))).scalar()
    new_today = (await db.execute(select(func.count(User.id)).where(User.created_at >= today_start))).scalar()
    new_week = (await db.execute(select(func.count(User.id)).where(User.created_at >= week_start))).scalar()
    total_workouts = (await db.execute(select(func.count(WorkoutPlan.id)))).scalar()
    total_diets = (await db.execute(select(func.count(DietPlan.id)))).scalar()
    total_chats = (await db.execute(select(func.count(ChatMessage.id)))).scalar()

    return AdminStatsResponse(
        total_users=total_users,
        active_users=active_users,
        new_users_today=new_today,
        new_users_this_week=new_week,
        total_workouts_generated=total_workouts,
        total_diet_plans_generated=total_diets,
        total_chat_messages=total_chats,
        avg_workouts_per_user=round(total_workouts / total_users, 2) if total_users else 0,
    )


@router.get("/users", response_model=List[AdminUserResponse])
async def list_users(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, le=100),
    search: Optional[str] = None,
    is_active: Optional[bool] = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = select(User)
    if search:
        query = query.where(User.email.ilike(f"%{search}%") | User.username.ilike(f"%{search}%"))
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    query = query.offset((page - 1) * per_page).limit(per_page).order_by(User.created_at.desc())
    return (await db.execute(query)).scalars().all()


@router.patch("/users/{user_id}/toggle", response_model=BaseResponse)
async def toggle_user(user_id: UUID, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = not user.is_active
    await db.commit()
    return BaseResponse(message=f"User {'activated' if user.is_active else 'deactivated'}")


@router.get("/workouts", response_model=List[dict])
async def list_all_workouts(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(
        select(WorkoutPlan).offset((page - 1) * per_page).limit(per_page).order_by(WorkoutPlan.created_at.desc())
    )
    return [{"id": str(p.id), "name": p.name, "user_id": str(p.user_id), "created_at": p.created_at.isoformat()} for p in result.scalars().all()]


@router.post("/foods", response_model=FoodItemResponse, status_code=201)
async def create_food(payload: FoodItemCreate, db: AsyncSession = Depends(get_db), _: User = Depends(require_admin)):
    food = FoodItem(**payload.model_dump())
    db.add(food)
    await db.commit()
    await db.refresh(food)
    return food


@router.get("/foods", response_model=List[FoodItemResponse])
async def list_foods(
    q: Optional[str] = None,
    limit: int = Query(default=20, le=100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    query = select(FoodItem).where(FoodItem.is_active == True)
    if q:
        query = query.where(FoodItem.name.ilike(f"%{q}%"))
    return (await db.execute(query.limit(limit))).scalars().all()


@router.post("/notifications", response_model=BaseResponse)
async def send_notification(
    title: str,
    message: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
):
    result = await db.execute(select(User.id).where(User.is_active == True))
    user_ids = result.scalars().all()
    db.add_all([Notification(user_id=uid, title=title, message=message, notification_type="announcement") for uid in user_ids])
    await db.commit()
    return BaseResponse(message=f"Notification sent to {len(user_ids)} users")
