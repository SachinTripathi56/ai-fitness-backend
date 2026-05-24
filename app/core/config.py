"""
Core configuration settings for AI Fitness Coach Platform.
Uses pydantic-settings for environment variable management.
AI powered by Google Gemini 2.5 Flash (FREE tier).
"""

from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import validator
import json


class Settings(BaseSettings):
    # App
    APP_NAME: str = "AI Fitness Coach Platform"
    APP_VERSION: str = "1.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "change-me-in-production-super-secret-key-32chars"

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    WORKERS: int = 4
    API_V1_STR: str = "/api/v1"

    # Database
# Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/ai_fitness_db"

    DATABASE_URL_SYNC: str = "postgresql://postgres:password@localhost:5432/ai_fitness_db"

    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"
    REDIS_CACHE_TTL: int = 3600

    # JWT
    JWT_SECRET_KEY: str = "change-me-jwt-secret-key-production"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ───────────────────────────────────────────────
    # Google Gemini AI  (FREE — get key at https://aistudio.google.com/app/apikey)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.5-flash"          # free, fast, smart
    GEMINI_TEMPERATURE: float = 0.7
    GEMINI_MAX_TOKENS: int = 4096
    # ───────────────────────────────────────────────

    # ChromaDB (local vector DB — no API key needed)
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    CHROMA_COLLECTION_FITNESS: str = "fitness_knowledge"
    CHROMA_COLLECTION_NUTRITION: str = "nutrition_knowledge"

    # File Storage
    STORAGE_BACKEND: str = "local"
    AWS_ACCESS_KEY_ID: Optional[str] = None
    AWS_SECRET_ACCESS_KEY: Optional[str] = None
    AWS_S3_BUCKET: Optional[str] = None
    AWS_REGION: str = "us-east-1"
    LOCAL_UPLOAD_DIR: str = "uploads"
    MAX_UPLOAD_SIZE_MB: int = 10

    # Email
    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    EMAILS_FROM_EMAIL: str = "noreply@aifitness.com"
    EMAILS_FROM_NAME: str = "AI Fitness Coach"

    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_AUTH_PER_MINUTE: int = 5

    # CORS
    ALLOWED_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
    ]

    # Admin defaults
    ADMIN_EMAIL: str = "admin@aifitness.com"
    ADMIN_PASSWORD: str = "changeme123!"

    @validator("ALLOWED_ORIGINS", pre=True)
    def parse_origins(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return [v]
        return v

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
