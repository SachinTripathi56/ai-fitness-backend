"""
User profile endpoints — prefix: /user  (matches frontend /api/user/*)
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database.session import get_db
from app.models.models import User, UserProfile
from app.schemas.schemas import (
    UserResponse, UserProfileUpdate, UserProfileResponse,
    OnboardingRequest, BaseResponse,
)
from app.core.dependencies import get_current_user
from app.services.ai_service import ai_service
from app.services.redis_service import redis_service
from app.utils.file_upload import upload_file

router = APIRouter(prefix="/user", tags=["User Profile"])


@router.post("/onboarding", response_model=UserProfileResponse)
async def complete_onboarding(
    payload: OnboardingRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none() or UserProfile(user_id=current_user.id)
    if not profile.id:
        db.add(profile)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)

    if payload.weight_kg and payload.height_cm and payload.age and payload.gender:
        bmr = ai_service.calculate_bmr(payload.weight_kg, payload.height_cm, payload.age, payload.gender.value)
        al = payload.activity_level.value if payload.activity_level else "moderately_active"
        goal = payload.fitness_goal.value if payload.fitness_goal else "maintenance"
        tdee = ai_service.calculate_tdee(bmr, al)
        profile.bmr = round(bmr)
        profile.tdee = round(tdee)
        profile.bmi = ai_service.calculate_bmi(payload.weight_kg, payload.height_cm)
        profile.daily_calorie_target = ai_service.calculate_calorie_target(tdee, goal)

    current_user.is_onboarded = True
    await db.commit()
    await db.refresh(profile)
    
    # Generate initial AI plans (workout, diet, schedule) in parallel
    from app.services.plan_generation import generate_initial_plans_for_user
    await generate_initial_plans_for_user(current_user.id, db)
    
    await redis_service.invalidate_user_cache(str(current_user.id))
    return profile


@router.get("/profile", response_model=UserProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found. Complete onboarding first.")
    return profile


@router.put("/profile", response_model=UserProfileResponse)
async def update_profile(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(profile, field, value)

    recalc = {"weight_kg", "height_cm", "age", "gender", "activity_level", "fitness_goal"}
    if recalc.intersection(update_data.keys()):
        w, h, a = profile.weight_kg, profile.height_cm, profile.age
        g = profile.gender.value if profile.gender else None
        al = profile.activity_level.value if profile.activity_level else "moderately_active"
        goal = profile.fitness_goal.value if profile.fitness_goal else "maintenance"
        if w and h and a and g:
            bmr = ai_service.calculate_bmr(w, h, a, g)
            tdee = ai_service.calculate_tdee(bmr, al)
            profile.bmr = round(bmr)
            profile.tdee = round(tdee)
            profile.bmi = ai_service.calculate_bmi(w, h)
            profile.daily_calorie_target = ai_service.calculate_calorie_target(tdee, goal)

    await db.commit()
    await db.refresh(profile)
    await redis_service.invalidate_user_cache(str(current_user.id))
    return profile


@router.get("/preferences", response_model=dict)
async def get_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return user preferences for frontend settings page."""
    result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = result.scalar_one_or_none()
    return {
        "diet_type": profile.diet_type.value if profile and profile.diet_type else None,
        "workout_location": profile.workout_location.value if profile and profile.workout_location else None,
        "workout_days_per_week": profile.workout_days_per_week if profile else None,
        "wake_up_time": profile.wake_up_time if profile else None,
        "sleep_time": profile.sleep_time if profile else None,
        "notifications_enabled": True,
    }


@router.post("/avatar", response_model=BaseResponse)
async def upload_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    allowed = {"image/jpeg", "image/png", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only JPG/PNG/WebP allowed")
    content = await file.read()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Max 5MB")
    url = await upload_file(content, f"avatars/{current_user.id}/{file.filename}", file.content_type)
    current_user.avatar_url = url
    await db.commit()
    return BaseResponse(message=f"Avatar updated: {url}")
