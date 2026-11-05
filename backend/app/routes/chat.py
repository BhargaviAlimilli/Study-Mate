from fastapi import APIRouter

router = APIRouter(tags=["Chat"])


@router.post("/query")
def query() -> dict[str, str]:
    print("Query endpoint called")
    return {"status": "success", "message": "Query request received"}
