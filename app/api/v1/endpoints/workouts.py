"""
Workout endpoints — prefix: /workouts
Matches frontend: /api/workouts/generate, /api/workouts/today, /api/workouts/week,
                  /api/workouts/history, /api/workouts/{id}/complete
"""

from uuid import UUID
from typing import List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.session import get_db
from app.models.models import (
    User, UserProfile, WorkoutPlan, WorkoutSession,
    WorkoutExercise, Exercise, WorkoutCompletionLog,
)
from app.schemas.schemas import (
    WorkoutGenerateRequest, WorkoutPlanResponse,
    WorkoutLogRequest, BaseResponse, ExerciseResponse,
)
from app.core.dependencies import get_current_user
from app.services.ai_service import ai_service
from loguru import logger

router = APIRouter(prefix="/workouts", tags=["Workouts"])


def _profile_to_dict(profile: UserProfile) -> dict:
    return {
        "age": profile.age,
        "gender": profile.gender.value if profile.gender else None,
        "height_cm": profile.height_cm,
        "weight_kg": profile.weight_kg,
        "fitness_goal": profile.fitness_goal.value if profile.fitness_goal else None,
        "activity_level": profile.activity_level.value if profile.activity_level else None,
        "workout_experience": profile.workout_experience.value if profile.workout_experience else None,
        "workout_location": profile.workout_location.value if profile.workout_location else "home",
        "available_equipment": profile.available_equipment or [],
        "medical_conditions": profile.medical_conditions or [],
        "injuries": profile.injuries or [],
        "workout_days_per_week": profile.workout_days_per_week or 4,
        "workout_duration_minutes": profile.workout_duration_minutes or 45,
    }


async def _get_active_plan(user_id, db):
    result = await db.execute(
        select(WorkoutPlan)
        .options(
            selectinload(WorkoutPlan.sessions)
            .selectinload(WorkoutSession.exercises)
            .selectinload(WorkoutExercise.exercise)
        )
        .where(WorkoutPlan.user_id == user_id, WorkoutPlan.is_active == True)
        .order_by(WorkoutPlan.created_at.desc())
    )
    return result.scalar_one_or_none()


@router.post("/generate", response_model=WorkoutPlanResponse)
async def generate_workout_plan(
    payload: WorkoutGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=400, detail="Complete onboarding first.")

    ai_data = await ai_service.generate_workout_plan(
        user_profile=_profile_to_dict(profile),
        weeks=payload.weeks,
        focus_areas=payload.focus_areas,
    )

    # Deactivate old plans
    for old in (await db.execute(
        select(WorkoutPlan).where(WorkoutPlan.user_id == current_user.id, WorkoutPlan.is_active == True)
    )).scalars():
        old.is_active = False

    plan = WorkoutPlan(
        user_id=current_user.id,
        name=payload.plan_name or ai_data.get("plan_name", "My Workout Plan"),
        description=ai_data.get("description"),
        plan_type="weekly",
        week_number=1,
        ai_generated=True,
    )
    db.add(plan)
    await db.flush()

    first_week = ai_data.get("weeks", [{}])[0]
    for session_data in first_week.get("sessions", []):
        session = WorkoutSession(
            plan_id=plan.id,
            day_of_week=session_data.get("day_of_week", "monday"),
            session_name=session_data.get("session_name", "Workout"),
            focus_area=session_data.get("focus_area"),
            estimated_duration_minutes=session_data.get("estimated_duration_minutes", 45),
            warmup_notes=session_data.get("warmup_notes"),
            cooldown_notes=session_data.get("cooldown_notes"),
            is_rest_day=session_data.get("is_rest_day", False),
        )
        db.add(session)
        await db.flush()

        for i, ex_data in enumerate(session_data.get("exercises", [])):
            ex_result = await db.execute(select(Exercise).where(Exercise.name == ex_data.get("name")))
            exercise = ex_result.scalar_one_or_none()
            if not exercise:
                exercise = Exercise(
                    name=ex_data.get("name", "Unknown"),
                    category=ex_data.get("category", "strength"),
                    muscle_groups=ex_data.get("muscle_groups", []),
                    equipment_needed=ex_data.get("equipment_needed", []),
                    difficulty=ex_data.get("difficulty", "beginner"),
                    instructions=ex_data.get("instructions"),
                    is_home_friendly=len(ex_data.get("equipment_needed", [])) == 0,
                )
                db.add(exercise)
                await db.flush()

            db.add(WorkoutExercise(
                session_id=session.id,
                exercise_id=exercise.id,
                sets=ex_data.get("sets", 3),
                reps=str(ex_data.get("reps", "10")),
                rest_seconds=ex_data.get("rest_seconds", 60),
                notes=ex_data.get("progressive_note"),
                order=i,
                is_warmup=ex_data.get("is_warmup", False),
                is_cooldown=ex_data.get("is_cooldown", False),
            ))

    await db.commit()
    return await _get_active_plan(current_user.id, db)


