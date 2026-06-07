from typing import Literal

from pydantic import BaseModel, Field


class PresenceHeartbeatRequest(BaseModel):
    session_id: str = Field(min_length=8, max_length=120)


class RhinitisEvidenceReviewRequest(BaseModel):
    document_scope: Literal["raw", "curated"] = "raw"
    document_id: int = Field(ge=1)
    status: Literal["candidate", "needs_review", "approved", "rejected", "deprecated"]
    note: str = Field(default="", max_length=1200)
    reviewer: str = Field(default="MedFlow reviewer", max_length=120)
    patient_visible: bool | None = None
    doctor_visible: bool | None = None


class RhinitisEvidenceBatchReviewRequest(BaseModel):
    document_ids: list[int] = Field(min_length=1, max_length=50)
    status: Literal["candidate", "needs_review", "approved", "rejected", "deprecated"]
    note: str = Field(default="", max_length=1200)
    reviewer: str = Field(default="MedFlow reviewer", max_length=120)
    patient_visible: bool | None = None
    doctor_visible: bool | None = None
