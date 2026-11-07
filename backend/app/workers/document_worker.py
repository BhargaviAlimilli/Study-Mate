"""RQ jobs carry identifiers only. Original PDFs remain in PostgreSQL."""
from io import BytesIO
from uuid import UUID
from redis import Redis
from rq import Queue
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile, Headers
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.document import DocumentRecord
from app.models.user import User


def ingestion_queue():
    return Queue("default", connection=Redis.from_url(get_settings().redis_url, socket_connect_timeout=5, socket_timeout=5))


def job_is_active(queue, job_id):
    if not job_id:
        return False
    job = queue.fetch_job(job_id)
    return job is not None and job.get_status(refresh=True) in {"queued", "started", "scheduled", "deferred"}


def ingest_document(document_id: str, user_id: str, job_id: str):
    from app.services.document_service import process_document_upload
    with SessionLocal() as db:
        record = db.get(DocumentRecord, UUID(document_id))
        if record is None or str(record.user_id) != user_id or record.ingestion_job_id != job_id:
            return {"status": "superseded"}
        upload = UploadFile(file=BytesIO(record.pdf_content), filename=record.filename, headers=Headers({"content-type": "application/pdf"}))
        try:
            return process_document_upload(upload, user_id, db, expected_job_id=job_id).model_dump(mode="json")
        except Exception:
            from rq import get_current_job
            current = get_current_job()
            db.rollback()
            record = db.get(DocumentRecord, UUID(document_id))
            if record and record.ingestion_job_id == job_id:
                record.status = "queued" if current and current.retries_left else "failed"
                record.chunks_stored = 0
                db.commit()
            raise


def ingestion_failed(job, connection, exception_type, exception_value, traceback):
    """RQ also invokes this in the parent worker after a timeout/work-horse failure."""
    document_id, user_id, job_id = job.args
    with SessionLocal() as db:
        record = db.get(DocumentRecord, UUID(document_id))
        if record and str(record.user_id) == user_id and record.ingestion_job_id == job_id and record.status != "ready":
            record.status = "queued" if job.retries_left else "failed"
            record.chunks_stored = 0
            db.commit()
