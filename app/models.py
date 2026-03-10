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
    mode: str | None = None
    avatar_id: str | None = None
    voice_id: str | None = None
    context_id: str | None = None
    language: str | None = None
    is_sandbox: bool | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class LiveAvatarTokenResponse(BaseModel):
    data: dict[str, Any]


class LiveAvatarStartRequest(BaseModel):
    session_token: str = Field(min_length=1)
