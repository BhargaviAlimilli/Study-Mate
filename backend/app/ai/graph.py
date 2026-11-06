"""Durable chat graph. Run `python -m app.ai.graph` once to set up its tables."""
from contextlib import contextmanager
from typing import TypedDict

from fastapi import HTTPException
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.graph import StateGraph, START, END
from sqlalchemy.engine import make_url

from app.core.config import get_settings


class ChatState(TypedDict, total=False):
    user_id: str
    query: str
    history: list[dict]
    context: dict
    passages: list[dict]
    model_answer: dict | None
    response: dict
    requested_action: str
    action: str
    document_id: str | None
    ready_document_ids: list[str]
    preferences: dict
    evidence: list[dict]


def get_checkpoint_uri() -> str:
    return make_url(get_settings().database_url).set(drivername="postgresql").render_as_string(hide_password=False)


def setup_checkpointer() -> None:
    with PostgresSaver.from_conn_string(get_checkpoint_uri()) as saver:
        saver.setup()


@contextmanager
def checkpoint_session(thread_id: str):
    with PostgresSaver.from_conn_string(get_checkpoint_uri()) as saver:
        # Cross-process lock: two retries may not invoke the same graph at once.
        with saver.conn.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(hashtextextended(%s, 0)) AS locked", (thread_id,))
            if not cursor.fetchone()["locked"]:
                raise HTTPException(status_code=409, detail="This request is already running. Retry later.")
        try:
            yield saver
        finally:
            with saver.conn.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (thread_id,))


def build_chat_graph(saver, retrieve, generate, validate, route=None, quiz=None):
    graph = StateGraph(ChatState)
    graph.add_node("retrieve", retrieve)
    graph.add_node("generate", generate)
    graph.add_node("validate", validate)
    if route is not None:
        graph.add_node("route", route)
        graph.add_node("quiz", quiz)
        graph.add_edge(START, "route")
        graph.add_conditional_edges("route", lambda state: "quiz" if state["action"] == "quiz" else "retrieve")
        graph.add_edge("quiz", END)
    else:
        graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "generate")
    graph.add_edge("generate", "validate")
    graph.add_edge("validate", END)
    return graph.compile(checkpointer=saver)


if __name__ == "__main__":
    setup_checkpointer()
    print("PostgreSQL graph checkpoint tables are ready.")
