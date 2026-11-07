import asyncio
import logging
import re
from uuid import UUID, uuid5, NAMESPACE_URL

from fastapi import HTTPException
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.document import DocumentRecord
from app.services.progress_service import get_preferences
from app.services.document_service import get_owned_document
from app.services.feedback_service import review_sources

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
        kwargs = {"user_id": state["user_id"], "k": 4}
        if "ready_document_ids" in state:
            kwargs["document_ids"] = state["ready_document_ids"]
        if state.get("document_id"):
            kwargs["document_id"] = state["document_id"]
        docs = get_document_embeddings(query, **kwargs)
    except MissingCollectionError:
        docs = []
    except Exception as exc:
        logger.error("Chat retrieval failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Document search is unavailable. Please try again later.") from exc
    if "ready_document_ids" in state:
        docs = [doc for doc in docs if str(doc.metadata.get("document_id")) in state["ready_document_ids"]]
    return {"passages": [{"citation_id": i, "text": doc.page_content[:2000]} for i, doc in enumerate(docs, start=1)],
            "evidence": [{"citation_id": i, **doc.metadata, "text": doc.page_content[:2000]} for i, doc in enumerate(docs, start=1)]}


def generate_node(state):
    if not state["passages"]:
        return {"model_answer": None}
    async def call():
        return await asyncio.wait_for(generate_reply(state["query"], state["passages"], history=state["history"], preferences=state.get("preferences", {}), action=state.get("action", "answer")), timeout=60)
    try:
        result = asyncio.run(call())
        return {"model_answer": result.model_dump()}
    except HTTPException:
        raise
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


def execute_run(db: Session, user_id: UUID, request_id: UUID, query: str | None, conversation_id: UUID | None, action: str = "auto", document_id: UUID | None = None) -> ChatResponse:
    # Namespace the server-controlled graph thread by the authenticated owner.
    thread_id = f"user:{user_id}:request:{request_id}"
    config = {"configurable": {"thread_id": thread_id}}
    try:
        with checkpoint_session(thread_id) as saver:
            def quiz_node(state):
                from app.schemas.quiz import QuizRequest
                from app.services.quiz_service import create_quiz
                quiz_id = uuid5(NAMESPACE_URL, f"quiz:{user_id}:{request_id}")
                saved = asyncio.run(create_quiz(QuizRequest(topic=state["query"][:200], document_id=state.get("document_id")), user_id, db, quiz_id=quiz_id))
                return {"response": ChatResponse(status="quiz_ready", answer="Your five-question practice quiz is ready.", quiz=saved).model_dump(mode="json"), "evidence": []}
            graph = build_chat_graph(saver, retrieve_node, generate_node, validate_node, route_node, quiz_node)
            snapshot = graph.get_state(config)
            if snapshot.values:
                if query is not None and query != snapshot.values["query"]:
                    raise HTTPException(status_code=409, detail="This request ID belongs to a different question.")
                if conversation_id is not None and str(conversation_id) != snapshot.values["context"]["id"]:
                    raise HTTPException(status_code=409, detail="This request ID belongs to a different conversation.")
                if query is not None and (action != snapshot.values.get("requested_action", "auto") or (str(document_id) if document_id else None) != snapshot.values.get("document_id")):
                    raise HTTPException(status_code=409, detail="This request ID belongs to different action or document settings.")
                # Release authentication's read transaction before model work.
                db.commit()
                state = graph.invoke(None, config, durability="sync") if snapshot.next else snapshot.values
            else:
                if query is None:
                    raise HTTPException(status_code=404, detail="Chat run not found.")
                if document_id:
                    document = get_owned_document(document_id, user_id, db)
                    if document.status != "ready":
                        raise HTTPException(status_code=409, detail="The selected document is not ready.")
                ready = [str(value) for value in db.scalars(select(DocumentRecord.id).where(DocumentRecord.user_id == user_id, DocumentRecord.status == "ready"))]
                preferences = get_preferences(user_id, db).model_dump()
                context = load_context(db, user_id, conversation_id)
                initial = {
                    "user_id": str(user_id), "query": query, "history": context.history,
                    "ready_document_ids": ready, "preferences": preferences,
                    "requested_action": action, "document_id": str(document_id) if document_id else None,
                    "context": {"id": str(context.id), "version": context.version, "is_new": context.is_new},
                }
                state = graph.invoke(initial, config, durability="sync")
            data = state["context"]
            context = ConversationContext(UUID(data["id"]), data["version"], state["history"], data["is_new"])
            response = ChatResponse.model_validate(state["response"])
            # Request IDs make this safe if a crash occurred after committing messages.
            ids = set((state.get("model_answer") or {}).get("citation_ids", []))
            evidence = review_sources([item for item in state.get("evidence", []) if item.get("citation_id") in ids]) if response.status == "answered" else []
            save_turn(db, user_id, context, state["query"], response, request_id=request_id,
                sources=[source.model_dump(mode="json") for source in evidence])
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


async def continue_conversation(query: str, user_id: UUID, conversation_id: UUID | None, db: Session, request_id: UUID, action: str = "auto", document_id: UUID | None = None) -> ChatResponse:
    # The synchronous graph, saver, database, and embedding calls run in a worker thread.
    return await run_in_threadpool(execute_run, db, user_id, request_id, query, conversation_id, action, document_id)


async def resume_conversation(request_id: UUID, user_id: UUID, db: Session) -> ChatResponse:
    return await run_in_threadpool(execute_run, db, user_id, request_id, None, None)


def route_node(state):
    action = state.get("requested_action", "auto")
    if action == "auto":
        query = state["query"].strip().lower()
        if not re.match(r"^(?:explain|what is|what does|how does|describe)\b", query) and re.search(r"\b(?:quiz|test)\s+me\b|\b(?:generate|create|conduct|give me|make|start|ask me|want)\b.*\b(?:quiz|practice questions|mcqs?)\b", query):
            action = "quiz"
        elif re.search(r"^(?:(?:please|can you|could you|would you)\s+)?(?:summarize|summarise|summary of|give me a summary|provide a summary)\b", query):
            action = "summarize"
        else:
            action = "answer"
    return {"action": action}


def get_run_evidence(request_id: UUID, user_id: UUID, db: Session):
    from app.models.conversation import Message, Conversation
    saved = db.scalar(select(Message).join(Conversation).where(Conversation.user_id == user_id, Message.request_id == request_id, Message.role == "assistant"))
    if saved is not None and saved.sources:
        owned_ids = {str(value) for value in db.scalars(select(DocumentRecord.id).where(DocumentRecord.user_id == user_id, DocumentRecord.status == "ready"))}
        return review_sources([source for source in saved.sources if str(source.get("document_id")) in owned_ids])
    config = {"configurable": {"thread_id": f"user:{user_id}:request:{request_id}"}}
    with checkpoint_session(config["configurable"]["thread_id"]) as saver:
        # Graph topology does not affect reading state.
        graph = build_chat_graph(saver, retrieve_node, generate_node, validate_node)
        snapshot = graph.get_state(config)
        if not snapshot.values:
            raise HTTPException(404, "Chat run not found.")
        result = snapshot.values.get("model_answer") or {}
        ids = set(result.get("citation_ids", []))
        if snapshot.values.get("response", {}).get("status") != "answered":
            return []
        evidence = [item for item in snapshot.values.get("evidence", []) if item.get("citation_id") in ids]
        owned_ids = {str(value) for value in db.scalars(select(DocumentRecord.id).where(DocumentRecord.user_id == user_id, DocumentRecord.status == "ready"))}
        return review_sources([item for item in evidence if str(item.get("document_id")) in owned_ids])
