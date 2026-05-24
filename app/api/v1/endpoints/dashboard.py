"""
Dashboard endpoints — prefix: /dashboard
Matches frontend: /api/dashboard/overview, /api/dashboard/insights
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta, timezone

from app.database.session import get_db
from app.models.models import User, UserProfile, ProgressLog, WorkoutCompletionLog, WorkoutPlan, DietPlan
from app.core.dependencies import get_current_user
from app.services.ai_service import ai_service

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/overview")
async def get_overview(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Single endpoint that returns everything the dashboard needs:
    profile, today's stats, recent logs, active plans summary.
    """
    # Profile
    profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = profile_result.scalar_one_or_none()

    # Latest progress log
    log_result = await db.execute(
        select(ProgressLog)
        .where(ProgressLog.user_id == current_user.id)
        .order_by(ProgressLog.log_date.desc())
        .limit(1)
    )
    latest_log = log_result.scalar_one_or_none()

    # Workouts this week
    week_start = datetime.now(timezone.utc) - timedelta(days=datetime.now(timezone.utc).weekday())
    workouts_result = await db.execute(
        select(func.count(WorkoutCompletionLog.id))
        .where(WorkoutCompletionLog.user_id == current_user.id, WorkoutCompletionLog.completed_at >= week_start)
    )
    workouts_this_week = workouts_result.scalar() or 0

    # Active plans
    has_workout_plan = bool((await db.execute(
        select(WorkoutPlan.id).where(WorkoutPlan.user_id == current_user.id, WorkoutPlan.is_active == True)
    )).scalar_one_or_none())

    has_diet_plan = bool((await db.execute(
        select(DietPlan.id).where(DietPlan.user_id == current_user.id, DietPlan.is_active == True)
    )).scalar_one_or_none())

    return {
        "user": {
            "id": str(current_user.id),
            "full_name": current_user.full_name,
            "username": current_user.username,
            "avatar_url": current_user.avatar_url,
            "is_onboarded": current_user.is_onboarded,
        },
        "profile": {
            "fitness_goal": profile.fitness_goal.value if profile and profile.fitness_goal else None,
            "current_weight": profile.weight_kg if profile else None,
            "target_weight": profile.target_weight_kg if profile else None,
            "bmi": profile.bmi if profile else None,
            "daily_calorie_target": profile.daily_calorie_target if profile else None,
        } if profile else None,
        "today": {
            "calories_consumed": latest_log.calories_consumed if latest_log else 0,
            "calories_burned": latest_log.calories_burned if latest_log else 0,
            "water_intake_ml": latest_log.water_intake_ml if latest_log else 0,
            "steps": latest_log.steps if latest_log else 0,
            "sleep_hours": latest_log.sleep_hours if latest_log else 0,
            "workout_completed": latest_log.workout_completed if latest_log else False,
            "mood": latest_log.mood if latest_log else None,
            "energy_level": latest_log.energy_level if latest_log else None,
        },
        "week": {
            "workouts_completed": workouts_this_week,
            "workouts_target": profile.workout_days_per_week if profile else 4,
        },
        "plans": {
            "has_workout_plan": has_workout_plan,
            "has_diet_plan": has_diet_plan,
        },
    }


@router.get("/insights")
async def get_insights(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI-generated insights based on recent progress."""
    profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = profile_result.scalar_one_or_none()

    logs_result = await db.execute(
        select(ProgressLog)
        .where(ProgressLog.user_id == current_user.id)
        .order_by(ProgressLog.log_date.desc())
        .limit(14)
    )
    logs = logs_result.scalars().all()

    profile_dict = {}
    if profile:
        profile_dict = {
            "fitness_goal": profile.fitness_goal.value if profile.fitness_goal else None,
            "weight_kg": profile.weight_kg,
            "target_weight_kg": profile.target_weight_kg,
        }

    progress_data = {}
    if logs:
        wl = [l.weight_kg for l in logs if l.weight_kg]
        sl = [l.steps for l in logs if l.steps]
        zl = [l.sleep_hours for l in logs if l.sleep_hours]
        progress_data = {
            "current_weight": wl[0] if wl else None,
            "starting_weight": wl[-1] if wl else None,
            "completion_rate": round(sum(1 for l in logs if l.workout_completed) / len(logs) * 100, 1),
            "avg_steps": round(sum(sl) / len(sl)) if sl else None,
            "avg_sleep": round(sum(zl) / len(zl), 1) if zl else None,
            "streak": sum(1 for l in logs if l.workout_completed),
        }

    recommendations = await ai_service.generate_recommendations(profile_dict, progress_data)

    return {
        "insights": recommendations,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
