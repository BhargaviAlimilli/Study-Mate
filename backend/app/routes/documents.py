from typing import Annotated

from fastapi import APIRouter, Depends, UploadFile

from app.core.security import get_current_user
from app.models.user import User
from app.schemas.document import DocumentUploadResponse
from app.services.document_service import process_document_upload

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
def upload_document(
    file: UploadFile, user: Annotated[User, Depends(get_current_user)]
) -> DocumentUploadResponse:
    return process_document_upload(file, user_id=str(user.id))
