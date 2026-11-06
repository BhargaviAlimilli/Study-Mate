import asyncio
import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.ai.quiz import generate_quiz
from app.ai.rag import get_document_embeddings
from app.ai.vectorstore import MissingCollectionError
from app.models.document import DocumentRecord
from app.models.quiz import Quiz, QuizQuestion
from app.schemas.quiz import QuizRequest, QuizResponse, GeneratedQuiz
from app.services.document_service import get_owned_document

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
    kwargs = {"user_id": str(user_id), "k": 12}
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


def persist_quiz(data: QuizRequest, user_id: UUID, generated: GeneratedQuiz, passages: list[dict], db: Session) -> QuizResponse:
    sources = {p["citation_id"]: p for p in passages}
    if any(citation not in sources for question in generated.questions for citation in question.citation_ids):
        raise HTTPException(status_code=502, detail="The generated quiz contained invalid evidence. Please try again.")
    quiz = Quiz(user_id=user_id, document_id=data.document_id, topic=data.topic, question_count=5)
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


async def create_quiz(data: QuizRequest, user_id: UUID, db: Session) -> QuizResponse:
    passages = await run_in_threadpool(collect_passages, data, user_id, db)
    try:
        generated = GeneratedQuiz.model_validate(await asyncio.wait_for(generate_quiz(data.topic, passages), timeout=90))
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Quiz generation timed out. Please try again.") from exc
    except Exception as exc:
        logger.error("Quiz generation failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=502, detail="A valid quiz could not be generated. Please try again.") from exc
    if generated.status == "insufficient_context":
        raise HTTPException(status_code=422, detail="Your notes do not provide enough retrieved material for five questions on this topic.")
    return await run_in_threadpool(persist_quiz, data, user_id, generated, passages, db)


def get_owned_quiz(quiz_id: UUID, user_id: UUID, db: Session) -> Quiz:
    quiz = db.scalar(select(Quiz).where(Quiz.id == quiz_id, Quiz.user_id == user_id))
    if quiz is None:
        raise HTTPException(status_code=404, detail="Quiz not found.")
    return quiz
