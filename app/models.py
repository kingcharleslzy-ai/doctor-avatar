from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation: list[dict[str, str]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)
    context_snippets: list[str] = Field(default_factory=list)


class LiveAvatarSessionRequest(BaseModel):
    avatar_name: str | None = None
    voice_id: str | None = None
    knowledge_id: str | None = None
    version: str | None = "v2"
    quality: str | None = "medium"
    video_encoding: str | None = "H264"
    source: str | None = "local"
    extra: dict[str, Any] = Field(default_factory=dict)


class LiveAvatarTokenResponse(BaseModel):
    data: dict[str, Any]
