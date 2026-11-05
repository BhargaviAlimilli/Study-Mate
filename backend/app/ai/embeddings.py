import os
from langchain_qdrant import QdrantVectorStore
from openai import OpenAI
from langchain_huggingface import HuggingFaceEmbeddings

embedding_model = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)

client = OpenAI(
    api_key=os.getenv("ANTHROPIC_API_KEY"),
    base_url="https://api.anthropic.com/v1/")

vector_store = QdrantVectorStore(
    url=os.getenv("QDRANT_URL"),
    collection_name="study_mate"
)

def create_document_embeddings(docs):
    document_indexing = vector_store.from_documents(
    documents="",
    embedding=embedding_model)

    return document_indexing

def get_document_embeddings(query):
    vector_db = vector_store.from_existing_collection(
        embedding=embedding_model,
        collection_name='study_mate',
        url= os.getenv("QDRANT_URL")
    )
    serach_results = vector_db.similarity_search(query=query)

    return serach_results
