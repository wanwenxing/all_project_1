from datetime import datetime

from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    title: str | None = Field(default=None, max_length=80)


class ChatSessionData(BaseModel):
    thread_id: str
    title: str
    created_at: datetime


class ChatMessageData(BaseModel):
    role: str
    content: str


class ChatMessageRequest(BaseModel):
    thread_id: str = Field(..., min_length=1, max_length=64)
    message: str = Field(..., min_length=1, max_length=4000)
