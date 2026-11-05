"""Upload indexing and chat retrieval entry points for application services."""
from uuid import uuid4

from langchain_core.documents import Document
from qdrant_client import models

from app.ai.vectorstore import add_documents, get_vector_store


def create_document_embeddings(
    docs: list[Document], *, user_id: str
) -> list[str]:
    """Index extracted, split document chunks; return their Qdrant IDs."""
    if not user_id.strip():
        raise ValueError("User ID is required.")
    if not docs or any(not isinstance(doc, Document) or not doc.page_content.strip() for doc in docs):
        raise ValueError("Provide a non-empty list of Document chunks with text.")

    # Copy metadata so caller-owned objects are not modified.
    scoped_docs = [
        Document(
            page_content=doc.page_content,
            metadata={**doc.metadata, "user_id": user_id},
        )
        for doc in docs
    ]
    ids = [str(uuid4()) for _ in scoped_docs]
    add_documents(scoped_docs, ids)
    return ids


def get_document_embeddings(
    query: str, *, user_id: str, k: int = 4
) -> list[Document]:
    """Return relevant stored chunks for chat, not the raw embedding vectors."""
    if not query.strip():
        raise ValueError("Query must not be empty.")
    if not user_id.strip():
        raise ValueError("User ID is required.")
    if not 1 <= k <= 20:
        raise ValueError("k must be between 1 and 20.")

    scope = models.Filter(must=[
        models.FieldCondition(key="metadata.user_id", match=models.MatchValue(value=user_id)),
    ])
    store = get_vector_store()
    try:
        return store.similarity_search(query=query.strip(), k=k, filter=scope)
    finally:
        store.client.close()
