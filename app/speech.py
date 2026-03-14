from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Literal

import httpx
from openai import OpenAI

from .config import settings


TTSProvider = Literal["aliyun", "openai", "edge"]


@dataclass
class SpeechResult:
    audio: bytes
    media_type: str
    provider: TTSProvider
    voice: str


class SpeechService:
    def __init__(self) -> None:
        tts_key = settings.openai_tts_api_key or settings.stt_api_key or settings.openai_api_key
        self._openai_client = (
            OpenAI(api_key=tts_key, base_url="https://api.openai.com/v1")
            if tts_key
            else None
        )

    async def synthesize(
        self,
        text: str,
        *,
        provider: TTSProvider | None = None,
        voice: str | None = None,
    ) -> SpeechResult:
        providers = self._provider_chain(provider)
        last_error: Exception | None = None

        for current in providers:
            try:
                if current == "aliyun":
                    return await self._synthesize_aliyun(text, voice)
                if current == "openai":
                    return await self._synthesize_openai(text, voice)
                return await self._synthesize_edge(text, voice)
            except Exception as exc:  # pragma: no cover - fallback behavior
                last_error = exc

        raise RuntimeError(f"TTS 失败：{last_error}") from last_error

    def provider_status(self) -> dict[str, object]:
        return {
            "active_provider": settings.tts_provider,
            "fallback_provider": settings.tts_fallback_provider,
            "providers": {
                "aliyun": {
                    "configured": bool(settings.dashscope_api_key),
                    "voice": settings.aliyun_tts_voice,
                    "model": settings.aliyun_tts_model,
                },
                "openai": {
                    "configured": bool(settings.openai_tts_api_key or settings.stt_api_key or settings.openai_api_key),
                    "voice": settings.openai_tts_voice,
                    "model": settings.openai_tts_model,
                },
                "edge": {
                    "configured": True,
                    "voice": settings.edge_tts_voice,
                    "model": "edge-tts",
                },
            },
        }

    def _provider_chain(self, requested: TTSProvider | None) -> list[TTSProvider]:
        if requested:
            return [requested]
        ordered = [requested or settings.tts_provider, settings.tts_fallback_provider, "edge"]
        unique: list[TTSProvider] = []
        for provider in ordered:
            if provider not in unique:
                unique.append(provider)
        return unique

    async def _synthesize_edge(self, text: str, voice: str | None) -> SpeechResult:
        import edge_tts

        selected_voice = voice or settings.edge_tts_voice or settings.tts_voice
        communicate = edge_tts.Communicate(text, selected_voice)
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return SpeechResult(
            audio=buf.getvalue(),
            media_type="audio/mpeg",
            provider="edge",
            voice=selected_voice,
        )

    async def _synthesize_openai(self, text: str, voice: str | None) -> SpeechResult:
        if self._openai_client is None:
            raise RuntimeError("OpenAI TTS 未配置。")

        selected_voice = voice or settings.openai_tts_voice
        response = self._openai_client.audio.speech.create(
            model=settings.openai_tts_model,
            voice=selected_voice,
            input=text,
            instructions=settings.openai_tts_instructions,
            response_format="mp3",
        )
        return SpeechResult(
            audio=response.read(),
            media_type="audio/mpeg",
            provider="openai",
            voice=selected_voice,
        )

    async def _synthesize_aliyun(self, text: str, voice: str | None) -> SpeechResult:
        if not settings.dashscope_api_key:
            raise RuntimeError("阿里云 TTS 未配置。")

        try:
            from dashscope.audio.qwen_tts import SpeechSynthesizer
        except Exception as exc:  # pragma: no cover - dependency missing
            raise RuntimeError("缺少 dashscope 依赖，无法使用阿里云语音。") from exc

        selected_voice = voice or settings.aliyun_tts_voice
        response = SpeechSynthesizer.call(
            model=settings.aliyun_tts_model,
            api_key=settings.dashscope_api_key,
            text=text,
            voice=selected_voice,
        )
        status_code = getattr(response, "status_code", None)
        if status_code and status_code >= 400:
            message = getattr(response, "message", "阿里云 TTS 返回错误")
            raise RuntimeError(message)

        output = getattr(response, "output", None)
        if output is None:
            raise RuntimeError("阿里云 TTS 未返回音频信息。")

        audio = output.get("audio") if isinstance(output, dict) else getattr(output, "audio", None)
        if not audio:
            raise RuntimeError("阿里云 TTS 输出缺少 audio 字段。")

        url = audio.get("url") if isinstance(audio, dict) else getattr(audio, "url", None)
        if not url:
            raise RuntimeError("阿里云 TTS 输出缺少音频 URL。")

        async with httpx.AsyncClient(timeout=60.0) as client:
            audio_response = await client.get(url)
            audio_response.raise_for_status()
            media_type = audio_response.headers.get("content-type", "audio/wav").split(";")[0]
            return SpeechResult(
                audio=audio_response.content,
                media_type=media_type,
                provider="aliyun",
                voice=selected_voice,
            )
