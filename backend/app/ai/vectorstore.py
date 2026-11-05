"""Qdrant connections and persistence, separate from model configuration."""
from langchain_core.documents import Document
from langchain_qdrant import QdrantVectorStore

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


def get_vector_store() -> QdrantVectorStore:
    settings = get_settings()
    return QdrantVectorStore.from_existing_collection(
        embedding=get_embedding_model(),
        collection_name=settings.qdrant_collection_name,
        url=settings.qdrant_url,
    )
