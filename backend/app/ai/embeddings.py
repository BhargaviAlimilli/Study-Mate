"""Shared local embedding model for document indexing and chat retrieval."""
from functools import lru_cache

from langchain_huggingface import HuggingFaceEmbeddings

from app.core.config import get_settings


@lru_cache(maxsize=1)
def get_embedding_model() -> HuggingFaceEmbeddings:
    # Load only on first use, not during FastAPI startup or module import.
    return HuggingFaceEmbeddings(
        model_name=get_settings().embedding_model_name,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
