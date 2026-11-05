from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import get_current_user
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_service import answer_query

router = APIRouter(tags=["Chat"])


@router.post("/query", response_model=ChatResponse)
async def query(data: ChatRequest, user: Annotated[User, Depends(get_current_user)]) -> ChatResponse:
    return await answer_query(data.query, user_id=str(user.id))
