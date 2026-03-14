from __future__ import annotations

from dataclasses import dataclass

from openai import OpenAI

from .config import settings


@dataclass
class TranscriptionResult:
    text: str
    provider: str
    model: str


class TranscriptionService:
    def __init__(self) -> None:
        stt_key = settings.stt_api_key or settings.openai_api_key
        self._openai_client = (
            OpenAI(api_key=stt_key, base_url="https://api.openai.com/v1")
            if stt_key
            else None
        )

    def provider_status(self) -> dict[str, object]:
        return {
            "active_provider": "openai",
            "providers": {
                "openai": {
                    "configured": bool(settings.stt_api_key or settings.openai_api_key),
                    "model": settings.openai_stt_model,
                    "language": settings.stt_language,
                }
            },
        }

    async def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm") -> TranscriptionResult:
        if self._openai_client is None:
            raise RuntimeError("语音识别 API key 未配置。")

        transcript = self._openai_client.audio.transcriptions.create(
            model=settings.openai_stt_model,
            file=(filename, audio_bytes),
            language=settings.stt_language,
            prompt=settings.openai_stt_prompt or None,
        )
        return TranscriptionResult(
            text=transcript.text,
            provider="openai",
            model=settings.openai_stt_model,
        )
