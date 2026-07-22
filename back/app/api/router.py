from fastapi import APIRouter

from app.api.v1 import auth, docs, hello, users

api_router = APIRouter(prefix="/api")
api_router.include_router(hello.router, tags=["demo"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(docs.router, prefix="/docs", tags=["docs"])
