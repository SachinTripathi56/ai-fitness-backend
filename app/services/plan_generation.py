import asyncio
from uuid import UUID
from app.models.models import (
    User, UserProfile, WorkoutPlan, WorkoutSession, WorkoutExercise, Exercise,
    DietPlan, Meal, MealFoodItem, FoodItem, Schedule, ScheduleEvent
)
from app.services.ai_service import ai_service
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

async def generate_initial_plans_for_user(user_id: UUID, db: AsyncSession):
    """
    Generate the initial Workout Plan, Diet Plan, and Schedule in parallel
    for a user who has just completed onboarding.
    """
    logger.info(f"Generating initial plans for user {user_id}...")
    
    # 1. Fetch user profile
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == user_id))
    profile = result.scalar_one_or_none()
    if not profile:
        logger.warning(f"No profile found for user {user_id}. Cannot generate plans.")
        return

    # 2. Build profile dicts for AI service
    workout_profile = {
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

    diet_profile = {
        "age": profile.age,
        "gender": profile.gender.value if profile.gender else None,
        "weight_kg": profile.weight_kg,
        "height_cm": profile.height_cm,
        "fitness_goal": profile.fitness_goal.value if profile.fitness_goal else None,
        "activity_level": profile.activity_level.value if profile.activity_level else None,
        "diet_type": profile.diet_type.value if profile.diet_type else None,
        "allergies": profile.allergies or [],
        "dietary_restrictions": profile.dietary_restrictions or [],
        "daily_calorie_target": profile.daily_calorie_target,
        "medical_conditions": profile.medical_conditions or [],
    }

    schedule_profile = {
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

    # 3. Generate all plans in parallel using asyncio.gather
    try:
        workout_task = ai_service.generate_workout_plan(workout_profile, weeks=4)
        diet_task = ai_service.generate_diet_plan(diet_profile, days=7)
        schedule_task = ai_service.generate_schedule(schedule_profile)

        ai_workout, ai_diet, ai_schedule = await asyncio.gather(workout_task, diet_task, schedule_task)
    except Exception as e:
        logger.error(f"Error during AI parallel generation for user {user_id}: {e}")
        return

    # Deactivate existing active plans
    # Workouts
    for old_plan in (await db.execute(
        select(WorkoutPlan).where(WorkoutPlan.user_id == user_id, WorkoutPlan.is_active == True)
    )).scalars():
        old_plan.is_active = False

    # Diets
    for old_diet in (await db.execute(
        select(DietPlan).where(DietPlan.user_id == user_id, DietPlan.is_active == True)
    )).scalars():
        old_diet.is_active = False

    # Schedules
    for old_sched in (await db.execute(
        select(Schedule).where(Schedule.user_id == user_id, Schedule.is_active == True)
    )).scalars():
        old_sched.is_active = False

    # 4. Save Workout Plan
    plan = WorkoutPlan(
        user_id=user_id,
        name=ai_workout.get("plan_name", "My Workout Plan"),
        description=ai_workout.get("description"),
        plan_type="weekly",
        week_number=1,
        ai_generated=True,
    )
    db.add(plan)
    await db.flush()

    first_week = ai_workout.get("weeks", [{}])[0]
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

    # 5. Save Diet Plan
    macros = ai_diet.get("macros", {})
    diet_plan = DietPlan(
        user_id=user_id,
        name=ai_diet.get("plan_name", "My Nutrition Plan"),
        total_calories=ai_diet.get("total_daily_calories", 2000),
        protein_g=macros.get("protein_g", 0),
        carbs_g=macros.get("carbs_g", 0),
        fat_g=macros.get("fat_g", 0),
        ai_generated=True,
        notes=ai_diet.get("meal_prep_tips"),
    )
    db.add(diet_plan)
    await db.flush()

    for day_data in ai_diet.get("days", []):
        for meal_data in day_data.get("meals", []):
            meal = Meal(
                diet_plan_id=diet_plan.id,
                meal_type=meal_data.get("meal_type", "breakfast"),
                name=meal_data.get("name", "Meal"),
                suggested_time=meal_data.get("suggested_time"),
                total_calories=meal_data.get("total_calories", 0),
                protein_g=meal_data.get("protein_g", 0),
                carbs_g=meal_data.get("carbs_g", 0),
                fat_g=meal_data.get("fat_g", 0),
                day_of_week=day_data.get("day_of_week"),
                instructions=meal_data.get("instructions"),
            )
            db.add(meal)
            await db.flush()

            for fi_data in meal_data.get("food_items", []):
                fi_result = await db.execute(select(FoodItem).where(FoodItem.name == fi_data.get("name")))
                food_item = fi_result.scalar_one_or_none()
                if not food_item:
                    food_item = FoodItem(
                        name=fi_data.get("name", "Unknown"),
                        category="General",
                        calories_per_100g=(fi_data.get("calories", 0) / fi_data.get("quantity_grams", 100)) * 100 if fi_data.get("quantity_grams") else 0,
                        protein_g=fi_data.get("protein_g", 0),
                        carbs_g=fi_data.get("carbs_g", 0),
                        fat_g=fi_data.get("fat_g", 0),
                    )
                    db.add(food_item)
                    await db.flush()

                db.add(MealFoodItem(
                    meal_id=meal.id,
                    food_item_id=food_item.id,
                    quantity_grams=fi_data.get("quantity_grams", 100),
                ))

    # 6. Save Schedule
    schedule = Schedule(
        user_id=user_id,
        name=ai_schedule.get("schedule_name", "My Weekly Schedule"),
        ai_generated=True,
    )
    db.add(schedule)
    await db.flush()

    for day_data in ai_schedule.get("days", []):
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
    logger.info(f"Successfully generated initial plans for user {user_id}!")
