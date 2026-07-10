from fastapi import APIRouter

from app.schemas.common import ApiResponse, success
from app.schemas.hello import HelloData

router = APIRouter()


@router.get("/hello", response_model=ApiResponse[HelloData])
def get_hello() -> ApiResponse[HelloData]:
    return success(HelloData(message="Hello from FastAPI backend"))
