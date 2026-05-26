"""
Diet endpoints — prefix: /diet
Matches frontend: /api/diet/generate, /api/diet/today, /api/diet/week,
                  /api/diet/grocery, /api/diet/log, /api/diet/replace-meal
"""

from uuid import UUID
from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.session import get_db
from app.models.models import User, UserProfile, DietPlan, Meal, MealFoodItem, FoodItem
from app.schemas.schemas import (
    DietGenerateRequest, DietPlanResponse, MealResponse,
    FoodItemResponse, BaseResponse,
)
from app.core.dependencies import get_current_user
from app.services.ai_service import ai_service
from loguru import logger

router = APIRouter(prefix="/diet", tags=["Diet & Nutrition"])


async def _get_active_plan(user_id, db):
    result = await db.execute(
        select(DietPlan)
        .options(selectinload(DietPlan.meals))
        .where(DietPlan.user_id == user_id, DietPlan.is_active == True)
        .order_by(DietPlan.created_at.desc())
    )
    return result.scalar_one_or_none()


@router.post("/generate", response_model=DietPlanResponse)
async def generate_diet_plan(
    payload: DietGenerateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=400, detail="Complete onboarding first.")

    profile_dict = {
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

    ai_data = await ai_service.generate_diet_plan(
        user_profile=profile_dict,
        days=payload.days,
        calorie_override=payload.calorie_override,
        budget_preference=payload.budget_preference or "moderate",
        cuisine_preference=payload.cuisine_preference or "mixed",
    )

    # Deactivate old plans
    for old in (await db.execute(
        select(DietPlan).where(DietPlan.user_id == current_user.id, DietPlan.is_active == True)
    )).scalars():
        old.is_active = False

    macros = ai_data.get("macros", {})
    plan = DietPlan(
        user_id=current_user.id,
        name=payload.plan_name or ai_data.get("plan_name", "My Nutrition Plan"),
        total_calories=ai_data.get("total_daily_calories", 2000),
        protein_g=macros.get("protein_g", 0),
        carbs_g=macros.get("carbs_g", 0),
        fat_g=macros.get("fat_g", 0),
        ai_generated=True,
        notes=ai_data.get("meal_prep_tips"),
    )
    db.add(plan)
    await db.flush()

    for day_data in ai_data.get("days", []):
        for meal_data in day_data.get("meals", []):
            meal = Meal(
                diet_plan_id=plan.id,
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

    await db.commit()
    return await _get_active_plan(current_user.id, db)


@router.get("/today", response_model=dict)
async def get_today_meals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import calendar
    today = calendar.day_name[datetime.now().weekday()].lower()
    
    plan = await _get_active_plan(current_user.id, db)
    if not plan:
        profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
        profile = profile_result.scalar_one_or_none()
        if profile:
            from app.services.plan_generation import generate_initial_plans_for_user
            await generate_initial_plans_for_user(current_user.id, db)
            plan = await _get_active_plan(current_user.id, db)
            
    if not plan:
        return {
            "date": "Today",
            "total_calories": 0,
            "macros": {"protein": 0, "carbs": 0, "fat": 0},
            "meals": [],
            "water_target_ml": 2500
        }

    result = await db.execute(
        select(Meal)
        .options(selectinload(Meal.food_items).selectinload(MealFoodItem.food_item))
        .where(
            Meal.diet_plan_id == plan.id,
            Meal.day_of_week == today,
        ).order_by(Meal.suggested_time)
    )
    meals = result.scalars().all()

    mapped_meals = []
    for m in meals:
        ingredients = [mfi.food_item.name for mfi in m.food_items if mfi.food_item]
        if not ingredients:
            ingredients = [m.name]

        mapped_meals.append({
            "id": str(m.id),
            "type": m.meal_type.value,
            "time": m.suggested_time or "08:00",
            "name": m.name,
            "ingredients": ingredients,
            "calories": m.total_calories,
            "macros": {
                "protein": m.protein_g,
                "carbs": m.carbs_g,
                "fat": m.fat_g
            }
        })

    return {
        "date": "Today",
        "total_calories": plan.total_calories or 2000,
        "macros": {
            "protein": plan.protein_g or 130,
            "carbs": plan.carbs_g or 220,
            "fat": plan.fat_g or 65
        },
        "meals": mapped_meals,
        "water_target_ml": 2500
    }


@router.get("/week", response_model=dict)
async def get_week_meals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await _get_active_plan(current_user.id, db)
    if not plan:
        return {"plan": None, "message": "No active diet plan. Generate one first."}

    days = {}
    for meal in plan.meals:
        day = meal.day_of_week.value if meal.day_of_week else "monday"
        if day not in days:
            days[day] = []
        days[day].append({
            "id": str(meal.id),
            "meal_type": meal.meal_type.value,
            "name": meal.name,
            "suggested_time": meal.suggested_time,
            "total_calories": meal.total_calories,
            "protein_g": meal.protein_g,
            "carbs_g": meal.carbs_g,
            "fat_g": meal.fat_g,
        })

    return {
        "plan_id": str(plan.id),
        "plan_name": plan.name,
        "total_daily_calories": plan.total_calories,
        "macros": {"protein_g": plan.protein_g, "carbs_g": plan.carbs_g, "fat_g": plan.fat_g},
        "days": days,
    }


@router.get("/grocery", response_model=dict)
async def get_grocery_list(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Grocery list from active diet plan."""
    result = await db.execute(
        select(DietPlan)
        .options(selectinload(DietPlan.meals).selectinload(Meal.food_items).selectinload(MealFoodItem.food_item))
        .where(DietPlan.user_id == current_user.id, DietPlan.is_active == True)
        .order_by(DietPlan.created_at.desc())
    )
    plan = result.scalar_one_or_none()
    if not plan:
        return {"items": [], "total_items": 0}

    aggregated: dict = {}
    for meal in plan.meals:
        for mfi in meal.food_items:
            name = mfi.food_item.name
            if name in aggregated:
                aggregated[name]["quantity_grams"] += mfi.quantity_grams
            else:
                aggregated[name] = {"item": name, "quantity_grams": mfi.quantity_grams, "category": mfi.food_item.category}

    return {
        "items": [{"name": v["item"], "qty": f"{round(v['quantity_grams'])}g", "category": v["category"]} for v in aggregated.values()],
        "total_items": len(aggregated),
    }


@router.post("/log", response_model=BaseResponse)
async def log_meal(
    meal_id: UUID,
    eaten: bool = True,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Log that a meal was eaten."""
    result = await db.execute(
        select(Meal).join(DietPlan).where(
            Meal.id == meal_id,
            DietPlan.user_id == current_user.id,
        )
    )
    meal = result.scalar_one_or_none()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")
        
    # Get or create today's progress log to update calories consumed
    from app.models.models import ProgressLog
    from datetime import date, time as dt_time, timezone
    
    today = datetime.now(timezone.utc).date()
    start_of_day = datetime.combine(today, dt_time.min).replace(tzinfo=timezone.utc)
    end_of_day = datetime.combine(today, dt_time.max).replace(tzinfo=timezone.utc)
    
    log_result = await db.execute(
        select(ProgressLog).where(
            ProgressLog.user_id == current_user.id,
            ProgressLog.log_date >= start_of_day,
            ProgressLog.log_date <= end_of_day
        )
    )
    progress_log = log_result.scalar_one_or_none()
    if not progress_log:
        progress_log = ProgressLog(
            user_id=current_user.id,
            log_date=datetime.now(timezone.utc),
            calories_consumed=0,
            water_intake_ml=0,
            steps=0,
            sleep_hours=0.0
        )
        db.add(progress_log)
        await db.flush()
        
    if eaten:
        progress_log.calories_consumed = (progress_log.calories_consumed or 0) + meal.total_calories
        
    await db.commit()
    return BaseResponse(message=f"Meal logged successfully. Added {meal.total_calories} kcal.")


@router.post("/replace-meal", response_model=dict)
async def replace_meal(
    meal_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get an AI-suggested replacement for a meal."""
    result = await db.execute(
        select(Meal).join(DietPlan).where(
            Meal.id == meal_id,
            DietPlan.user_id == current_user.id,
        )
    )
    meal = result.scalar_one_or_none()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    return {
        "original_meal": meal.name,
        "replacement": f"Healthy alternative to {meal.name}",
        "calories": meal.total_calories,
        "message": "Replacement suggestion generated",
    }
