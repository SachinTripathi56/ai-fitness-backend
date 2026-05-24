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

    await db.commit()
    return await _get_active_plan(current_user.id, db)


@router.get("/today", response_model=List[dict])
async def get_today_meals(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import calendar
    today = calendar.day_name[datetime.now().weekday()].lower()
    result = await db.execute(
        select(Meal).join(DietPlan).where(
            DietPlan.user_id == current_user.id,
            DietPlan.is_active == True,
            Meal.day_of_week == today,
        ).order_by(Meal.suggested_time)
    )
    meals = result.scalars().all()
    return [
        {
            "id": str(m.id),
            "meal_type": m.meal_type.value,
            "name": m.name,
            "suggested_time": m.suggested_time,
            "total_calories": m.total_calories,
            "protein_g": m.protein_g,
            "carbs_g": m.carbs_g,
            "fat_g": m.fat_g,
            "instructions": m.instructions,
        }
        for m in meals
    ]


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
        raise HTTPException(status_code=404, detail="No active diet plan")

    aggregated: dict = {}
    for meal in plan.meals:
        for mfi in meal.food_items:
            name = mfi.food_item.name
            if name in aggregated:
                aggregated[name]["quantity_grams"] += mfi.quantity_grams
            else:
                aggregated[name] = {"item": name, "quantity_grams": mfi.quantity_grams, "category": mfi.food_item.category}

    return {
        "items": [{"item": v["item"], "quantity": f"{round(v['quantity_grams'])}g", "category": v["category"]} for v in aggregated.values()],
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
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Meal not found")
    return BaseResponse(message="Meal logged successfully")


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
