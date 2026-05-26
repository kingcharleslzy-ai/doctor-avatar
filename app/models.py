from pydantic import BaseModel, Field


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
