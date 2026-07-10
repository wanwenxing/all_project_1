from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import AuthData, ChangePasswordRequest, UserPublic
from app.schemas.common import ApiResponse, success
from app.services.auth import change_password

router = APIRouter()


@router.get("/me", response_model=ApiResponse[UserPublic])
def get_me(current_user: User = Depends(get_current_user)) -> ApiResponse[UserPublic]:
    return success(UserPublic.model_validate(current_user))


@router.post("/change-password", response_model=ApiResponse[AuthData])
def update_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ApiResponse[AuthData]:
    data = change_password(db, current_user, payload.old_password, payload.new_password)
    return success(data, message="密码修改成功，请使用新 Token")
