"""
Schedule endpoints — prefix: /schedule  (matches frontend /api/schedule/*)
"""

from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.session import get_db
from app.models.models import User, UserProfile, Schedule, ScheduleEvent
from app.schemas.schemas import (
    ScheduleGenerateRequest, ScheduleResponse,
    ScheduleEventResponse, ScheduleEventUpdate, BaseResponse,
)
from app.core.dependencies import get_current_user
from app.services.ai_service import ai_service

router = APIRouter(prefix="/schedule", tags=["Schedule"])


async def _get_active_schedule(user_id, db):
    result = await db.execute(
        select(Schedule)
        .options(selectinload(Schedule.events))
        .where(Schedule.user_id == user_id, Schedule.is_active == True)
        .order_by(Schedule.created_at.desc())
    )
    return result.scalar_one_or_none()


@router.post("/generate", response_model=ScheduleResponse)
async def generate_schedule(
    payload: ScheduleGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=400, detail="Complete onboarding first.")

    profile_dict = {
        "fitness_goal": profile.fitness_goal.value if profile.fitness_goal else None,
        "workout_location": profile.workout_location.value if profile.workout_location else None,
        "workout_days_per_week": profile.workout_days_per_week or 4,
        "workout_duration_minutes": profile.workout_duration_minutes or 45,
        "diet_type": profile.diet_type.value if profile.diet_type else None,
        "wake_up_time": profile.wake_up_time or "06:30",
        "sleep_time": profile.sleep_time or "22:30",
        "work_start_time": profile.work_start_time or "09:00",
        "work_end_time": profile.work_end_time or "18:00",
        "preferred_workout_time": profile.preferred_workout_time or "06:30",
    }

    ai_data = await ai_service.generate_schedule(profile_dict)

    for old in (await db.execute(
        select(Schedule).where(Schedule.user_id == current_user.id, Schedule.is_active == True)
    )).scalars():
        old.is_active = False

    schedule = Schedule(
        user_id=current_user.id,
        name=payload.schedule_name or ai_data.get("schedule_name", "My Weekly Schedule"),
        ai_generated=True,
        week_start_date=payload.week_start_date,
    )
    db.add(schedule)
    await db.flush()

    for day_data in ai_data.get("days", []):
        for i, event_data in enumerate(day_data.get("events", [])):
            db.add(ScheduleEvent(
                schedule_id=schedule.id,
                title=event_data.get("title", "Event"),
                event_type=event_data.get("event_type", "lifestyle"),
                day_of_week=day_data.get("day_of_week"),
                start_time=event_data.get("start_time", "09:00"),
                end_time=event_data.get("end_time"),
                duration_minutes=event_data.get("duration_minutes"),
                description=event_data.get("description"),
                is_reminder=event_data.get("is_reminder", False),
                color=event_data.get("color", "#4CAF50"),
                order=event_data.get("order", i),
            ))

    await db.commit()
    return await _get_active_schedule(current_user.id, db)


@router.get("/today", response_model=List[dict])
async def get_today_schedule(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return today's schedule events."""
    import calendar
    from datetime import datetime
    today = calendar.day_name[datetime.now().weekday()].lower()
    schedule = await _get_active_schedule(current_user.id, db)
    if not schedule:
        profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
        profile = profile_result.scalar_one_or_none()
        if profile:
            from app.services.plan_generation import generate_initial_plans_for_user
            await generate_initial_plans_for_user(current_user.id, db)
            schedule = await _get_active_schedule(current_user.id, db)
            
    if not schedule:
        return []

    events = [e for e in schedule.events if e.day_of_week.value == today]
    return [
        {
            "id": str(e.id),
            "title": e.title,
            "event_type": e.event_type,
            "start_time": e.start_time,
            "end_time": e.end_time,
            "duration_minutes": e.duration_minutes,
            "description": e.description,
            "color": e.color,
            "is_completed": e.is_completed,
        }
        for e in sorted(events, key=lambda x: x.start_time)
    ]


@router.get("/week", response_model=dict)
async def get_week_schedule(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    schedule = await _get_active_schedule(current_user.id, db)
    if not schedule:
        profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
        profile = profile_result.scalar_one_or_none()
        if profile:
            from app.services.plan_generation import generate_initial_plans_for_user
            await generate_initial_plans_for_user(current_user.id, db)
            schedule = await _get_active_schedule(current_user.id, db)
            
    if not schedule:
        return {"schedule": None, "message": "No active schedule. Generate one first."}

    days = {}
    for event in schedule.events:
        day = event.day_of_week.value
        if day not in days:
            days[day] = []
        days[day].append({
            "id": str(event.id),
            "title": event.title,
            "event_type": event.event_type,
            "start_time": event.start_time,
            "end_time": event.end_time,
            "color": event.color,
            "is_completed": event.is_completed,
        })

    return {"schedule_id": str(schedule.id), "schedule_name": schedule.name, "days": days}


@router.patch("/update", response_model=dict)
async def update_event(
    event_id: UUID,
    payload: ScheduleEventUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ScheduleEvent).join(Schedule).where(
            ScheduleEvent.id == event_id, Schedule.user_id == current_user.id
        )
    )
    event = result.scalar_one_or_none()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(event, field, value)
    await db.commit()
    await db.refresh(event)
    return {"id": str(event.id), "message": "Event updated"}


@router.post("/reschedule", response_model=dict)
async def reschedule(
    event_type: str,
    context: dict = {},
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI-powered adaptive rescheduling."""
    profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = profile_result.scalar_one_or_none()
    profile_dict = {"fitness_goal": profile.fitness_goal.value if profile and profile.fitness_goal else None}
    return await ai_service.adapt_schedule(profile_dict, event_type, context)
