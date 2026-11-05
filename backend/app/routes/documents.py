from typing import Annotated
from uuid import UUID
from io import BytesIO

from fastapi import APIRouter, Depends, UploadFile, Query, HTTPException, Response
from sqlalchemy.orm import Session
from pypdf import PdfReader, PdfWriter

from app.core.security import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.document import DocumentUploadResponse, DocumentResponse
from app.services.document_service import process_document_upload, get_owned_document, list_documents, get_document_content

router = APIRouter(prefix="/documents", tags=["Documents"])
Database = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]


@router.post("/upload", response_model=DocumentUploadResponse, status_code=201)
def upload_document(
    file: UploadFile, user: CurrentUser, db: Database
) -> DocumentUploadResponse:
    return process_document_upload(file, user_id=str(user.id), db=db)


@router.get("", response_model=list[DocumentResponse])
def documents(user: CurrentUser, db: Database, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return list_documents(user.id, db, limit, offset)


@router.get("/{document_id}", response_model=DocumentResponse)
def document(document_id: UUID, user: CurrentUser, db: Database):
    return get_owned_document(document_id, user.id, db)


@router.get("/{document_id}/file", response_class=Response)
def document_file(document_id: UUID, user: CurrentUser, db: Database, page: int | None = Query(None, ge=1)):
    record = get_owned_document(document_id, user.id, db)
    content = get_document_content(record)
    headers = {"Cache-Control": "no-store"}
    if page is None:
        return Response(content, media_type="application/pdf", headers=headers)
    if page > record.page_count:
        raise HTTPException(status_code=404, detail="Page not found.")
    try:
        reader = PdfReader(BytesIO(content))
        writer = PdfWriter()
        writer.add_page(reader.pages[page - 1])
        output = BytesIO()
        writer.write(output)
    except Exception as exc:
        raise HTTPException(status_code=503, detail="The PDF page could not be opened.") from exc
    return Response(output.getvalue(), media_type="application/pdf", headers=headers)
