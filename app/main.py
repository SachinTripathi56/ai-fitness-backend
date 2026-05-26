"""
AI Fitness Coach Platform — FastAPI Application Entry Point
Backend APIs are developed separately using FastAPI.
Frontend is built with React + Lovable AI and consumes these REST APIs.
"""

import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from loguru import logger
import os

from app.core.config import settings
from app.database.session import init_db
from app.services.redis_service import redis_service
from app.api.v1.router import api_router


# ─── LIFESPAN ───

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 Starting {settings.APP_NAME} v{settings.APP_VERSION}")
    await init_db()
    logger.info("✅ Database ready")
    yield
    await redis_service.close()
    logger.info("👋 Shutdown complete")


# ─── RATE LIMITER ───

limiter = Limiter(key_func=get_remote_address)


# ─── APP ───

app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
## AI Fitness Coach Platform API

Production-grade backend for the AI Fitness Coach Platform.

### Features
- 🔐 JWT Authentication with refresh token rotation
- 🏋️ AI-powered personalized workout plan generation
- 🥗 AI-powered diet & meal plan generation  
- 🤖 Conversational AI fitness coach
- 📅 Smart adaptive schedule planner
- 📊 Progress tracking & analytics
- 💡 AI-generated recommendations
- 👑 Admin dashboard

### Tech Stack
FastAPI · PostgreSQL · SQLAlchemy · Redis · Google Gemini 2.5 Flash (FREE) · ChromaDB
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# ─── MIDDLEWARE ───

class CleanDoubleSlashesMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope.get("path", "")
            if "//" in path:
                import re
                scope["path"] = re.sub(r"/+", "/", path)
        await self.app(scope, receive, send)

app.add_middleware(CleanDoubleSlashesMiddleware)


origins = list(set(settings.ALLOWED_ORIGINS + [
    "http://localhost:8080",
    "http://127.0.0.1:8080",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://ai-fitness-backend-6v9k.onrender.com",
    "https://fit-ai-companion-71.vercel.app",
    "https://fit-ai-companion-71.lovable.app",
]))

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = round((time.time() - start) * 1000, 2)
    logger.info(f"{request.method} {request.url.path} → {response.status_code} [{duration}ms]")
    return response

@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


# ─── STATIC FILES ───

os.makedirs("uploads", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# ─── ROUTES ───

app.include_router(api_router, prefix="/api")


# ─── HEALTH ───

@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }

@app.get("/", tags=["Root"])
async def root():
    return {
        "message": f"Welcome to {settings.APP_NAME} API",
        "docs": "/docs",
        "version": settings.APP_VERSION,
    }


# ─── GLOBAL EXCEPTION HANDLER ───

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc} | Path: {request.url.path}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "success": False},
    )
