from pydantic import BaseModel, Field


class PresenceHeartbeatRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=120)
