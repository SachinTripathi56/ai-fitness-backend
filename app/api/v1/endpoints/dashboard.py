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

    # Proactively generate plans if profile exists but no active workout plan is found
    if profile:
        plan_check = await db.execute(
            select(WorkoutPlan).where(WorkoutPlan.user_id == current_user.id, WorkoutPlan.is_active == True)
        )
        if not plan_check.scalar_one_or_none():
            from app.services.plan_generation import generate_initial_plans_for_user
            await generate_initial_plans_for_user(current_user.id, db)
            # Re-fetch profile in case generate_initial_plans_for_user made changes or to be clean
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

    # Fetch weight logs for the last 8 weeks (56 days)
    eight_weeks_ago = datetime.now(timezone.utc) - timedelta(weeks=8)
    logs_result = await db.execute(
        select(ProgressLog)
        .where(ProgressLog.user_id == current_user.id, ProgressLog.log_date >= eight_weeks_ago)
        .order_by(ProgressLog.log_date.asc())
    )
    weight_logs = logs_result.scalars().all()
    weight_data = [
        {"date": log.log_date.strftime("%d %b"), "value": log.weight_kg}
        for log in weight_logs if log.weight_kg
    ]
    # If empty, default to current profile weight
    if not weight_data and profile and profile.weight_kg:
        weight_data = [{"date": "Today", "value": profile.weight_kg}]
    elif not weight_data:
        weight_data = [{"date": "Today", "value": 70.0}]

    # Workouts this week (completed)
    week_start = datetime.now(timezone.utc) - timedelta(days=datetime.now(timezone.utc).weekday())
    comp_result = await db.execute(
        select(WorkoutCompletionLog.completed_at)
        .where(WorkoutCompletionLog.user_id == current_user.id, WorkoutCompletionLog.completed_at >= week_start)
    )
    comp_dates = comp_result.scalars().all()
    completed_days = {d.weekday() for d in comp_dates}

    # Workouts target per week
    workouts_target = profile.workout_days_per_week if profile and profile.workout_days_per_week else 4

    # Scheduled workout days
    workout_days = {0, 2, 4, 5} # Mon, Wed, Fri, Sat as default
    plan_sessions_result = await db.execute(
        select(WorkoutPlan)
        .where(WorkoutPlan.user_id == current_user.id, WorkoutPlan.is_active == True)
    )
    active_plan = plan_sessions_result.scalar_one_or_none()
    if active_plan:
        from app.models.models import WorkoutSession
        sessions_result = await db.execute(
            select(WorkoutSession.day_of_week)
            .where(WorkoutSession.plan_id == active_plan.id, WorkoutSession.is_rest_day == False)
        )
        session_days = sessions_result.scalars().all()
        day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
        workout_days = {day_map[s.value] for s in session_days if s.value in day_map}

    days_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekly_workouts = []
    for i, day_name in enumerate(days_names):
        weekly_workouts.append({
            "day": day_name,
            "completed": 1 if i in completed_days else 0,
            "target": 1 if i in workout_days else 0
        })

    workouts_this_week = len(completed_days)
    workout_completion_pct = round((workouts_this_week / workouts_target) * 100) if workouts_target > 0 else 0
    workout_completion_pct = min(100, max(0, workout_completion_pct))

    # AI Insights (logs for the last 14 days)
    logs_result_14 = await db.execute(
        select(ProgressLog)
        .where(ProgressLog.user_id == current_user.id)
        .order_by(ProgressLog.log_date.desc())
        .limit(14)
    )
    logs_14 = logs_result_14.scalars().all()

    profile_dict = {}
    if profile:
        profile_dict = {
            "fitness_goal": profile.fitness_goal.value if profile.fitness_goal else None,
            "weight_kg": profile.weight_kg,
            "target_weight_kg": profile.target_weight_kg,
        }

    progress_data = {}
    if logs_14:
        wl = [l.weight_kg for l in logs_14 if l.weight_kg]
        sl = [l.steps for l in logs_14 if l.steps]
        zl = [l.sleep_hours for l in logs_14 if l.sleep_hours]
        progress_data = {
            "current_weight": wl[0] if wl else None,
            "starting_weight": wl[-1] if wl else None,
            "completion_rate": round(sum(1 for l in logs_14 if l.workout_completed) / len(logs_14) * 100, 1),
            "avg_steps": round(sum(sl) / len(sl)) if sl else None,
            "avg_sleep": round(sum(zl) / len(zl), 1) if zl else None,
            "streak": sum(1 for l in logs_14 if l.workout_completed),
        }

    raw_recommendations = await ai_service.generate_recommendations(profile_dict, progress_data)
    insights = []
    tone_map = {"high": "warning", "medium": "neutral", "low": "positive"}
    for idx, rec in enumerate(raw_recommendations):
        tone = tone_map.get(rec.get("priority", "medium"), "neutral")
        if rec.get("type") == "motivation" or rec.get("type") == "workout":
            if tone == "neutral":
                tone = "positive"
        insights.append({
            "id": f"insight-{idx}",
            "title": rec.get("title", "Recommendation"),
            "body": rec.get("content", ""),
            "tone": tone
        })

    if not insights:
        insights = [
            {
                "id": "insight-1",
                "title": "Welcome to AIFit!",
                "body": "Complete your daily tracking to receive personalized AI recommendations.",
                "tone": "positive"
            },
            {
                "id": "insight-2",
                "title": "Hydration is key",
                "body": "Drinking water boosts metabolism and aids muscle recovery. Aim for at least 2.5L.",
                "tone": "neutral"
            }
        ]

    # Today metrics
    calories_today = latest_log.calories_consumed if latest_log and latest_log.calories_consumed else 0
    calories_target = profile.daily_calorie_target if profile and profile.daily_calorie_target else 2000
    water_ml = latest_log.water_intake_ml if latest_log and latest_log.water_intake_ml else 0
    water_target_ml = 2500
    steps = latest_log.steps if latest_log and latest_log.steps else 0
    steps_target = 10000
    sleep_hours = latest_log.sleep_hours if latest_log and latest_log.sleep_hours else 0

    return {
        "weight": weight_data,
        "calories_today": calories_today,
        "calories_target": calories_target,
        "water_ml": water_ml,
        "water_target_ml": water_target_ml,
        "steps": steps,
        "steps_target": steps_target,
        "sleep_hours": sleep_hours,
        "workout_completion_pct": workout_completion_pct,
        "weekly_workouts": weekly_workouts,
        "insights": insights
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
