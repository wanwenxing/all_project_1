from pydantic import BaseModel, Field


class UploadDocData(BaseModel):
    filename: str
    path: str
    size: int


class IndexStatsData(BaseModel):
    indexed: int
    skipped: int
    metadata_updated: int = 0
    removed: int
    chunks: int


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="检索关键字 / 自然语言问题")
    top_k: int = Field(2, ge=1, le=50, description="返回条数（混合精排后的最终条数）")
    source_path: str | None = Field(None, description="按文件路径精确过滤，如 docs/笔记.md")
    title: str | None = Field(None, description="按标题精确过滤")
    updated_at: str | None = Field(None, description="按更新时间标签精确过滤")


class SearchHitData(BaseModel):
    chroma_id: str
    content: str
    distance: float | None = None
    score: float | None = None
    document_id: str | None = None
    chunk_id: str | None = None
    chunk_index: int | None = None
    source_path: str | None = None
    title: str | None = None
    updated_at: str | None = None


class SearchResultData(BaseModel):
    query: str
    total: int
    hits: list[SearchHitData]


class AskRequest(BaseModel):
    query: str = Field(..., min_length=1, description="自然语言问题")
    top_k: int = Field(2, ge=1, le=50, description="送给 LLM 的检索条数（精排后）")
    source_path: str | None = Field(None, description="按文件路径精确过滤")
    title: str | None = Field(None, description="按标题精确过滤")
    updated_at: str | None = Field(None, description="按更新时间标签精确过滤")
