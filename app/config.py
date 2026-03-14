from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
KNOWLEDGE_DIR = BASE_DIR / "knowledge"


class Settings(BaseSettings):
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, alias="OPENAI_BASE_URL")
    openai_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_MODEL")
    stt_api_key: str | None = Field(default=None, alias="STT_API_KEY")
    openai_tts_api_key: str | None = Field(default=None, alias="OPENAI_TTS_API_KEY")
    heygen_api_key: str | None = Field(default=None, alias="HEYGEN_API_KEY")
    heygen_api_base: str = Field(default="https://api.heygen.com", alias="HEYGEN_API_BASE")
    liveavatar_api_base: str = Field(default="https://api.liveavatar.com", alias="LIVEAVATAR_API_BASE")
    heygen_mode: str = Field(default="FULL", alias="HEYGEN_MODE")
    heygen_avatar_id: str | None = Field(default=None, alias="HEYGEN_AVATAR_ID")
    heygen_voice_id: str | None = Field(default=None, alias="HEYGEN_VOICE_ID")
    heygen_context_id: str | None = Field(default=None, alias="HEYGEN_CONTEXT_ID")
    heygen_language: str = Field(default="zh", alias="HEYGEN_LANGUAGE")
    heygen_use_sandbox: bool = Field(default=True, alias="HEYGEN_USE_SANDBOX")
    heygen_push_to_talk: bool = Field(default=False, alias="HEYGEN_PUSH_TO_TALK")
    enable_video_avatar: bool = Field(default=False, alias="ENABLE_VIDEO_AVATAR")
    console_auth_mode: Literal["off", "basic"] = Field(default="basic", alias="CONSOLE_AUTH_MODE")
    console_username: str | None = Field(default=None, alias="CONSOLE_USERNAME")
    console_password: str | None = Field(default=None, alias="CONSOLE_PASSWORD")
    app_host: str = Field(default="127.0.0.1", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    embed_cache_dir: str = Field(default="", alias="EMBED_CACHE_DIR")
    ditto_service_url: str = Field(default="http://127.0.0.1:8001", alias="DITTO_SERVICE_URL")
    ditto_enabled: bool = Field(default=False, alias="ENABLE_DITTO_VIDEO")
    ditto_ws_url: str = Field(default="ws://host.docker.internal:8002", alias="DITTO_WS_URL")
    ditto_stream_enabled: bool = Field(default=False, alias="ENABLE_DITTO_STREAM")
    tts_voice: str = Field(default="zh-CN-XiaoxiaoNeural", alias="TTS_VOICE")
    tts_provider: Literal["aliyun", "openai", "edge"] = Field(default="aliyun", alias="TTS_PROVIDER")
    tts_fallback_provider: Literal["aliyun", "openai", "edge"] = Field(default="openai", alias="TTS_FALLBACK_PROVIDER")
    dashscope_api_key: str | None = Field(default=None, alias="DASHSCOPE_API_KEY")
    aliyun_tts_model: str = Field(default="qwen-tts-latest", alias="ALIYUN_TTS_MODEL")
    aliyun_tts_voice: str = Field(default="Neil", alias="ALIYUN_TTS_VOICE")
    openai_tts_model: str = Field(default="gpt-4o-mini-tts", alias="OPENAI_TTS_MODEL")
    openai_tts_voice: str = Field(default="cedar", alias="OPENAI_TTS_VOICE")
    openai_tts_instructions: str = Field(
        default="请用沉稳、成熟、专业、温和的中文男医生语气说话，语速平稳，吐字清晰，不要夸张表演。",
        alias="OPENAI_TTS_INSTRUCTIONS",
    )
    edge_tts_voice: str = Field(default="zh-CN-YunxiNeural", alias="EDGE_TTS_VOICE")
    doctor_memory_db_path: str = Field(default=str(BASE_DIR / "data" / "doctor_memory.db"), alias="DOCTOR_MEMORY_DB_PATH")
    doctor_memory_bootstrap: bool = Field(default=True, alias="DOCTOR_MEMORY_BOOTSTRAP")
    console_memory_write_enabled: bool = Field(default=False, alias="CONSOLE_MEMORY_WRITE_ENABLED")

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
