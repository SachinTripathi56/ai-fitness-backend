"""
Central API router.
All routes mounted at /api (no /v1) to match frontend endpoint registry.
"""

from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, workouts, diet, chat, progress, schedules, admin, dashboard

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(workouts.router)
api_router.include_router(diet.router)
api_router.include_router(chat.router)
api_router.include_router(progress.router)
api_router.include_router(schedules.router)
api_router.include_router(admin.router)
api_router.include_router(dashboard.router)