from uuid import UUID

from pydantic import BaseModel


class DocumentUploadResponse(BaseModel):
    status: str = "success"
    message: str = "Document embedded and stored successfully"
    document_id: UUID
    chunks_stored: int
