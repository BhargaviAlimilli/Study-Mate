from datetime import datetime, timezone
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User
from app.models.progress import RevisionItem, LearningPreferences
from app.schemas.progress import PreferenceUpdate, RevisionUpdate, RevisionResponse
from app.schemas.quiz import QuizRequest, QuizResponse
from app.services.progress_service import get_preferences, progress_report, owned_revision, revision_response, sync_history

router = APIRouter(tags=["Learning progress"])
DB = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.get("/preferences", response_model=PreferenceUpdate)
def preferences(user: CurrentUser, db: DB):
    return get_preferences(user.id, db)


@router.put("/preferences", response_model=PreferenceUpdate)
def update_preferences(data: PreferenceUpdate, user: CurrentUser, db: DB):
    from app.ai.llm import ensure_provider_available
    ensure_provider_available(data.model_provider)
    record = db.get(LearningPreferences, user.id)
    if record is None:
        record = LearningPreferences(user_id=user.id)
        db.add(record)
    for name, value in data.model_dump().items():
        setattr(record, name, value)
    record.updated_at = datetime.now(timezone.utc)
    db.commit()
    return data


@router.get("/progress")
def progress(user: CurrentUser, db: DB):
    return progress_report(user.id, db)


@router.post("/revisions/sync")
def sync(user: CurrentUser, db: DB):
    sync_history(user.id, db)
    return {"status": "success"}


@router.get("/revisions", response_model=list[RevisionResponse])
def revisions(user: CurrentUser, db: DB, status: Literal["pending", "reviewed"] | None = None,
              limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
    query = select(RevisionItem).where(RevisionItem.user_id == user.id)
    if status:
        query = query.where(RevisionItem.status == status)
    return [revision_response(item) for item in db.scalars(query.order_by(RevisionItem.last_missed_at.desc(), RevisionItem.id).limit(limit).offset(offset))]


@router.patch("/revisions/{item_id}", response_model=RevisionResponse)
def review(item_id: UUID, data: RevisionUpdate, user: CurrentUser, db: DB):
    item = owned_revision(item_id, user.id, db)
    item.status = data.status
    item.reviewed_at = datetime.now(timezone.utc) if data.status == "reviewed" else None
    db.commit()
    return revision_response(item)


@router.post("/revisions/{item_id}/quiz", response_model=QuizResponse, status_code=201)
async def practise(item_id: UUID, user: CurrentUser, db: DB):
    from app.services.quiz_service import create_quiz
    item = owned_revision(item_id, user.id, db)
    return await create_quiz(QuizRequest(topic=item.topic), user.id, db)


@router.get("/progress/recommendations")
def recommendations(user: CurrentUser, db: DB):
    items = list(db.scalars(select(RevisionItem).where(RevisionItem.user_id == user.id, RevisionItem.status == "pending")))
    items.sort(key=lambda item: (len(item.missed_question_ids), item.last_missed_at), reverse=True)
    return {"recommendations": [{"revision": revision_response(item), "reason": f"Review the {len(item.missed_question_ids)} missed question(s) recorded in the latest relevant attempt."} for item in items[:10]],
            "note": "Prioritized by missed questions in the latest relevant attempt, then recency; not a mastery ranking."}
