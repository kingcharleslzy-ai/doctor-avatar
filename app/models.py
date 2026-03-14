from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation: list[dict[str, str]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)
    context_snippets: list[str] = Field(default_factory=list)


class MemoryEntryCreate(BaseModel):
    kind: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=8000)
    tags: list[str] = Field(default_factory=list)
    source: str = Field(default="manual", max_length=200)
    importance: float = Field(default=1.0, ge=0.1, le=5.0)


class MemoryEntryResponse(BaseModel):
    id: int
    kind: str
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)
    source: str
    importance: float
    created_at: str
    updated_at: str


class MemoryEntryDeleteRequest(BaseModel):
    entry_ids: list[int] = Field(min_length=1)


class PresenceHeartbeatRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=120)


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


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: str | None = None
    provider: Literal["aliyun", "openai", "edge"] | None = None


class DittoGenerateRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
