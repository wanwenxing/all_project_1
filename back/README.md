# Backend API

FastAPI backend for the `front` project.

## Tech stack

- FastAPI + Uvicorn
- SQLite + SQLAlchemy
- JWT auth (register / login)
- Passwords stored as bcrypt hashes (one-way, not plain text)
- JWT idle timeout: expires after 1 hour without authenticated backend requests
- uv for dependency management

## Quick start

```bash
cd back
cp .env.example .env
uv sync
uv run python run.py
```

Server runs at `http://localhost:3000` (matches Vite proxy in `front`).

## API endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/health` | No | Health check |
| GET | `/api/hello` | No | Demo endpoint for front |
| POST | `/api/auth/register` | No | Register |
| POST | `/api/auth/login` | No | Login |
| GET | `/api/users/me` | Bearer | Current user |
| POST | `/api/users/change-password` | Bearer | Change password (invalidates old tokens) |
| POST | `/api/docs/upload` | Bearer | Upload `.md` / `.txt` into `docs/` |
| POST | `/api/docs/index` | Bearer | Index one file via `?path=docs/xxx.md` (omit `path` to index all; `?rebuild=true` force) |
| POST | `/api/docs/search` | Bearer | Vector search with optional filters (`source_path` / `title` / `updated_at`) |

### Response format

```json
{
  "code": 0,
  "data": {},
  "message": "ok"
}
```

### Register / Login request

```json
{
  "username": "admin",
  "email": "admin@example.com",
  "password": "secret123"
}
```

Login only needs `username` and `password`. On success, `data.token.access_token` is the JWT.

Authenticated requests return a refreshed token in the `X-Access-Token` response header.
The client should replace the stored token with this value to keep the session alive
while the user remains active. If no authenticated request is made within 1 hour, the
token expires and the user must log in again.

## Development

```bash
uv run pytest
```

OpenAPI docs: `http://localhost:3000/docs`

## RAG indexing (Phase 1)

Index local markdown files into SQLite metadata + ChromaDB vectors using `BAAI/bge-large-zh-v1.5`.

Via API (front「知识库」页，需登录):

1. `POST /api/docs/upload` — multipart field `file`，保存到 `docs/`
2. `POST /api/docs/index?path=docs/笔记.md` — **只索引指定单个文件**
3. `POST /api/docs/index` — 不传 `path` 时扫描整个 `docs/`；`?rebuild=true` 全量重建

Embedding 模型首次会下载到 `data/models/`，之后一律读本地，不再访问 Hugging Face。

开发服务器热重载只监视 `app/`，避免 `.venv` / 模型缓存改动导致进程重启、模型反复卸载。

### Search (Phase 1)

```bash
POST /api/docs/search
```

```json
{
  "query": "友情",
  "top_k": 5,
  "source_path": "docs/好的友情不亚于爱情.md",
  "title": "好的友情不亚于爱情",
  "updated_at": "2026年6月"
}
```

`source_path` / `title` / `updated_at` 均为可选精确过滤；前端「知识库」页已提供检索表单。

Via CLI:

```bash
# Put markdown files under docs/
uv run python scripts/index_docs.py           # incremental index
uv run python scripts/index_docs.py --rebuild # full rebuild
```

Storage:

- `data/app.db` — `documents` and `document_chunks` tables
- `data/chroma/` — ChromaDB persistent vectors
- `data/models/` — embedding model local snapshot (first download only)

Optional metadata at the end of a markdown file:

```markdown
更新时间：2026年6月
```

First run downloads the BGE model from Hugging Face and may take a few minutes.
