"""
Pydantic v2 schemas for all API endpoints.
Organized by domain: Auth, User, Workout, Diet, Progress, Chat, Schedule, Admin.
"""

from datetime import datetime
from typing import Optional, List, Any, Dict
from uuid import UUID
from pydantic import BaseModel, EmailStr, field_validator, model_validator, Field

from app.models.models import (
    UserRole, Gender, FitnessGoal, ActivityLevel, DietType,
    WorkoutExperience, WorkoutLocation, ExerciseCategory, MealType, DayOfWeek
)


# ═══════════════════ BASE ═══════════════════

class BaseResponse(BaseModel):
    message: str = "Success"
    success: bool = True


class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int


# ═══════════════════ AUTH ═══════════════════

class RegisterRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=8, max_length=100)
    full_name: Optional[str] = Field(default=None, max_length=100)

    @field_validator("username")
    @classmethod
    def username_alphanumeric(cls, v: str) -> str:
        if not v.replace("_", "").replace("-", "").isalnum():
            raise ValueError("Username must be alphanumeric (underscores/hyphens allowed)")
        return v.lower()

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserAuthResponse(BaseModel):
    id: UUID
    email: EmailStr
    name: Optional[str] = None
    role: UserRole
    avatar_url: Optional[str] = None
    onboarded: bool

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def populate_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            data = data.copy()
            data["name"] = data.get("full_name") or data.get("username") or ""
            data["onboarded"] = data.get("is_onboarded") or False
        else:
            # It's an ORM object
            return {
                "id": getattr(data, "id"),
                "email": getattr(data, "email"),
                "name": getattr(data, "full_name", None) or getattr(data, "username", ""),
                "role": getattr(data, "role"),
                "avatar_url": getattr(data, "avatar_url", None),
                "onboarded": getattr(data, "is_onboarded", False)
            }
        return data


class AuthTokens(BaseModel):
    access_token: str
    refresh_token: str


