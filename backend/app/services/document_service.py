import logging
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ai.rag import create_document_embeddings
from app.core.config import get_settings
from app.schemas.document import DocumentUploadResponse
from app.utils.pdf_parser import extract_pdf_pages

logger = logging.getLogger(__name__)


def process_document_upload(file: UploadFile, user_id: str) -> DocumentUploadResponse:
    try:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=415, detail="Only PDF files are supported.")
        if file.content_type not in {"application/pdf", "application/octet-stream"}:
            raise HTTPException(status_code=415, detail="Upload a PDF file with a valid content type.")
        content = file.file.read(get_settings().max_upload_bytes + 1)
        if not content:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
        if len(content) > get_settings().max_upload_bytes:
            raise HTTPException(status_code=413, detail="The PDF exceeds the upload size limit (default: 10 MiB).")
        if not content.startswith(b"%PDF-"):
            raise HTTPException(status_code=400, detail="The file content is not a PDF.")
        try:
            pages = extract_pdf_pages(content)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        document_id = uuid4()
        for page in pages:
            page.metadata.update({"document_id": str(document_id), "filename": file.filename})
        chunks = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        ).split_documents(pages)
        for index, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = index
        try:
            ids = create_document_embeddings(chunks, user_id=user_id)
        except Exception as exc:
            # Do not return provider errors, credentials, or uploaded text to clients.
            logger.error("Document indexing failed (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=503, detail="Document embedding or storage failed. Please try again later."
            ) from exc
        return DocumentUploadResponse(document_id=document_id, chunks_stored=len(ids))
    finally:
        file.file.close()
