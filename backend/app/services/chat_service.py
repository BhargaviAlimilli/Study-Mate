import asyncio
import logging

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool

from app.ai.llm import generate_reply
from app.ai.rag import get_document_embeddings
from app.ai.vectorstore import MissingCollectionError
from app.schemas.chat import ChatResponse

logger = logging.getLogger(__name__)


def insufficient_context() -> ChatResponse:
    return ChatResponse(
        status="insufficient_context",
        answer="I could not find relevant passages in your uploaded materials. Please upload a text PDF or ask a more specific question about your notes.",
    )


async def answer_query(query: str, user_id: str) -> ChatResponse:
    try:
        # Embedding and Qdrant clients are synchronous; keep them off the event loop.
        docs = await run_in_threadpool(get_document_embeddings, query, user_id=user_id, k=4)
    except MissingCollectionError:
        return insufficient_context()
    except Exception as exc:
        logger.error("Chat retrieval failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Document search is unavailable. Please try again later.") from exc
    if not docs:
        return insufficient_context()

    passages = [
        {"citation_id": i, "text": doc.page_content[:2000]}
        for i, doc in enumerate(docs, start=1)
    ]
    valid_ids = {passage["citation_id"] for passage in passages}
    try:
        result = await asyncio.wait_for(generate_reply(query, passages), timeout=60)
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="The tutor took too long to respond. Please try again.") from exc
    except Exception as exc:
        logger.error("Tutor generation failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="The tutor is unavailable. Please try again later.") from exc

    if result.status != "answered":
        return ChatResponse(status=result.status, answer=result.answer)
    ids = list(dict.fromkeys(result.citation_ids))
    if not ids or any(i not in valid_ids for i in ids):
        # Never return invented source references as a grounded answer.
        return insufficient_context()
    return ChatResponse(status="answered", answer=result.answer)
