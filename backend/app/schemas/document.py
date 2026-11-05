from uuid import UUID
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class DocumentUploadResponse(BaseModel):
    status: str = "success"
    message: str = "Document embedded and stored successfully"
    document_id: UUID
    chunks_stored: int


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    filename: str
    size_bytes: int
    page_count: int
    chunks_stored: int
    status: Literal["processing", "ready", "failed"]
    uploaded_at: datetime
