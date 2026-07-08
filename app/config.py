from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"


class Settings(BaseSettings):
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    site_brand_name: str = Field(default="MedFlow", alias="SITE_BRAND_NAME")
    site_legal_name: str = Field(default="杭州富阳启临数智科技工作室", alias="SITE_LEGAL_NAME")
    site_icp_beian_no: str = Field(default="", alias="SITE_ICP_BEIAN_NO")

    doubao_realtime_enabled: bool = Field(default=True, alias="DOUBAO_REALTIME_ENABLED")
    doubao_realtime_ws_url: str = Field(
        default="wss://openspeech.bytedance.com/api/v3/realtime/dialogue",
        alias="DOUBAO_REALTIME_WS_URL",
    )
    doubao_realtime_api_key: str | None = Field(default=None, alias="DOUBAO_REALTIME_API_KEY")
    doubao_realtime_resource_id: str = Field(default="volc.speech.dialog", alias="DOUBAO_REALTIME_RESOURCE_ID")
    doubao_realtime_model: str = Field(default="1.2.1.1", alias="DOUBAO_REALTIME_MODEL")
    doubao_realtime_speaker: str = Field(
        default="zh_male_yunzhou_jupiter_bigtts",
        alias="DOUBAO_REALTIME_SPEAKER",
    )
    doubao_realtime_speech_rate: int = Field(default=0, alias="DOUBAO_REALTIME_SPEECH_RATE")
    doubao_realtime_loudness_rate: int = Field(default=0, alias="DOUBAO_REALTIME_LOUDNESS_RATE")
    doubao_realtime_bot_name: str = Field(default="MedFlow", alias="DOUBAO_REALTIME_BOT_NAME")
    doubao_realtime_system_role: str = Field(
        default=(
            "你是 MedFlow 医疗 AI 信息化工作室提供的医疗健康科普语音助手。"
            "你只提供常见健康科普、就医准备、检查流程解释和术前术后注意事项的通俗说明；"
            "不做诊断结论，不替代医生面诊，不承诺疗效。遇到急症、严重症状或个体化治疗选择时，"
            "应建议用户及时联系医生或前往医疗机构。"
        ),
        alias="DOUBAO_REALTIME_SYSTEM_ROLE",
    )
    doubao_realtime_speaking_style: str = Field(
        default="沉稳、清晰、专业、温和，回答尽量简洁，适合医疗机构患者宣教场景。",
        alias="DOUBAO_REALTIME_SPEAKING_STYLE",
    )
    doubao_realtime_opening_remark: str = Field(
        default="你好，我是李医生。你先说一下现在最不舒服的症状，我来一步一步问清楚。",
        alias="DOUBAO_REALTIME_OPENING_REMARK",
    )
    doubao_realtime_dialog_id: str = Field(default="", alias="DOUBAO_REALTIME_DIALOG_ID")
    doubao_realtime_location_city: str = Field(default="杭州", alias="DOUBAO_REALTIME_LOCATION_CITY")
    doubao_realtime_input_mode: str = Field(default="keep_alive", alias="DOUBAO_REALTIME_INPUT_MODE")
    doubao_realtime_strict_audit: bool = Field(default=True, alias="DOUBAO_REALTIME_STRICT_AUDIT")
    doubao_realtime_audit_response: str = Field(
        default="这个问题需要由线下医生结合检查结果判断，我可以先帮你整理需要补充的信息。",
        alias="DOUBAO_REALTIME_AUDIT_RESPONSE",
    )
    doubao_realtime_end_smooth_window_ms: int = Field(default=1200, alias="DOUBAO_REALTIME_END_SMOOTH_WINDOW_MS")
    doubao_realtime_enable_asr_twopass: bool = Field(default=True, alias="DOUBAO_REALTIME_ENABLE_ASR_TWOPASS")
    doubao_realtime_hotwords: str = Field(
        default="鼻炎,过敏性鼻炎,鼻窦炎,鼻塞,喷嚏,鼻痒,流涕,鼻内镜,过敏原,免疫治疗,腺样体,鼻中隔,耳鸣,咽炎",
        alias="DOUBAO_REALTIME_HOTWORDS",
    )
    doubao_realtime_correct_words: str = Field(default="", alias="DOUBAO_REALTIME_CORRECT_WORDS")
    doubao_realtime_enable_websearch: bool = Field(default=False, alias="DOUBAO_REALTIME_ENABLE_WEBSEARCH")
    doubao_realtime_websearch_type: str = Field(default="web_summary", alias="DOUBAO_REALTIME_WEBSEARCH_TYPE")
    doubao_realtime_websearch_api_key: str | None = Field(default=None, alias="DOUBAO_REALTIME_WEBSEARCH_API_KEY")
    doubao_realtime_websearch_bot_id: str | None = Field(default=None, alias="DOUBAO_REALTIME_WEBSEARCH_BOT_ID")
    doubao_realtime_websearch_result_count: int = Field(default=5, alias="DOUBAO_REALTIME_WEBSEARCH_RESULT_COUNT")
    doubao_realtime_websearch_no_result_message: str = Field(
        default="没有检索到可靠的实时资料，本轮先依据已确认的院内资料继续说明。",
        alias="DOUBAO_REALTIME_WEBSEARCH_NO_RESULT_MESSAGE",
    )
    doubao_realtime_enable_loudness_norm: bool = Field(default=True, alias="DOUBAO_REALTIME_ENABLE_LOUDNESS_NORM")
    doubao_realtime_enable_conversation_truncate: bool = Field(
        default=True,
        alias="DOUBAO_REALTIME_ENABLE_CONVERSATION_TRUNCATE",
    )
    doubao_realtime_enable_user_query_exit: bool = Field(default=True, alias="DOUBAO_REALTIME_ENABLE_USER_QUERY_EXIT")

    doctor_memory_db_path: str = Field(default=str(BASE_DIR / "data" / "doctor_memory.db"), alias="DOCTOR_MEMORY_DB_PATH")
    doctor_memory_bootstrap: bool = Field(default=True, alias="DOCTOR_MEMORY_BOOTSTRAP")
    rhinitis_evidence_db_path: str = Field(
        default=str(BASE_DIR / "data" / "rhinitis_evidence.db"),
        alias="RHINITIS_EVIDENCE_DB_PATH",
    )
    rhinitis_evidence_review_enabled: bool = Field(default=False, alias="RHINITIS_EVIDENCE_REVIEW_ENABLED")
    rhinitis_evidence_seed_snapshot_enabled: bool = Field(
        default=True,
        alias="RHINITIS_EVIDENCE_SEED_SNAPSHOT_ENABLED",
    )

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
