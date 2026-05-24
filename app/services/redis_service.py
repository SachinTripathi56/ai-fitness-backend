"""
Redis cache service for session storage, rate limiting, and API response caching.
"""

import json
from typing import Optional, Any
from functools import wraps
import redis.asyncio as aioredis
from app.core.config import settings
from loguru import logger


class RedisService:
    _client: Optional[aioredis.Redis] = None

    @classmethod
    async def get_client(cls) -> aioredis.Redis:
        if cls._client is None:
            cls._client = aioredis.from_url(
                settings.REDIS_URL,
                encoding="utf-8",
                decode_responses=True,
            )
        return cls._client

    @classmethod
    async def get(cls, key: str) -> Optional[Any]:
        try:
            client = await cls.get_client()
            value = await client.get(key)
            if value:
                return json.loads(value)
        except Exception as e:
            logger.warning(f"Redis GET error for key={key}: {e}")
        return None

    @classmethod
    async def set(cls, key: str, value: Any, ttl: int = None) -> bool:
        try:
            client = await cls.get_client()
            serialized = json.dumps(value, default=str)
            ttl = ttl or settings.REDIS_CACHE_TTL
            await client.setex(key, ttl, serialized)
            return True
        except Exception as e:
            logger.warning(f"Redis SET error for key={key}: {e}")
            return False

    @classmethod
    async def delete(cls, key: str) -> bool:
        try:
            client = await cls.get_client()
            await client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Redis DELETE error for key={key}: {e}")
            return False

    @classmethod
    async def delete_pattern(cls, pattern: str) -> int:
        try:
            client = await cls.get_client()
            keys = await client.keys(pattern)
            if keys:
                return await client.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Redis DELETE PATTERN error for pattern={pattern}: {e}")
            return 0

    @classmethod
    async def exists(cls, key: str) -> bool:
        try:
            client = await cls.get_client()
            return bool(await client.exists(key))
        except Exception as e:
            logger.warning(f"Redis EXISTS error for key={key}: {e}")
            return False

    @classmethod
    async def incr(cls, key: str, ttl: int = 60) -> int:
        try:
            client = await cls.get_client()
            value = await client.incr(key)
            if value == 1:
                await client.expire(key, ttl)
            return value
        except Exception as e:
            logger.warning(f"Redis INCR error for key={key}: {e}")
            return 0

    @classmethod
    async def store_refresh_token(cls, user_id: str, token: str, ttl_days: int = 7):
        key = f"refresh_token:{user_id}:{token[:16]}"
        await cls.set(key, {"user_id": user_id, "token": token}, ttl=ttl_days * 86400)

    @classmethod
    async def revoke_refresh_token(cls, user_id: str, token: str):
        key = f"refresh_token:{user_id}:{token[:16]}"
        await cls.delete(key)

    @classmethod
    async def cache_user_profile(cls, user_id: str, profile_data: dict):
        await cls.set(f"profile:{user_id}", profile_data, ttl=300)

    @classmethod
    async def get_cached_user_profile(cls, user_id: str) -> Optional[dict]:
        return await cls.get(f"profile:{user_id}")

    @classmethod
    async def invalidate_user_cache(cls, user_id: str):
        await cls.delete_pattern(f"*:{user_id}*")

    @classmethod
    async def close(cls):
        if cls._client:
            await cls._client.close()
            cls._client = None


redis_service = RedisService()
