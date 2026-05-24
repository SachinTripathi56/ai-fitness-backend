"""
Progress endpoints — prefix: /progress
Matches frontend: /api/progress/summary, /api/progress/log, /api/progress/weight,
                  /api/progress/measurements, /api/progress/photos, /api/progress/photos/upload
"""

from uuid import UUID
from typing import List, Optional
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.session import get_db
from app.models.models import User, UserProfile, ProgressLog, ProgressPhoto, AIRecommendation
from app.schemas.schemas import (
    ProgressLogCreate, ProgressLogResponse,
    ProgressSummaryResponse, RecommendationResponse, BaseResponse,
)
from app.core.dependencies import get_current_user
from app.services.ai_service import ai_service
from app.utils.file_upload import upload_file

router = APIRouter(prefix="/progress", tags=["Progress"])


@router.post("/log", response_model=ProgressLogResponse, status_code=201)
async def log_progress(
    payload: ProgressLogCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    log = ProgressLog(user_id=current_user.id, **payload.model_dump(exclude_unset=True))
    db.add(log)
    await db.commit()
    await db.refresh(log)
    return log


@router.get("/summary", response_model=ProgressSummaryResponse)
async def get_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = profile_result.scalar_one_or_none()
    goal_weight = profile.target_weight_kg if profile else None
    starting_weight = profile.weight_kg if profile else None

    result = await db.execute(
        select(ProgressLog).where(ProgressLog.user_id == current_user.id).order_by(ProgressLog.log_date.asc())
    )
    logs = result.scalars().all()

    if not logs:
        return ProgressSummaryResponse(
            current_weight=None, starting_weight=starting_weight,
            weight_change=None, goal_weight=goal_weight,
            progress_percentage=None, avg_daily_steps=None,
            avg_sleep_hours=None, avg_water_intake_ml=None,
            workouts_this_week=0, streak_days=0, total_workouts=0,
        )

    weight_logs = [l for l in logs if l.weight_kg]
    current_weight = weight_logs[-1].weight_kg if weight_logs else None
    first_weight = weight_logs[0].weight_kg if weight_logs else starting_weight
    weight_change = round(current_weight - first_weight, 1) if current_weight and first_weight else None

    progress_pct = None
    if current_weight and starting_weight and goal_weight and starting_weight != goal_weight:
        progress_pct = min(round(abs(starting_weight - current_weight) / abs(starting_weight - goal_weight) * 100, 1), 100)

    since_30 = datetime.now(timezone.utc) - timedelta(days=30)
    recent = [l for l in logs if l.log_date >= since_30]

    step_logs = [l.steps for l in recent if l.steps]
    sleep_logs = [l.sleep_hours for l in recent if l.sleep_hours]
    water_logs = [l.water_intake_ml for l in recent if l.water_intake_ml]
    workout_logs = [l for l in logs if l.workout_completed]

    week_start = datetime.now(timezone.utc) - timedelta(days=datetime.now(timezone.utc).weekday())
    workouts_this_week = sum(1 for l in logs if l.workout_completed and l.log_date >= week_start)

    streak = 0
    today = datetime.now(timezone.utc).date()
    for i, log in enumerate(sorted(workout_logs, key=lambda x: x.log_date, reverse=True)):
        log_date = log.log_date.date() if hasattr(log.log_date, 'date') else log.log_date
        if log_date == today - timedelta(days=i):
            streak += 1
        else:
            break

    return ProgressSummaryResponse(
        current_weight=current_weight,
        starting_weight=first_weight,
        weight_change=weight_change,
        goal_weight=goal_weight,
        progress_percentage=progress_pct,
        avg_daily_steps=round(sum(step_logs) / len(step_logs)) if step_logs else None,
        avg_sleep_hours=round(sum(sleep_logs) / len(sleep_logs), 1) if sleep_logs else None,
        avg_water_intake_ml=round(sum(water_logs) / len(water_logs)) if water_logs else None,
        workouts_this_week=workouts_this_week,
        streak_days=streak,
        total_workouts=len(workout_logs),
    )


@router.get("/weight", response_model=List[dict])
async def get_weight_history(
    days: int = Query(default=30, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Weight logs for charting."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(ProgressLog)
        .where(ProgressLog.user_id == current_user.id, ProgressLog.weight_kg != None, ProgressLog.log_date >= since)
        .order_by(ProgressLog.log_date.asc())
    )
    return [
        {"date": log.log_date.isoformat(), "weight_kg": log.weight_kg}
        for log in result.scalars().all()
    ]


@router.get("/measurements", response_model=List[dict])
async def get_measurements(
    days: int = Query(default=90, ge=1, le=365),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Body measurement history."""
    since = datetime.now(timezone.utc) - timedelta(days=days)
    result = await db.execute(
        select(ProgressLog)
        .where(ProgressLog.user_id == current_user.id, ProgressLog.log_date >= since)
        .order_by(ProgressLog.log_date.asc())
    )
    return [
        {
            "date": log.log_date.isoformat(),
            "chest_cm": log.chest_cm,
            "waist_cm": log.waist_cm,
            "hips_cm": log.hips_cm,
            "bicep_cm": log.bicep_cm,
            "thigh_cm": log.thigh_cm,
            "body_fat_percentage": log.body_fat_percentage,
        }
        for log in result.scalars().all()
        if any([log.chest_cm, log.waist_cm, log.hips_cm])
    ]


@router.get("/photos", response_model=List[dict])
async def get_photos(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProgressPhoto)
        .where(ProgressPhoto.user_id == current_user.id)
        .order_by(ProgressPhoto.created_at.desc())
    )
    return [
        {
            "id": str(p.id),
            "photo_url": p.photo_url,
            "photo_type": p.photo_type,
            "created_at": p.created_at.isoformat(),
        }
        for p in result.scalars().all()
    ]


@router.post("/photos/upload", response_model=BaseResponse)
async def upload_photo(
    photo_type: str = "front",
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only JPG/PNG/WebP allowed")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Max 10MB")

    url = await upload_file(content, f"progress/{current_user.id}/{photo_type}_{file.filename}", file.content_type)

    # Create a log entry if needed, then attach photo
    log = ProgressLog(user_id=current_user.id)
    db.add(log)
    await db.flush()

    db.add(ProgressPhoto(progress_log_id=log.id, user_id=current_user.id, photo_url=url, photo_type=photo_type))
    await db.commit()
    return BaseResponse(message=f"Photo uploaded: {url}")
