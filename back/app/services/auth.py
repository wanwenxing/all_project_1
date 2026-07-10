from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.user import User
from app.schemas.auth import AuthData, TokenData, UserLoginRequest, UserPublic, UserRegisterRequest
from app.services.user import get_user_by_email, get_user_by_username


def register_user(db: Session, payload: UserRegisterRequest) -> AuthData:
    if get_user_by_username(db, payload.username):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")

    if get_user_by_email(db, payload.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邮箱已被注册")

    user = User(
        username=payload.username,
        email=payload.email,
        hashed_password=get_password_hash(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return _build_auth_data(user)


def login_user(db: Session, payload: UserLoginRequest) -> AuthData:
    user = get_user_by_username(db, payload.username)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="账号已被禁用")

    return _build_auth_data(user)


def _build_auth_data(user: User) -> AuthData:
    access_token = create_access_token(user.id, user.token_version)
    return AuthData(
        token=TokenData(access_token=access_token),
        user=UserPublic.model_validate(user),
    )


def change_password(db: Session, user: User, old_password: str, new_password: str) -> AuthData:
    if not verify_password(old_password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="原密码错误")

    user.hashed_password = get_password_hash(new_password)
    user.token_version += 1
    db.commit()
    db.refresh(user)

    return _build_auth_data(user)
