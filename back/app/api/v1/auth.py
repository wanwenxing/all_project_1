from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.auth import AuthData, UserLoginRequest, UserRegisterRequest
from app.schemas.common import ApiResponse, success
from app.services.auth import login_user, register_user

router = APIRouter()


@router.post("/register", response_model=ApiResponse[AuthData])
def register(payload: UserRegisterRequest, db: Session = Depends(get_db)) -> ApiResponse[AuthData]:
    data = register_user(db, payload)
    return success(data, message="注册成功")


@router.post("/login", response_model=ApiResponse[AuthData])
def login(payload: UserLoginRequest, db: Session = Depends(get_db)) -> ApiResponse[AuthData]:
    data = login_user(db, payload)
    return success(data, message="登录成功")
