from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID, uuid4
from fastapi import HTTPException
from sqlalchemy import select, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session
from app.models.progress import RevisionItem, LearningPreferences
from app.models.quiz import Quiz, QuizQuestion, QuizAttempt
from app.schemas.progress import PreferenceUpdate, RevisionResponse
from app.services.feedback_service import review_sources


def topic_key(value: str) -> str:
    return " ".join(value.split()).casefold()


def sync_attempt_revisions(attempt: QuizAttempt, db: Session) -> None:
    groups = defaultdict(list)
    for answer in attempt.answers:
        if not answer.is_correct:
            groups[topic_key(answer.topic)].append(answer)
    for key, answers in groups.items():
        values = dict(id=uuid4(), user_id=attempt.user_id, topic=answers[0].topic,
            topic_key=key, status="pending", attempt_id=attempt.id,
            evidence=[p for a in answers for p in a.evidence],
            missed_question_ids=[str(a.question_id) for a in answers],
            last_missed_at=attempt.submitted_at, reviewed_at=None)
        statement = insert(RevisionItem).values(**values)
        db.execute(statement.on_conflict_do_update(
            constraint="uq_revision_user_topic",
            set_={k: v for k, v in values.items() if k not in {"id", "user_id", "topic_key"}},
            where=RevisionItem.last_missed_at < attempt.submitted_at))


def sync_history(user_id: UUID, db: Session) -> None:
    for attempt in db.scalars(select(QuizAttempt).where(QuizAttempt.user_id == user_id).order_by(QuizAttempt.submitted_at)):
        sync_attempt_revisions(attempt, db)
    db.commit()


def revision_response(item: RevisionItem) -> RevisionResponse:
    return RevisionResponse(id=item.id, topic=item.topic, status=item.status, attempt_id=item.attempt_id,
        missed_question_ids=item.missed_question_ids, last_missed_at=item.last_missed_at,
        reviewed_at=item.reviewed_at, sources=review_sources(item.evidence))


def owned_revision(item_id: UUID, user_id: UUID, db: Session) -> RevisionItem:
    item = db.scalar(select(RevisionItem).where(RevisionItem.id == item_id, RevisionItem.user_id == user_id))
    if item is None:
        raise HTTPException(404, "Revision topic not found.")
    return item


def get_preferences(user_id: UUID, db: Session) -> PreferenceUpdate:
    record = db.get(LearningPreferences, user_id)
    return PreferenceUpdate(detail=record.detail, comparison_language=record.comparison_language,
                            model_provider=record.model_provider) if record else PreferenceUpdate()


def progress_report(user_id: UUID, db: Session) -> dict:
    topics = {}
    for label in db.scalars(select(QuizQuestion.topic).join(Quiz).where(Quiz.user_id == user_id)):
        topics.setdefault(topic_key(label), {"topic": label, "correct": 0, "assessed_answers": 0, "attempts": []})
    attempts = list(db.scalars(select(QuizAttempt).where(QuizAttempt.user_id == user_id).order_by(QuizAttempt.submitted_at, QuizAttempt.id)))
    for attempt in attempts:
        per_attempt = defaultdict(list)
        for answer in attempt.answers:
            key = topic_key(answer.topic)
            entry = topics.setdefault(key, {"topic": answer.topic, "correct": 0, "assessed_answers": 0, "attempts": []})
            entry["correct"] += int(answer.is_correct)
            entry["assessed_answers"] += 1
            per_attempt[key].append(answer.is_correct)
        for key, flags in per_attempt.items():
            topics[key]["attempts"].append({"attempt_id": str(attempt.id), "correct": sum(flags), "total": len(flags), "submitted_at": attempt.submitted_at})
    pending = {item.topic_key for item in db.scalars(select(RevisionItem).where(RevisionItem.user_id == user_id, RevisionItem.status == "pending"))}
    for key, entry in topics.items():
        history = entry["attempts"]
        entry["status"] = "not_assessed" if not history else "needs_review" if key in pending else "doing_well" if history[-1]["correct"] == history[-1]["total"] else "practising"
        entry["trend"] = "not_enough_data"
        if len(history) >= 2:
            previous, latest = history[-2:]
            delta = latest["correct"] / latest["total"] - previous["correct"] / previous["total"]
            entry["trend"] = "improving" if delta > 0 else "declining" if delta < 0 else "unchanged"
        entry["accuracy"] = round(entry["correct"] / entry["assessed_answers"] * 100, 2) if history else None
    return {"attempt_count": len(attempts), "topics": list(topics.values()),
        "assessment_note": "Accuracy and trends describe the recorded questions, not a definitive mastery score. Reviewed topics may still need further practice."}
