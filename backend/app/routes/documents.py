from fastapi import APIRouter, UploadFile

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/upload")
def upload_document(file: UploadFile) -> dict[str, str]:
    print("Document upload endpoint called")
    return {"status": "success", "message": "Document upload request received"}
