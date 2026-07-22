from pydantic import BaseModel


class UploadDocData(BaseModel):
    filename: str
    path: str
    size: int


class IndexStatsData(BaseModel):
    indexed: int
    skipped: int
    removed: int
    chunks: int
