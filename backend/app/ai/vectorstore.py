"""Qdrant connections and persistence, separate from model configuration."""
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore
from qdrant_client import QdrantClient, models

from app.ai.embeddings import get_embedding_model
from app.core.config import get_settings


def add_documents(documents: list[Document], ids: list[str]) -> None:
    settings = get_settings()
    # Creates the collection on first upload; appends on subsequent uploads.
    # Do not force_recreate: that would erase previously uploaded chunks.
    store = QdrantVectorStore.from_documents(
        documents=documents,
        embedding=get_embedding_model(),
        ids=ids,
        url=settings.qdrant_url,
        collection_name=settings.qdrant_collection_name,
    )
    store.client.close()


class MissingCollectionError(Exception):
    pass


def delete_document_vectors(document_id: str, user_id: str) -> None:
    """Compensate for partially indexed uploads without touching other documents."""
    settings = get_settings()
    client = QdrantClient(url=settings.qdrant_url, timeout=15)
    try:
        if client.collection_exists(settings.qdrant_collection_name):
            client.delete(
                collection_name=settings.qdrant_collection_name,
                points_selector=models.FilterSelector(filter=models.Filter(must=[
                    models.FieldCondition(key="metadata.document_id", match=models.MatchValue(value=document_id)),
                    models.FieldCondition(key="metadata.user_id", match=models.MatchValue(value=user_id)),
                ])),
                wait=True,
            )
    finally:
        client.close()


def get_vector_store() -> QdrantVectorStore:
    settings = get_settings()
    client = QdrantClient(url=settings.qdrant_url, timeout=15)
    try:
        if not client.collection_exists(settings.qdrant_collection_name):
            raise MissingCollectionError()
        return QdrantVectorStore(
            client=client, embedding=get_embedding_model(),
            collection_name=settings.qdrant_collection_name,
        )
    except Exception:
        client.close()
        raise
