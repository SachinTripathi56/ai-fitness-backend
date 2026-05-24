"""
Tests for authentication endpoints.
Run: pytest tests/ -v
"""

import pytest
from httpx import AsyncClient
from app.main import app


@pytest.mark.asyncio
async def test_register():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/v1/auth/register", json={
            "email": "test@example.com",
            "username": "testuser",
            "password": "Test1234!",
            "full_name": "Test User",
        })
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_login_invalid():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.post("/api/v1/auth/login", json={
            "email": "nobody@example.com",
            "password": "wrongpass",
        })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
