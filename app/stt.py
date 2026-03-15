from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from openai import OpenAI

from .config import settings


def _convert_to_wav(audio_bytes: bytes, original_filename: str) -> tuple[bytes, str]:
    """Convert any audio format to 16kHz mono WAV via ffmpeg for maximum Whisper compatibility."""
    suffix = Path(original_filename).suffix or ".webm"
    inp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as inp:
            inp.write(audio_bytes)
            inp_path = inp.name
        out_path = inp_path + ".wav"
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", inp_path, "-ar", "16000", "-ac", "1", "-f", "wav", out_path],
            capture_output=True, timeout=10,
        )
        if result.returncode == 0 and Path(out_path).exists():
            wav_bytes = Path(out_path).read_bytes()
            return wav_bytes, "audio.wav"
    except Exception:
        pass  # ffmpeg not available or conversion failed — use original
    finally:
        if inp_path:
            for p in [inp_path, inp_path + ".wav"]:
                try:
                    Path(p).unlink(missing_ok=True)
                except Exception:
                    pass
    return audio_bytes, original_filename


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

        # Convert to WAV for maximum compatibility (iOS mp4/m4a, etc.)
        audio_bytes, filename = _convert_to_wav(audio_bytes, filename)

        last_error = None
        for attempt in range(2):  # retry once on transient failure
            try:
                transcript = self._openai_client.audio.transcriptions.create(
                    model=settings.openai_stt_model,
                    file=(filename, audio_bytes),
                    language=settings.stt_language,
                    prompt=settings.openai_stt_prompt or None,
                )
                text = transcript.text.strip()
                # Filter hallucinated prompt echo (Whisper returns prompt when audio is silent)
                prompt = (settings.openai_stt_prompt or "").strip()
                if prompt and text and (text == prompt or text in prompt or prompt in text):
                    text = ""
                return TranscriptionResult(
                    text=text,
                    provider="openai",
                    model=settings.openai_stt_model,
                )
            except Exception as exc:
                last_error = exc
                if attempt == 0 and "authentication" not in str(exc).lower():
                    import asyncio
                    await asyncio.sleep(0.5)
                    continue
                raise
        raise last_error  # type: ignore[misc]
