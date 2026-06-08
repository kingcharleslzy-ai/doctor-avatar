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


class RhinitisDemoCase(BaseModel):
    age_group: str = Field(default="成人", max_length=40)
    main_symptoms: list[str] = Field(
        default_factory=lambda: ["鼻塞", "连续喷嚏", "清水样流涕", "鼻痒"],
        min_length=1,
        max_length=8,
    )
    duration: str = Field(default="反复 3 年，每年春秋加重，本次持续 2 周", max_length=160)
    seasonality: str = Field(default="春秋季明显，天气变化和花粉季加重", max_length=160)
    triggers: list[str] = Field(default_factory=lambda: ["花粉", "冷空气", "打扫卫生"], max_length=8)
    medication_history: str = Field(default="自行间断使用氯雷他定，鼻喷药使用不规律", max_length=260)
    allergen_tests: str = Field(default="既往提示尘螨和蒿草花粉 IgE 阳性，近期未复查", max_length=260)
    nasal_endoscopy: str = Field(default="鼻黏膜苍白水肿，下鼻甲肿胀，清亮分泌物，未见明显息肉", max_length=260)
    comorbidities: list[str] = Field(default_factory=lambda: ["偶有咳嗽，无明确哮喘诊断"], max_length=8)
    patient_goal: str = Field(default="希望明确是否为过敏性鼻炎，以及是否需要规范用药或脱敏治疗", max_length=260)


class RhinitisDemoSummaryRequest(BaseModel):
    case: RhinitisDemoCase = Field(default_factory=RhinitisDemoCase)