class AuthResponse(BaseModel):
    user: UserAuthResponse
    tokens: AuthTokens


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8)

    @field_validator("new_password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=8)


# ═══════════════════ USER ═══════════════════

class UserBase(BaseModel):
    email: EmailStr
    username: str
    full_name: Optional[str] = None


class UserResponse(UserBase):
    id: UUID
    role: UserRole
    is_active: bool
    is_verified: bool
    is_onboarded: bool
    avatar_url: Optional[str] = None
    last_login: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class UserProfileUpdate(BaseModel):
    age: Optional[int] = Field(default=None, ge=10, le=120)
    gender: Optional[Gender] = None
    height_cm: Optional[float] = Field(default=None, ge=50, le=300)
    weight_kg: Optional[float] = Field(default=None, ge=20, le=500)
    target_weight_kg: Optional[float] = Field(default=None, ge=20, le=500)
    fitness_goal: Optional[FitnessGoal] = None
    activity_level: Optional[ActivityLevel] = None
    workout_experience: Optional[WorkoutExperience] = None
    workout_location: Optional[WorkoutLocation] = None
    available_equipment: Optional[List[str]] = None
    workout_days_per_week: Optional[int] = Field(default=None, ge=1, le=7)
    workout_duration_minutes: Optional[int] = Field(default=None, ge=10, le=300)
    diet_type: Optional[DietType] = None
    allergies: Optional[List[str]] = None
    dietary_restrictions: Optional[List[str]] = None
    medical_conditions: Optional[List[str]] = None
    injuries: Optional[List[str]] = None
    wake_up_time: Optional[str] = None
    sleep_time: Optional[str] = None
    work_start_time: Optional[str] = None
    work_end_time: Optional[str] = None
    preferred_workout_time: Optional[str] = None


class UserProfileResponse(UserProfileUpdate):
    id: UUID
    user_id: UUID
    bmi: Optional[float] = None
    bmr: Optional[float] = None
    tdee: Optional[float] = None
    daily_calorie_target: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class OnboardingRequest(UserProfileUpdate):
    """Complete onboarding data — all fields required."""
    age: int = Field(ge=10, le=120)
    gender: Gender
    height_cm: float = Field(ge=50, le=300)
    weight_kg: float = Field(ge=20, le=500)
    fitness_goal: FitnessGoal
    activity_level: ActivityLevel
    workout_experience: WorkoutExperience
    workout_location: WorkoutLocation
    diet_type: DietType


# ═══════════════════ WORKOUT ═══════════════════

class WorkoutGenerateRequest(BaseModel):
    """Request to generate AI workout plan."""
    plan_name: Optional[str] = None
    weeks: int = Field(default=4, ge=1, le=12)
    focus_areas: Optional[List[str]] = None
    override_location: Optional[WorkoutLocation] = None
    override_experience: Optional[WorkoutExperience] = None


class ExerciseResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    category: ExerciseCategory
    muscle_groups: List[str]
    equipment_needed: List[str]
    difficulty: str
    instructions: Optional[str]
    video_url: Optional[str]
    image_url: Optional[str]
    calories_per_minute: Optional[float]
    is_home_friendly: bool

    model_config = {"from_attributes": True}


class WorkoutExerciseResponse(BaseModel):
    id: UUID
    exercise: ExerciseResponse
    sets: int
    reps: Optional[str]
    duration_seconds: Optional[int]
    rest_seconds: int
    weight_kg: Optional[float]
    notes: Optional[str]
    order: int
    is_warmup: bool
    is_cooldown: bool

    model_config = {"from_attributes": True}


class WorkoutSessionResponse(BaseModel):
    id: UUID
    day_of_week: DayOfWeek
    session_name: str
    focus_area: Optional[str]
    estimated_duration_minutes: int
    warmup_notes: Optional[str]
    cooldown_notes: Optional[str]
    is_rest_day: bool
    exercises: List[WorkoutExerciseResponse] = []

    model_config = {"from_attributes": True}


class WorkoutPlanResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str]
    plan_type: str
    week_number: Optional[int]
    ai_generated: bool
    is_active: bool
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    sessions: List[WorkoutSessionResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkoutLogRequest(BaseModel):
    session_id: Optional[UUID] = None  # Already in URL path, optional in body
    duration_minutes: Optional[int] = None
    calories_burned: Optional[float] = None
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    notes: Optional[str] = None
    exercises_data: Optional[Dict[str, Any]] = None


# ═══════════════════ DIET ═══════════════════

class DietGenerateRequest(BaseModel):
    plan_name: Optional[str] = None
    days: int = Field(default=7, ge=1, le=30)
    calorie_override: Optional[int] = Field(default=None, ge=800, le=5000)
    budget_preference: Optional[str] = None  # budget, moderate, premium
    cuisine_preference: Optional[str] = None  # indian, international, mixed


class FoodItemResponse(BaseModel):
    id: UUID
    name: str
    name_hindi: Optional[str]
    category: str
    calories_per_100g: float
    protein_g: float
    carbs_g: float
    fat_g: float
    fiber_g: float
    is_vegetarian: bool
    is_vegan: bool
    is_jain: bool
    is_indian: bool
    allergens: List[str]

    model_config = {"from_attributes": True}


class MealResponse(BaseModel):
    id: UUID
    meal_type: MealType
    name: str
    suggested_time: Optional[str]
    total_calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
    day_of_week: Optional[DayOfWeek]
    instructions: Optional[str]

    model_config = {"from_attributes": True}


class DietPlanResponse(BaseModel):
    id: UUID
    name: str
    total_calories: int
    protein_g: float
    carbs_g: float
    fat_g: float
    ai_generated: bool
    is_active: bool
    start_date: Optional[datetime]
    end_date: Optional[datetime]
    meals: List[MealResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class GroceryListResponse(BaseModel):
    items: List[Dict[str, Any]]
    total_estimated_cost: Optional[float] = None
    generated_for_days: int


# ═══════════════════ PROGRESS ═══════════════════

class ProgressLogCreate(BaseModel):
    log_date: Optional[datetime] = None
    weight_kg: Optional[float] = Field(default=None, ge=20, le=500)
    body_fat_percentage: Optional[float] = Field(default=None, ge=1, le=70)
    chest_cm: Optional[float] = None
    waist_cm: Optional[float] = None
    hips_cm: Optional[float] = None
    bicep_cm: Optional[float] = None
    thigh_cm: Optional[float] = None
    steps: Optional[int] = Field(default=None, ge=0)
    calories_consumed: Optional[int] = Field(default=None, ge=0)
    calories_burned: Optional[int] = Field(default=None, ge=0)
    water_intake_ml: Optional[int] = Field(default=None, ge=0)
    sleep_hours: Optional[float] = Field(default=None, ge=0, le=24)
    sleep_quality: Optional[int] = Field(default=None, ge=1, le=5)
    mood: Optional[int] = Field(default=None, ge=1, le=5)
    energy_level: Optional[int] = Field(default=None, ge=1, le=5)
    stress_level: Optional[int] = Field(default=None, ge=1, le=5)
    workout_completed: bool = False
    workout_duration_minutes: Optional[int] = None
    notes: Optional[str] = None


class ProgressLogResponse(ProgressLogCreate):
    id: UUID
    user_id: UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class ProgressSummaryResponse(BaseModel):
    current_weight: Optional[float]
    starting_weight: Optional[float]
    weight_change: Optional[float]
    goal_weight: Optional[float]
    progress_percentage: Optional[float]
    avg_daily_steps: Optional[float]
    avg_sleep_hours: Optional[float]
    avg_water_intake_ml: Optional[float]
    workouts_this_week: int
    streak_days: int
    total_workouts: int


# ═══════════════════ CHAT ═══════════════════

class ChatMessageCreate(BaseModel):
    session_id: Optional[UUID] = None
    message: str = Field(min_length=1, max_length=2000)
    context: Optional[Dict[str, Any]] = None


class ChatMessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ChatSessionResponse(BaseModel):
    id: UUID
    title: Optional[str]
    is_active: bool
    created_at: datetime
    message_count: Optional[int] = 0

    model_config = {"from_attributes": True}


class ChatResponse(BaseModel):
    session_id: UUID
    message: ChatMessageResponse
    reply: ChatMessageResponse
    suggested_prompts: Optional[List[str]] = None


# ═══════════════════ SCHEDULE ═══════════════════

class ScheduleGenerateRequest(BaseModel):
    schedule_name: Optional[str] = None
    week_start_date: Optional[datetime] = None
    include_workouts: bool = True
    include_meals: bool = True
    include_hydration: bool = True
    include_sleep: bool = True


class ScheduleEventResponse(BaseModel):
    id: UUID
    title: str
    event_type: str
    day_of_week: DayOfWeek
    start_time: str
    end_time: Optional[str]
    duration_minutes: Optional[int]
    description: Optional[str]
    is_reminder: bool
    color: Optional[str]
    is_completed: bool
    order: int

    model_config = {"from_attributes": True}


class ScheduleResponse(BaseModel):
    id: UUID
    name: str
    ai_generated: bool
    is_active: bool
    week_start_date: Optional[datetime]
    events: List[ScheduleEventResponse] = []
    created_at: datetime

    model_config = {"from_attributes": True}


class ScheduleEventUpdate(BaseModel):
    title: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    day_of_week: Optional[DayOfWeek] = None
    is_completed: Optional[bool] = None
    description: Optional[str] = None


# ═══════════════════ ADMIN ═══════════════════

class AdminUserResponse(UserResponse):
    profile: Optional[UserProfileResponse] = None


class AdminStatsResponse(BaseModel):
    total_users: int
    active_users: int
    new_users_today: int
    new_users_this_week: int
    total_workouts_generated: int
    total_diet_plans_generated: int
    total_chat_messages: int
    avg_workouts_per_user: float


class ExerciseCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description: Optional[str] = None
    category: ExerciseCategory
    muscle_groups: List[str]
    equipment_needed: List[str] = []
    difficulty: str = "beginner"
    instructions: Optional[str] = None
    video_url: Optional[str] = None
    calories_per_minute: Optional[float] = None
    is_home_friendly: bool = True


class FoodItemCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    name_hindi: Optional[str] = None
    category: str
    calories_per_100g: float = Field(ge=0)
    protein_g: float = Field(ge=0, default=0)
    carbs_g: float = Field(ge=0, default=0)
    fat_g: float = Field(ge=0, default=0)
    fiber_g: float = Field(ge=0, default=0)
    is_vegetarian: bool = True
    is_vegan: bool = False
    is_jain: bool = False
    allergens: List[str] = []
    is_indian: bool = False


# ═══════════════════ AI RECOMMENDATIONS ═══════════════════

class RecommendationResponse(BaseModel):
    id: UUID
    recommendation_type: str
    title: str
    content: str
    priority: str
    is_dismissed: bool
    created_at: datetime

    model_config = {"from_attributes": True}
