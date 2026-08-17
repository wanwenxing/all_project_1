from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.security import TOKEN_REFRESH_HEADER
from app.db.base import Base
from app.db.migrate import run_migrations
from app.db.session import engine, ensure_data_dir
from app.models import ask_log, document, document_chunk, eval_models, user  # noqa: F401
from app.schemas.common import error


class TokenRefreshMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        new_token = getattr(request.state, "new_access_token", None)
        if new_token:
            response.headers[TOKEN_REFRESH_HEADER] = new_token
        return response


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_data_dir()
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    yield


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)

app.add_middleware(TokenRefreshMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[TOKEN_REFRESH_HEADER],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    status_code = exc.status_code
    code = status_code if status_code >= 400 else 1
    message = exc.detail if isinstance(exc.detail, str) else "请求失败"
    return JSONResponse(status_code=status_code, content=error(code, message).model_dump())


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    messages = []
    for item in exc.errors():
        loc = ".".join(str(part) for part in item.get("loc", []) if part != "body")
        msg = item.get("msg", "参数错误")
        messages.append(f"{loc}: {msg}" if loc else msg)
    message = "; ".join(messages) or "参数校验失败"
    return JSONResponse(status_code=422, content=error(422, message).model_dump())


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(api_router)
