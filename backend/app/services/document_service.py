import logging
import hashlib
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from fastapi import HTTPException, UploadFile
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.ai.rag import create_document_embeddings
from app.ai.vectorstore import delete_document_vectors
from app.models.document import DocumentRecord
from app.core.config import get_settings
from app.schemas.document import DocumentUploadResponse
from app.utils.pdf_parser import extract_pdf_pages

logger = logging.getLogger(__name__)


def process_document_upload(file: UploadFile, user_id: str, db: Session, *, queued: bool = False, expected_job_id: str | None = None) -> DocumentUploadResponse:
    lock_connection = None
    lock_identity = None
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

        filename = file.filename.replace("\\", "/").rsplit("/", 1)[-1]
        if not filename or len(filename) > 255:
            raise HTTPException(status_code=400, detail="The filename must contain 1 to 255 characters.")
        digest = hashlib.sha256(content).hexdigest()
        identity = str(user_id) + ":" + digest
        lock_connection = db.get_bind().connect()
        if expected_job_id:
            lock_connection.execute(text("SELECT pg_advisory_lock(hashtextextended(:identity, 0))"), {"identity": identity})
            locked = True
        else:
            locked = lock_connection.scalar(text("SELECT pg_try_advisory_lock(hashtextextended(:identity, 0))"), {"identity": identity})
        lock_connection.commit()
        if not locked:
            raise HTTPException(status_code=409, detail="This document is already being processed. Retry later.")
        lock_identity = identity
        existing = db.scalar(select(DocumentRecord).where(
            DocumentRecord.user_id == UUID(user_id), DocumentRecord.content_hash == digest))
        if expected_job_id and (existing is None or existing.ingestion_job_id != expected_job_id):
            return DocumentUploadResponse(document_id=existing.id if existing else uuid4(), chunks_stored=0, message="Superseded ingestion job skipped.")
        if existing and existing.status == "ready":
            db.commit()
            return DocumentUploadResponse(document_id=existing.id, chunks_stored=existing.chunks_stored,
                message="This document is already uploaded and indexed.")
        document_id = existing.id if existing else uuid4()
        if existing:
            filename = existing.filename
        queue = None
        if queued:
            from app.workers.document_worker import ingestion_queue, job_is_active
            try:
                queue = ingestion_queue()
                # Holding this lock proves no worker is currently indexing this hash.
                # A processing row with no lock holder is an abandoned execution.
                if existing and existing.status != "processing" and job_is_active(queue, existing.ingestion_job_id):
                    if existing.status == "failed":
                        existing.status = "queued"
                        db.commit()
                    return DocumentUploadResponse(document_id=existing.id, chunks_stored=0, status="queued", message="Document ingestion is already queued or running.")
            except Exception as exc:
                raise HTTPException(503, "Document queue is unavailable. Start Redis and try again.") from exc
        record = existing or DocumentRecord(
            id=document_id, user_id=UUID(user_id), filename=filename,
            pdf_content=content, size_bytes=len(content), content_hash=digest,
            embedding_model=get_settings().embedding_model_name,
            page_count=pages[0].metadata["total_pages"], chunks_stored=0, status="processing",
        )
        record.status = "queued" if queued else "processing"
        if queued:
            record.ingestion_job_id = uuid4().hex
        record.chunks_stored = 0
        record.embedding_model = get_settings().embedding_model_name
        try:
            db.add(record)
            db.commit()
        except Exception as exc:
            db.rollback()
            logger.error("Document persistence failed (%s)", type(exc).__name__)
            raise HTTPException(status_code=503, detail="Document storage is unavailable.") from exc
        if queued:
            from rq import Retry
            from rq.job import Callback
            from app.workers.document_worker import ingestion_failed
            try:
                queue.enqueue_call("app.workers.document_worker.ingest_document", args=(str(record.id), user_id, record.ingestion_job_id),
                    job_id=record.ingestion_job_id, timeout=get_settings().ingestion_timeout_seconds,
                    retry=Retry(max=2, interval=[10, 30]), result_ttl=86400, failure_ttl=604800,
                    on_failure=Callback(ingestion_failed, timeout=30),
                    description="Index study document")
            except Exception as exc:
                record.status = "failed"
                db.commit()
                logger.error("Ingestion enqueue failed (%s)", type(exc).__name__)
                raise HTTPException(503, "Document was saved, but ingestion could not be queued. Retry this upload after Redis is available.") from exc
            return DocumentUploadResponse(document_id=document_id, chunks_stored=0, status="queued", message="Document saved and queued for processing.")
        for page in pages:
            page.metadata.update({"document_id": str(document_id), "filename": filename})
        chunks = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200
        ).split_documents(pages)
        for index, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = index
        try:
            if existing:
                delete_document_vectors(str(document_id), user_id)
            ids = create_document_embeddings(chunks, user_id=user_id)
            record.chunks_stored = len(ids)
            record.status = "ready"
            db.commit()
        except Exception as exc:
            db.rollback()
            try:
                delete_document_vectors(str(document_id), user_id)
            except Exception as cleanup_error:
                logger.error("Vector cleanup failed (%s)", type(cleanup_error).__name__)
            record.status = "failed"
            record.chunks_stored = 0
            try:
                db.commit()
            except Exception:
                db.rollback()
            # Do not return provider errors, credentials, or uploaded text to clients.
            logger.error("Document indexing failed (%s)", type(exc).__name__)
            raise HTTPException(
                status_code=503, detail="Document embedding or storage failed. Please try again later."
            ) from exc
        return DocumentUploadResponse(document_id=document_id, chunks_stored=len(ids))
    finally:
        if lock_connection is not None:
            try:
                if lock_identity is not None:
                    lock_connection.execute(text("SELECT pg_advisory_unlock(hashtextextended(:identity, 0))"), {"identity": lock_identity})
                    lock_connection.commit()
            except Exception as cleanup_error:
                # Never return a pooled connection that might retain a session lock.
                lock_connection.invalidate()
                logger.error("Upload lock cleanup failed (%s)", type(cleanup_error).__name__)
            finally:
                lock_connection.close()
        file.file.close()


def get_owned_document(document_id: UUID, user_id: UUID, db: Session) -> DocumentRecord:
    record = db.scalar(select(DocumentRecord).where(
        DocumentRecord.id == document_id, DocumentRecord.user_id == user_id
    ))
    if record is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return record


def list_documents(user_id: UUID, db: Session, limit: int, offset: int) -> list[DocumentRecord]:
    return list(db.scalars(select(DocumentRecord).where(
        DocumentRecord.user_id == user_id
    ).order_by(DocumentRecord.uploaded_at.desc(), DocumentRecord.id).limit(limit).offset(offset)))


def get_document_content(record: DocumentRecord) -> bytes:
    if record.status != "ready":
        raise HTTPException(status_code=409, detail="Document is not ready.")
    return record.pdf_content
