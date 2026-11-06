import asyncio
import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from starlette.concurrency import run_in_threadpool

from app.ai.quiz import generate_quiz
from app.ai.rag import get_document_embeddings
from app.ai.vectorstore import MissingCollectionError
from app.models.document import DocumentRecord
from app.models.quiz import Quiz, QuizQuestion, QuizAttempt, QuizAttemptAnswer
from app.schemas.quiz import QuizRequest, QuizResponse, GeneratedQuiz, QuizSubmission, AttemptResponse
from app.services.document_service import get_owned_document
from app.services.feedback_service import build_attempt_response

logger = logging.getLogger(__name__)


def collect_passages(data: QuizRequest, user_id: UUID, db: Session) -> list[dict]:
    if data.document_id is not None:
        document = get_owned_document(data.document_id, user_id, db)
        if document.status != "ready":
            raise HTTPException(status_code=409, detail="The selected document is not ready.")
    records = list(db.scalars(select(DocumentRecord).where(
        DocumentRecord.user_id == user_id, DocumentRecord.status == "ready"
    )))
    ready = {str(record.id): (record.filename, record.page_count) for record in records}
    db.commit()  # Release the read connection before embeddings and model work.
    if not ready:
        raise HTTPException(status_code=422, detail="Upload a document before generating a quiz.")
    kwargs = {"user_id": str(user_id), "k": 12, "document_ids": list(ready)}
    if data.document_id is not None:
        kwargs["document_id"] = str(data.document_id)
    try:
        chunks = get_document_embeddings(data.topic, **kwargs)
    except MissingCollectionError:
        chunks = []
    except Exception as exc:
        logger.error("Quiz retrieval failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Document search is unavailable.") from exc
    passages = []
    seen = set()
    for chunk in chunks:
        doc_id = str(chunk.metadata.get("document_id", ""))
        page = chunk.metadata.get("page")
        if doc_id not in ready or (data.document_id is not None and doc_id != str(data.document_id)):
            continue
        if not isinstance(page, int) or not 1 <= page <= ready[doc_id][1] or not chunk.page_content.strip():
            continue
        identity = (doc_id, page, chunk.page_content)
        if identity in seen:
            continue
        seen.add(identity)
        passages.append({"citation_id": len(passages) + 1, "document_id": doc_id,
                         "filename": ready[doc_id][0], "page": page, "text": chunk.page_content[:2000]})
    if not passages:
        raise HTTPException(status_code=422, detail="No usable study passages were found for this topic.")
    return passages


