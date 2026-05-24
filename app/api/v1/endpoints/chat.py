"""
Chat endpoints — prefix: /chat
Matches frontend: /api/chat/message, /api/chat/history,
                  /api/chat/sessions/{id}, /api/chat/suggestions
"""

from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.session import get_db
from app.models.models import User, UserProfile, ChatSession, ChatMessage
from app.schemas.schemas import (
    ChatMessageCreate, ChatResponse, ChatSessionResponse,
    ChatMessageResponse, BaseResponse,
)
from app.core.dependencies import get_current_user
from app.services.ai_service import ai_service
from loguru import logger

router = APIRouter(prefix="/chat", tags=["AI Chat"])


@router.post("/message", response_model=ChatResponse)
async def send_message(
    payload: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Get or create session
    if payload.session_id:
        result = await db.execute(
            select(ChatSession).where(ChatSession.id == payload.session_id, ChatSession.user_id == current_user.id)
        )
        session = result.scalar_one_or_none()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
    else:
        title = payload.message[:50] + ("..." if len(payload.message) > 50 else "")
        session = ChatSession(user_id=current_user.id, title=title)
        db.add(session)
        await db.flush()

    # Load history
    result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session.id).order_by(ChatMessage.created_at.asc())
    )
    history = [{"role": m.role, "content": m.content} for m in result.scalars().all()]

    # Get profile
    profile_result = await db.execute(select(UserProfile).where(UserProfile.user_id == current_user.id))
    profile = profile_result.scalar_one_or_none()
    profile_dict = {}
    if profile:
        profile_dict = {
            "age": profile.age,
            "fitness_goal": profile.fitness_goal.value if profile.fitness_goal else None,
            "diet_type": profile.diet_type.value if profile.diet_type else None,
            "workout_experience": profile.workout_experience.value if profile.workout_experience else None,
            "weight_kg": profile.weight_kg,
            "allergies": profile.allergies or [],
        }

    # Save user message
    user_msg = ChatMessage(session_id=session.id, role="user", content=payload.message)
    db.add(user_msg)
    await db.flush()

    # Get AI response
    ai_response = await ai_service.chat(
        user_message=payload.message,
        conversation_history=history,
        user_profile=profile_dict,
    )

    ai_msg = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=ai_response["reply"],
        tokens_used=ai_response.get("tokens_used"),
    )
    db.add(ai_msg)
    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(ai_msg)

    return ChatResponse(
        session_id=session.id,
        message=ChatMessageResponse.model_validate(user_msg),
        reply=ChatMessageResponse.model_validate(ai_msg),
        suggested_prompts=ai_response.get("suggested_prompts"),
    )


@router.get("/history", response_model=List[ChatSessionResponse])
async def get_chat_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all chat sessions — mapped from frontend /api/chat/history"""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == current_user.id, ChatSession.is_active == True)
        .order_by(ChatSession.created_at.desc())
    )
    return result.scalars().all()


@router.get("/sessions/{session_id}", response_model=List[ChatMessageResponse])
async def get_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get messages for a specific session."""
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Session not found")

    result = await db.execute(
        select(ChatMessage).where(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc())
    )
    return result.scalars().all()


@router.get("/suggestions", response_model=List[str])
async def get_suggestions(current_user: User = Depends(get_current_user)):
    """Suggested prompts for the chat UI."""
    return [
        "Give me a home workout for today",
        "What should I eat after my workout?",
        "How much protein do I need daily?",
        "I missed my workout, what should I do?",
        "Give me a 500-calorie breakfast idea",
        "How can I improve my sleep quality?",
        "Create a high-protein vegetarian meal",
        "What's the best time to work out for fat loss?",
    ]


@router.delete("/sessions/{session_id}", response_model=BaseResponse)
async def delete_session(
    session_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == current_user.id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.is_active = False
    await db.commit()
    return BaseResponse(message="Session deleted")
