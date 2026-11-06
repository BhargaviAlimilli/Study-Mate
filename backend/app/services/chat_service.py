import asyncio
import logging
from uuid import UUID

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.ai.llm import generate_reply
from app.ai.rag import get_document_embeddings
from app.ai.vectorstore import MissingCollectionError
from app.ai.graph import checkpoint_session, build_chat_graph
from app.ai.memory import ConversationContext, load_context, save_turn
from app.schemas.chat import ChatResponse, TutorAnswer

logger = logging.getLogger(__name__)


def insufficient_context() -> ChatResponse:
    return ChatResponse(
        status="insufficient_context",
        answer="I could not find relevant passages in your uploaded materials. Please upload a text PDF or ask a more specific question about your notes.",
    )


def retrieve_node(state):
    previous = [message["content"][:500] for message in state["history"] if message["role"] == "user"][-3:]
    query = state["query"]
    if previous:
        query += "\nRecent study questions:\n" + "\n".join(previous)
    try:
        docs = get_document_embeddings(query, user_id=state["user_id"], k=4)
    except MissingCollectionError:
        docs = []
    except Exception as exc:
        logger.error("Chat retrieval failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Document search is unavailable. Please try again later.") from exc
    return {"passages": [{"citation_id": i, "text": doc.page_content[:2000]} for i, doc in enumerate(docs, start=1)]}


def generate_node(state):
    if not state["passages"]:
        return {"model_answer": None}
    async def call():
        return await asyncio.wait_for(generate_reply(state["query"], state["passages"], history=state["history"]), timeout=60)
    try:
        result = asyncio.run(call())
        return {"model_answer": result.model_dump()}
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="The tutor took too long to respond. Please try again.") from exc
    except Exception as exc:
        logger.error("Tutor generation failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="The tutor is unavailable. Please try again later.") from exc


def validate_node(state):
    if state["model_answer"] is None:
        response = insufficient_context()
    else:
        result = TutorAnswer.model_validate(state["model_answer"])
        valid_ids = {passage["citation_id"] for passage in state["passages"]}
        if result.status == "answered" and (not result.citation_ids or any(i not in valid_ids for i in result.citation_ids)):
            response = insufficient_context()
        else:
            response = ChatResponse(status=result.status, answer=result.answer)
    return {"response": response.model_dump(mode="json")}


def execute_run(db: Session, user_id: UUID, request_id: UUID, query: str | None, conversation_id: UUID | None) -> ChatResponse:
    # Namespace the server-controlled graph thread by the authenticated owner.
    thread_id = f"user:{user_id}:request:{request_id}"
    config = {"configurable": {"thread_id": thread_id}}
    try:
        with checkpoint_session(thread_id) as saver:
            graph = build_chat_graph(saver, retrieve_node, generate_node, validate_node)
            snapshot = graph.get_state(config)
            if snapshot.values:
                if query is not None and query != snapshot.values["query"]:
                    raise HTTPException(status_code=409, detail="This request ID belongs to a different question.")
                if conversation_id is not None and str(conversation_id) != snapshot.values["context"]["id"]:
                    raise HTTPException(status_code=409, detail="This request ID belongs to a different conversation.")
                # Release authentication's read transaction before model work.
                db.commit()
                state = graph.invoke(None, config, durability="sync") if snapshot.next else snapshot.values
            else:
                if query is None:
                    raise HTTPException(status_code=404, detail="Chat run not found.")
                context = load_context(db, user_id, conversation_id)
                initial = {
                    "user_id": str(user_id), "query": query, "history": context.history,
                    "context": {"id": str(context.id), "version": context.version, "is_new": context.is_new},
                }
                state = graph.invoke(initial, config, durability="sync")
            data = state["context"]
            context = ConversationContext(UUID(data["id"]), data["version"], state["history"], data["is_new"])
            response = ChatResponse.model_validate(state["response"])
            # Request IDs make this safe if a crash occurred after committing messages.
            save_turn(db, user_id, context, state["query"], response, request_id=request_id)
            response.conversation_id = context.id
            response.request_id = request_id
            return response
    except HTTPException as exc:
        db.rollback()
        raise HTTPException(status_code=exc.status_code, detail={"message": exc.detail, "request_id": str(request_id)}) from exc
    except Exception as exc:
        db.rollback()
        logger.error("Checkpointed chat failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail={
            "message": "Chat processing or storage is unavailable. Retry this request ID or use the resume endpoint.",
            "request_id": str(request_id),
        }) from exc


async def continue_conversation(query: str, user_id: UUID, conversation_id: UUID | None, db: Session, request_id: UUID) -> ChatResponse:
    # The synchronous graph, saver, database, and embedding calls run in a worker thread.
    return await run_in_threadpool(execute_run, db, user_id, request_id, query, conversation_id)


async def resume_conversation(request_id: UUID, user_id: UUID, db: Session) -> ChatResponse:
    return await run_in_threadpool(execute_run, db, user_id, request_id, None, None)