def persist_quiz(data: QuizRequest, user_id: UUID, generated: GeneratedQuiz, passages: list[dict], db: Session, quiz_id: UUID | None = None) -> QuizResponse:
    sources = {p["citation_id"]: p for p in passages}
    if any(citation not in sources for question in generated.questions for citation in question.citation_ids):
        raise HTTPException(status_code=502, detail="The generated quiz contained invalid evidence. Please try again.")
    quiz = Quiz(**({"id": quiz_id} if quiz_id else {}), user_id=user_id, document_id=data.document_id, topic=data.topic, question_count=5)
    quiz.questions = [QuizQuestion(
        position=position, question=question.question, options=question.options,
        correct_index=question.correct_index, explanation=question.explanation, topic=question.topic,
        evidence=[sources[i] for i in dict.fromkeys(question.citation_ids)],
    ) for position, question in enumerate(generated.questions, start=1)]
    try:
        db.add(quiz)
        db.commit()
        db.refresh(quiz)
        return QuizResponse.model_validate(quiz)
    except Exception as exc:
        db.rollback()
        logger.error("Quiz save failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="The quiz could not be saved.") from exc


async def create_quiz(data: QuizRequest, user_id: UUID, db: Session, quiz_id: UUID | None = None) -> QuizResponse:
    if quiz_id is not None:
        existing = await run_in_threadpool(db.scalar, select(Quiz).where(Quiz.id == quiz_id, Quiz.user_id == user_id))
        if existing is not None:
            return QuizResponse.model_validate(existing)
    from app.services.progress_service import get_preferences
    preferences = await run_in_threadpool(get_preferences, user_id, db)
    passages = await run_in_threadpool(collect_passages, data, user_id, db)
    try:
        generated = GeneratedQuiz.model_validate(await asyncio.wait_for(generate_quiz(data.topic, passages, provider=preferences.model_provider), timeout=90))
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Quiz generation timed out. Please try again.") from exc
    except Exception as exc:
        logger.error("Quiz generation failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="A valid quiz could not be generated. Please try again.") from exc
    if generated.status == "insufficient_context":
        raise HTTPException(status_code=422, detail="Your notes do not provide enough retrieved material for five questions on this topic.")
    return await run_in_threadpool(persist_quiz, data, user_id, generated, passages, db, quiz_id)


def get_owned_quiz(quiz_id: UUID, user_id: UUID, db: Session) -> Quiz:
    quiz = db.scalar(select(Quiz).where(Quiz.id == quiz_id, Quiz.user_id == user_id))
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    return quiz


def existing_submission(data: QuizSubmission, quiz_id: UUID, user_id: UUID, db: Session) -> QuizAttempt | None:
    saved = db.scalar(select(QuizAttempt).where(
        QuizAttempt.user_id == user_id, QuizAttempt.submission_id == data.submission_id
    ))
    if saved is not None:
        previous = {answer.question_id: answer.selected_index for answer in saved.answers}
        submitted = {answer.question_id: answer.selected_index for answer in data.answers}
        if saved.quiz_id != quiz_id or previous != submitted:
            raise HTTPException(status_code=409, detail="This submission ID has already been used with different answers or a different quiz.")
    return saved


def submit_quiz(quiz_id: UUID, data: QuizSubmission, user_id: UUID, db: Session) -> tuple[AttemptResponse, bool]:
    quiz = get_owned_quiz(quiz_id, user_id, db)
    saved = existing_submission(data, quiz_id, user_id, db)
    if saved is not None:
        return build_attempt_response(saved), False
    selections = {answer.question_id: answer.selected_index for answer in data.answers}
    if set(selections) != {question.id for question in quiz.questions}:
        raise HTTPException(status_code=422, detail="Answers must include every question from this quiz exactly once.")
    # Scoring is application logic: no model call and no client-supplied score.
    attempt = QuizAttempt(
        quiz_id=quiz_id, user_id=user_id, submission_id=data.submission_id,
        total=len(quiz.questions),
        score=sum(selections[question.id] == question.correct_index for question in quiz.questions),
    )
    attempt.answers = [QuizAttemptAnswer(
        question_id=question.id, position=question.position, selected_index=selections[question.id],
        correct_index=question.correct_index, is_correct=selections[question.id] == question.correct_index,
        question=question.question, options=list(question.options), explanation=question.explanation,
        topic=question.topic, evidence=question.evidence,
    ) for question in quiz.questions]
    try:
        db.add(attempt)
        db.flush()
        from app.services.progress_service import sync_attempt_revisions
        sync_attempt_revisions(attempt, db)
        db.commit()
        db.refresh(attempt)
        return build_attempt_response(attempt), True
    except IntegrityError as exc:
        db.rollback()
        # A concurrent retry may have saved this same submission first.
        saved = existing_submission(data, quiz_id, user_id, db)
        if saved is not None:
            return build_attempt_response(saved), False
        logger.error("Attempt constraint failure (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="The quiz attempt could not be saved.") from exc
    except Exception as exc:
        db.rollback()
        logger.error("Attempt save failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="The quiz attempt could not be saved.") from exc


def get_owned_attempt(quiz_id: UUID, attempt_id: UUID, user_id: UUID, db: Session) -> QuizAttempt:
    get_owned_quiz(quiz_id, user_id, db)
    attempt = db.scalar(select(QuizAttempt).where(
        QuizAttempt.id == attempt_id, QuizAttempt.quiz_id == quiz_id, QuizAttempt.user_id == user_id
    ))
    if attempt is None:
        raise HTTPException(status_code=404, detail="Quiz attempt not found.")
    return attempt
