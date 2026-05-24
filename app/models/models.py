"""
All SQLAlchemy ORM models for the AI Fitness Coach Platform.
Normalized PostgreSQL schema with relationships, indexes, and audit timestamps.
"""

import uuid
from datetime import datetime
from enum import Enum as PyEnum
from typing import Optional, List

from sqlalchemy import (
    String, Integer, Float, Boolean, Text, DateTime,
    ForeignKey, Enum, JSON, Index, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.session import Base


# ─────────────────── ENUMS ───────────────────

class UserRole(str, PyEnum):
    USER = "user"
    ADMIN = "admin"
    TRAINER = "trainer"


class Gender(str, PyEnum):
    MALE = "male"
    FEMALE = "female"
    OTHER = "other"


class FitnessGoal(str, PyEnum):
    WEIGHT_LOSS = "weight_loss"
    MUSCLE_GAIN = "muscle_gain"
    FAT_LOSS = "fat_loss"
    MAINTENANCE = "maintenance"
    ATHLETIC_PERFORMANCE = "athletic_performance"


class ActivityLevel(str, PyEnum):
    SEDENTARY = "sedentary"
    LIGHTLY_ACTIVE = "lightly_active"
    MODERATELY_ACTIVE = "moderately_active"
    VERY_ACTIVE = "very_active"
    EXTREMELY_ACTIVE = "extremely_active"


class DietType(str, PyEnum):
    VEGETARIAN = "vegetarian"
    VEGAN = "vegan"
    NON_VEG = "non_veg"
    JAIN = "jain"
    KETO = "keto"
    PALEO = "paleo"
    MEDITERRANEAN = "mediterranean"


class WorkoutExperience(str, PyEnum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class WorkoutLocation(str, PyEnum):
    HOME = "home"
    GYM = "gym"
    BOTH = "both"


class ExerciseCategory(str, PyEnum):
    STRENGTH = "strength"
    CARDIO = "cardio"
    HIIT = "hiit"
    YOGA = "yoga"
    MOBILITY = "mobility"
    STRETCHING = "stretching"
    CALISTHENICS = "calisthenics"


class MealType(str, PyEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"
    PRE_WORKOUT = "pre_workout"
    POST_WORKOUT = "post_workout"


class DayOfWeek(str, PyEnum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"
    SATURDAY = "saturday"
    SUNDAY = "sunday"


# ─────────────────── MIXINS ───────────────────

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ─────────────────── USER ───────────────────

class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255))
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_onboarded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    profile: Mapped[Optional["UserProfile"]] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    workouts: Mapped[List["WorkoutPlan"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    diet_plans: Mapped[List["DietPlan"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    progress_logs: Mapped[List["ProgressLog"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    chat_sessions: Mapped[List["ChatSession"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    schedules: Mapped[List["Schedule"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    refresh_tokens: Mapped[List["RefreshToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_users_email_active", "email", "is_active"),
    )


class RefreshToken(Base, TimestampMixin):
    __tablename__ = "refresh_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token: Mapped[str] = mapped_column(String(500), unique=True, index=True, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_revoked: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped["User"] = relationship(back_populates="refresh_tokens")


# ─────────────────── USER PROFILE ───────────────────

class UserProfile(Base, TimestampMixin):
    __tablename__ = "user_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)

    # Demographics
    age: Mapped[Optional[int]] = mapped_column(Integer)
    gender: Mapped[Optional[Gender]] = mapped_column(Enum(Gender))
    height_cm: Mapped[Optional[float]] = mapped_column(Float)
    weight_kg: Mapped[Optional[float]] = mapped_column(Float)
    target_weight_kg: Mapped[Optional[float]] = mapped_column(Float)

    # Fitness Profile
    fitness_goal: Mapped[Optional[FitnessGoal]] = mapped_column(Enum(FitnessGoal))
    activity_level: Mapped[Optional[ActivityLevel]] = mapped_column(Enum(ActivityLevel))
    workout_experience: Mapped[Optional[WorkoutExperience]] = mapped_column(Enum(WorkoutExperience))
    workout_location: Mapped[Optional[WorkoutLocation]] = mapped_column(Enum(WorkoutLocation))
    available_equipment: Mapped[Optional[List]] = mapped_column(JSON, default=list)
    workout_days_per_week: Mapped[Optional[int]] = mapped_column(Integer)
    workout_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)

    # Diet Profile
    diet_type: Mapped[Optional[DietType]] = mapped_column(Enum(DietType))
    allergies: Mapped[Optional[List]] = mapped_column(JSON, default=list)
    dietary_restrictions: Mapped[Optional[List]] = mapped_column(JSON, default=list)
    daily_calorie_target: Mapped[Optional[int]] = mapped_column(Integer)

    # Health
    medical_conditions: Mapped[Optional[List]] = mapped_column(JSON, default=list)
    injuries: Mapped[Optional[List]] = mapped_column(JSON, default=list)
    medications: Mapped[Optional[List]] = mapped_column(JSON, default=list)

    # Schedule Preferences
    wake_up_time: Mapped[Optional[str]] = mapped_column(String(10))
    sleep_time: Mapped[Optional[str]] = mapped_column(String(10))
    work_start_time: Mapped[Optional[str]] = mapped_column(String(10))
    work_end_time: Mapped[Optional[str]] = mapped_column(String(10))
    preferred_workout_time: Mapped[Optional[str]] = mapped_column(String(10))

    # Calculated fields (updated by AI)
    bmi: Mapped[Optional[float]] = mapped_column(Float)
    bmr: Mapped[Optional[float]] = mapped_column(Float)
    tdee: Mapped[Optional[float]] = mapped_column(Float)

    user: Mapped["User"] = relationship(back_populates="profile")


# ─────────────────── EXERCISE DATABASE ───────────────────

class Exercise(Base, TimestampMixin):
    __tablename__ = "exercises"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[ExerciseCategory] = mapped_column(Enum(ExerciseCategory), nullable=False)
    muscle_groups: Mapped[List] = mapped_column(JSON, default=list)
    equipment_needed: Mapped[List] = mapped_column(JSON, default=list)
    difficulty: Mapped[str] = mapped_column(String(20), default="beginner")
    instructions: Mapped[Optional[str]] = mapped_column(Text)
    video_url: Mapped[Optional[str]] = mapped_column(String(500))
    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    calories_per_minute: Mapped[Optional[float]] = mapped_column(Float)
    is_home_friendly: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    workout_exercises: Mapped[List["WorkoutExercise"]] = relationship(back_populates="exercise")


# ─────────────────── WORKOUT PLANS ───────────────────

class WorkoutPlan(Base, TimestampMixin):
    __tablename__ = "workout_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    plan_type: Mapped[str] = mapped_column(String(50), default="weekly")
    week_number: Mapped[Optional[int]] = mapped_column(Integer)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    ai_prompt_used: Mapped[Optional[str]] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="workouts")
    sessions: Mapped[List["WorkoutSession"]] = relationship(back_populates="plan", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_workout_plans_user_active", "user_id", "is_active"),
    )


class WorkoutSession(Base, TimestampMixin):
    __tablename__ = "workout_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workout_plans.id", ondelete="CASCADE"), nullable=False)
    day_of_week: Mapped[DayOfWeek] = mapped_column(Enum(DayOfWeek), nullable=False)
    session_name: Mapped[str] = mapped_column(String(200), nullable=False)
    focus_area: Mapped[Optional[str]] = mapped_column(String(200))
    estimated_duration_minutes: Mapped[int] = mapped_column(Integer, default=45)
    warmup_notes: Mapped[Optional[str]] = mapped_column(Text)
    cooldown_notes: Mapped[Optional[str]] = mapped_column(Text)
    is_rest_day: Mapped[bool] = mapped_column(Boolean, default=False)
    order: Mapped[int] = mapped_column(Integer, default=0)

    plan: Mapped["WorkoutPlan"] = relationship(back_populates="sessions")
    exercises: Mapped[List["WorkoutExercise"]] = relationship(back_populates="session", cascade="all, delete-orphan")
    completion_logs: Mapped[List["WorkoutCompletionLog"]] = relationship(back_populates="session")


class WorkoutExercise(Base):
    __tablename__ = "workout_exercises"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workout_sessions.id", ondelete="CASCADE"), nullable=False)
    exercise_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exercises.id"), nullable=False)
    sets: Mapped[int] = mapped_column(Integer, default=3)
    reps: Mapped[Optional[str]] = mapped_column(String(50))  # "8-12" or "10"
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    rest_seconds: Mapped[int] = mapped_column(Integer, default=60)
    weight_kg: Mapped[Optional[float]] = mapped_column(Float)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    order: Mapped[int] = mapped_column(Integer, default=0)
    is_warmup: Mapped[bool] = mapped_column(Boolean, default=False)
    is_cooldown: Mapped[bool] = mapped_column(Boolean, default=False)

    session: Mapped["WorkoutSession"] = relationship(back_populates="exercises")
    exercise: Mapped["Exercise"] = relationship(back_populates="workout_exercises")


class WorkoutCompletionLog(Base, TimestampMixin):
    __tablename__ = "workout_completion_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("workout_sessions.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    calories_burned: Mapped[Optional[float]] = mapped_column(Float)
    rating: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5
    notes: Mapped[Optional[str]] = mapped_column(Text)
    exercises_data: Mapped[Optional[dict]] = mapped_column(JSON)

    session: Mapped["WorkoutSession"] = relationship(back_populates="completion_logs")


# ─────────────────── DIET PLANS ───────────────────

class FoodItem(Base, TimestampMixin):
    __tablename__ = "food_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    name_hindi: Mapped[Optional[str]] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100))
    calories_per_100g: Mapped[float] = mapped_column(Float, nullable=False)
    protein_g: Mapped[float] = mapped_column(Float, default=0)
    carbs_g: Mapped[float] = mapped_column(Float, default=0)
    fat_g: Mapped[float] = mapped_column(Float, default=0)
    fiber_g: Mapped[float] = mapped_column(Float, default=0)
    is_vegetarian: Mapped[bool] = mapped_column(Boolean, default=True)
    is_vegan: Mapped[bool] = mapped_column(Boolean, default=False)
    is_jain: Mapped[bool] = mapped_column(Boolean, default=False)
    allergens: Mapped[List] = mapped_column(JSON, default=list)
    is_indian: Mapped[bool] = mapped_column(Boolean, default=False)
    image_url: Mapped[Optional[str]] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DietPlan(Base, TimestampMixin):
    __tablename__ = "diet_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    total_calories: Mapped[int] = mapped_column(Integer)
    protein_g: Mapped[float] = mapped_column(Float)
    carbs_g: Mapped[float] = mapped_column(Float)
    fat_g: Mapped[float] = mapped_column(Float)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped["User"] = relationship(back_populates="diet_plans")
    meals: Mapped[List["Meal"]] = relationship(back_populates="diet_plan", cascade="all, delete-orphan")


class Meal(Base, TimestampMixin):
    __tablename__ = "meals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    diet_plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("diet_plans.id", ondelete="CASCADE"), nullable=False)
    meal_type: Mapped[MealType] = mapped_column(Enum(MealType), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    suggested_time: Mapped[Optional[str]] = mapped_column(String(10))
    total_calories: Mapped[int] = mapped_column(Integer)
    protein_g: Mapped[float] = mapped_column(Float)
    carbs_g: Mapped[float] = mapped_column(Float)
    fat_g: Mapped[float] = mapped_column(Float)
    day_of_week: Mapped[Optional[DayOfWeek]] = mapped_column(Enum(DayOfWeek))
    instructions: Mapped[Optional[str]] = mapped_column(Text)

    diet_plan: Mapped["DietPlan"] = relationship(back_populates="meals")
    food_items: Mapped[List["MealFoodItem"]] = relationship(back_populates="meal", cascade="all, delete-orphan")


class MealFoodItem(Base):
    __tablename__ = "meal_food_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    meal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meals.id", ondelete="CASCADE"), nullable=False)
    food_item_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("food_items.id"), nullable=False)
    quantity_grams: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(String(200))

    meal: Mapped["Meal"] = relationship(back_populates="food_items")
    food_item: Mapped["FoodItem"] = relationship()


# ─────────────────── PROGRESS TRACKING ───────────────────

class ProgressLog(Base, TimestampMixin):
    __tablename__ = "progress_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    log_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Body metrics
    weight_kg: Mapped[Optional[float]] = mapped_column(Float)
    body_fat_percentage: Mapped[Optional[float]] = mapped_column(Float)
    chest_cm: Mapped[Optional[float]] = mapped_column(Float)
    waist_cm: Mapped[Optional[float]] = mapped_column(Float)
    hips_cm: Mapped[Optional[float]] = mapped_column(Float)
    bicep_cm: Mapped[Optional[float]] = mapped_column(Float)
    thigh_cm: Mapped[Optional[float]] = mapped_column(Float)

    # Daily metrics
    steps: Mapped[Optional[int]] = mapped_column(Integer)
    calories_consumed: Mapped[Optional[int]] = mapped_column(Integer)
    calories_burned: Mapped[Optional[int]] = mapped_column(Integer)
    water_intake_ml: Mapped[Optional[int]] = mapped_column(Integer)
    sleep_hours: Mapped[Optional[float]] = mapped_column(Float)
    sleep_quality: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5
    mood: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5
    energy_level: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5
    stress_level: Mapped[Optional[int]] = mapped_column(Integer)  # 1-5

    # Workout
    workout_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    workout_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)

    notes: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped["User"] = relationship(back_populates="progress_logs")
    photos: Mapped[List["ProgressPhoto"]] = relationship(back_populates="progress_log", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_progress_logs_user_date", "user_id", "log_date"),
    )


class ProgressPhoto(Base, TimestampMixin):
    __tablename__ = "progress_photos"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    progress_log_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("progress_logs.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    photo_url: Mapped[str] = mapped_column(String(500), nullable=False)
    photo_type: Mapped[str] = mapped_column(String(50), default="front")  # front, back, side
    notes: Mapped[Optional[str]] = mapped_column(String(500))

    progress_log: Mapped["ProgressLog"] = relationship(back_populates="photos")


# ─────────────────── AI CHAT ───────────────────

class ChatSession(Base, TimestampMixin):
    __tablename__ = "chat_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    user: Mapped["User"] = relationship(back_populates="chat_sessions")
    messages: Mapped[List["ChatMessage"]] = relationship(back_populates="session", cascade="all, delete-orphan", order_by="ChatMessage.created_at")


class ChatMessage(Base, TimestampMixin):
    __tablename__ = "chat_messages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant | system
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer)
    extra_data: Mapped[Optional[dict]] = mapped_column("metadata", JSON)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")


# ─────────────────── SCHEDULE ───────────────────

class Schedule(Base, TimestampMixin):
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    week_start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    user: Mapped["User"] = relationship(back_populates="schedules")
    events: Mapped[List["ScheduleEvent"]] = relationship(back_populates="schedule", cascade="all, delete-orphan")


class ScheduleEvent(Base, TimestampMixin):
    __tablename__ = "schedule_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    schedule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)  # workout, meal, hydration, sleep, etc
    day_of_week: Mapped[DayOfWeek] = mapped_column(Enum(DayOfWeek), nullable=False)
    start_time: Mapped[str] = mapped_column(String(10), nullable=False)
    end_time: Mapped[Optional[str]] = mapped_column(String(10))
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    description: Mapped[Optional[str]] = mapped_column(Text)
    is_reminder: Mapped[bool] = mapped_column(Boolean, default=False)
    reminder_minutes_before: Mapped[int] = mapped_column(Integer, default=15)
    color: Mapped[Optional[str]] = mapped_column(String(20))
    is_completed: Mapped[bool] = mapped_column(Boolean, default=False)
    order: Mapped[int] = mapped_column(Integer, default=0)

    schedule: Mapped["Schedule"] = relationship(back_populates="events")


# ─────────────────── NOTIFICATIONS ───────────────────

class Notification(Base, TimestampMixin):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    notification_type: Mapped[str] = mapped_column(String(50))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    action_url: Mapped[Optional[str]] = mapped_column(String(500))
    extra_data: Mapped[Optional[dict]] = mapped_column("metadata", JSON)


# ─────────────────── AI RECOMMENDATIONS ───────────────────

class AIRecommendation(Base, TimestampMixin):
    __tablename__ = "ai_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    recommendation_type: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    is_dismissed: Mapped[bool] = mapped_column(Boolean, default=False)
    extra_data: Mapped[Optional[dict]] = mapped_column("metadata", JSON)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))