@router.get("/today", response_model=dict)
async def get_today_workout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return today's workout session from the active plan."""
    import calendar
    today = calendar.day_name[datetime.now().weekday()].lower()
    plan = await _get_active_plan(current_user.id, db)
    if not plan:
        return {"session": None, "message": "No active plan. Generate one first."}

    session = next((s for s in plan.sessions if s.day_of_week.value == today), None)
    if not session:
        return {"session": None, "message": "Rest day today!"}

    return {
        "session": {
            "id": str(session.id),
            "name": session.session_name,
            "focus_area": session.focus_area,
            "estimated_duration_minutes": session.estimated_duration_minutes,
            "is_rest_day": session.is_rest_day,
            "warmup_notes": session.warmup_notes,
            "cooldown_notes": session.cooldown_notes,
            "exercises": [
                {
                    "id": str(we.id),
                    "name": we.exercise.name,
                    "sets": we.sets,
                    "reps": we.reps,
                    "rest_seconds": we.rest_seconds,
                    "muscle_groups": we.exercise.muscle_groups,
                    "instructions": we.exercise.instructions,
                    "is_warmup": we.is_warmup,
                    "is_cooldown": we.is_cooldown,
                }
                for we in sorted((we for we in session.exercises), key=lambda x: x.order)
            ],
        }
    }


@router.get("/week", response_model=dict)
async def get_week_workout(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the full weekly workout plan."""
    plan = await _get_active_plan(current_user.id, db)
    if not plan:
        return {"plan": None, "message": "No active plan. Generate one first."}

    return {
        "plan_id": str(plan.id),
        "plan_name": plan.name,
        "sessions": [
            {
                "id": str(s.id),
                "day_of_week": s.day_of_week.value,
                "session_name": s.session_name,
                "focus_area": s.focus_area,
                "estimated_duration_minutes": s.estimated_duration_minutes,
                "is_rest_day": s.is_rest_day,
                "exercise_count": len(s.exercises),
            }
            for s in sorted(
    (s for s in plan.sessions),
    key=lambda x: ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"].index(x.day_of_week.value)
)
            #for s in sorted(s for s in plan.sessions, key=lambda x: ["monday","tuesday","wednesday","thursday","friday","saturday","sunday"].index(x.day_of_week.value))
        ],
    }


@router.post("/{session_id}/complete", response_model=BaseResponse)
async def complete_workout(
    session_id: UUID,
    payload: WorkoutLogRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a workout session as complete."""
    result = await db.execute(
        select(WorkoutSession).join(WorkoutPlan).where(
            WorkoutSession.id == session_id,
            WorkoutPlan.user_id == current_user.id,
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")

    db.add(WorkoutCompletionLog(
        session_id=session_id,
        user_id=current_user.id,
        duration_minutes=payload.duration_minutes,
        calories_burned=payload.calories_burned,
        rating=payload.rating,
        notes=payload.notes,
    ))
    await db.commit()
    return BaseResponse(message="Workout completed! Great job!")


@router.get("/history", response_model=List[dict])
async def get_workout_history(
    limit: int = Query(default=20, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WorkoutCompletionLog)
        .options(selectinload(WorkoutCompletionLog.session))
        .where(WorkoutCompletionLog.user_id == current_user.id)
        .order_by(WorkoutCompletionLog.completed_at.desc())
        .limit(limit)
    )
    return [
        {
            "id": str(log.id),
            "session_name": log.session.session_name if log.session else "Unknown",
            "completed_at": log.completed_at.isoformat(),
            "duration_minutes": log.duration_minutes,
            "calories_burned": log.calories_burned,
            "rating": log.rating,
        }
        for log in result.scalars().all()
    ]


@router.get("/exercises/{exercise_id}", response_model=ExerciseResponse)
async def get_exercise(
    exercise_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Exercise).where(Exercise.id == exercise_id))
    ex = result.scalar_one_or_none()
    if not ex:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return ex
