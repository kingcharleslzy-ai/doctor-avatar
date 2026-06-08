from __future__ import annotations

import gzip
import json
import uuid
from dataclasses import dataclass
from typing import Any

from .config import settings


FULL_CLIENT_REQUEST = 0x1
AUDIO_CLIENT_REQUEST = 0x2
FULL_SERVER_RESPONSE = 0x9
AUDIO_SERVER_RESPONSE = 0xB
ERROR_INFORMATION = 0xF

SERIALIZATION_RAW = 0x0
SERIALIZATION_JSON = 0x1
COMPRESSION_NONE = 0x0
COMPRESSION_GZIP = 0x1

FLAG_POSITIVE_SEQUENCE = 0x1
FLAG_NEGATIVE_SEQUENCE = 0x3
FLAG_EVENT = 0x4


class ClientEvent:
    START_CONNECTION = 1
    FINISH_CONNECTION = 2
    START_SESSION = 100
    FINISH_SESSION = 102
    TASK_REQUEST = 200
    UPDATE_CONFIG = 201
    SAY_HELLO = 300
    END_ASR = 400
    CHAT_TTS_TEXT = 500
    CHAT_TEXT_QUERY = 501
    CHAT_RAG_TEXT = 502
    CLIENT_INTERRUPT = 515


class ServerEvent:
    CONNECTION_STARTED = 50
    CONNECTION_FAILED = 51
    CONNECTION_FINISHED = 52
    SESSION_STARTED = 150
    SESSION_FINISHED = 152
    SESSION_FAILED = 153
    USAGE_RESPONSE = 154
    CONFIG_UPDATED = 251
    TTS_SENTENCE_START = 350
    TTS_SENTENCE_END = 351
    TTS_RESPONSE = 352
    TTS_ENDED = 359
    ASR_INFO = 450
    ASR_RESPONSE = 451
    ASR_ENDED = 459
    CHAT_RESPONSE = 550
    CHAT_TEXT_QUERY_CONFIRMED = 553
    CHAT_ENDED = 559


SESSION_LEVEL_EVENTS = {
    ClientEvent.START_SESSION,
    ClientEvent.FINISH_SESSION,
    ClientEvent.TASK_REQUEST,
    ClientEvent.UPDATE_CONFIG,
    ClientEvent.SAY_HELLO,
    ClientEvent.END_ASR,
    ClientEvent.CHAT_TTS_TEXT,
    ClientEvent.CHAT_TEXT_QUERY,
    ClientEvent.CHAT_RAG_TEXT,
    ClientEvent.CLIENT_INTERRUPT,
    ServerEvent.SESSION_STARTED,
    ServerEvent.SESSION_FINISHED,
    ServerEvent.SESSION_FAILED,
    ServerEvent.USAGE_RESPONSE,
    ServerEvent.CONFIG_UPDATED,
    ServerEvent.TTS_SENTENCE_START,
    ServerEvent.TTS_SENTENCE_END,
    ServerEvent.TTS_RESPONSE,
    ServerEvent.TTS_ENDED,
    ServerEvent.ASR_INFO,
    ServerEvent.ASR_RESPONSE,
    ServerEvent.ASR_ENDED,
    ServerEvent.CHAT_RESPONSE,
    ServerEvent.CHAT_TEXT_QUERY_CONFIRMED,
    ServerEvent.CHAT_ENDED,
}


@dataclass
class RealtimeFrame:
    message_type: int
    flags: int
    serialization: int
    compression: int
    event: int | None
    payload: bytes
    session_id: str | None = None
    sequence: int | None = None
    code: int | None = None

    def json_payload(self) -> dict[str, Any]:
        if not self.payload:
            return {}
        return json.loads(self.payload.decode("utf-8"))


def is_doubao_realtime_configured() -> bool:
    return not doubao_realtime_missing_fields()


def doubao_realtime_missing_fields() -> list[str]:
    missing: list[str] = []
    if not settings.doubao_realtime_enabled:
        missing.append("DOUBAO_REALTIME_ENABLED")
    if not settings.doubao_realtime_api_key:
        missing.append("DOUBAO_REALTIME_API_KEY")
    return missing


def doubao_realtime_auth_mode() -> str:
    if settings.doubao_realtime_api_key:
        return "api_key"
    return "unconfigured"


def create_connect_id() -> str:
    return str(uuid.uuid4())


def create_session_id() -> str:
    return str(uuid.uuid4())


def build_headers(connect_id: str) -> dict[str, str]:
    missing = doubao_realtime_missing_fields()
    if missing:
        raise RuntimeError(f"豆包端到端实时语音未配置 {', '.join(missing)}。")
    return {
        "X-Api-Key": settings.doubao_realtime_api_key or "",
        "X-Api-Resource-Id": settings.doubao_realtime_resource_id,
        "X-Api-Connect-Id": connect_id,
    }


def uses_sc_clone_persona() -> bool:
    return (
        settings.doubao_realtime_model.strip() == "2.2.0.0"
        and settings.doubao_realtime_speaker.strip().startswith("S_")
    )


def adapt_dialog_persona(dialog_config: dict[str, Any]) -> dict[str, Any]:
    if not uses_sc_clone_persona():
        return dialog_config

    bot_name = str(dialog_config.get("bot_name") or settings.doubao_realtime_bot_name).strip()
    system_role = str(dialog_config.get("system_role") or settings.doubao_realtime_system_role).strip()
    speaking_style = str(dialog_config.get("speaking_style") or settings.doubao_realtime_speaking_style).strip()
    manifest_parts = [part for part in (bot_name, system_role, speaking_style) if part]
    return {"character_manifest": " ".join(manifest_parts)}


def build_start_session_payload() -> dict[str, Any]:
    dialog_persona = adapt_dialog_persona(
        {
            "bot_name": settings.doubao_realtime_bot_name,
            "system_role": settings.doubao_realtime_system_role,
            "speaking_style": settings.doubao_realtime_speaking_style,
        }
    )
    payload: dict[str, Any] = {
        "tts": {
            "speaker": settings.doubao_realtime_speaker,
            "audio_config": {
                "channel": 1,
                "format": "pcm_s16le",
                "sample_rate": 24000,
                "speech_rate": settings.doubao_realtime_speech_rate,
                "loudness_rate": settings.doubao_realtime_loudness_rate,
            },
        },
        "asr": {
            "extra": {
                "end_smooth_window_ms": settings.doubao_realtime_end_smooth_window_ms,
                "enable_asr_twopass": settings.doubao_realtime_enable_asr_twopass,
            },
        },
        "dialog": {
            "dialog_id": settings.doubao_realtime_dialog_id,
            **dialog_persona,
            "extra": {
                "strict_audit": settings.doubao_realtime_strict_audit,
                "audit_response": settings.doubao_realtime_audit_response,
                "input_mod": settings.doubao_realtime_input_mode,
                "model": settings.doubao_realtime_model,
                "enable_loudness_norm": settings.doubao_realtime_enable_loudness_norm,
                "enable_conversation_truncate": settings.doubao_realtime_enable_conversation_truncate,
                "enable_user_query_exit": settings.doubao_realtime_enable_user_query_exit,
            },
        },
    }
    hotwords = _comma_words(settings.doubao_realtime_hotwords)
    correct_words = _json_object(settings.doubao_realtime_correct_words)
    if hotwords or correct_words:
        context: dict[str, Any] = {}
        if hotwords:
            context["hotwords"] = [{"word": word} for word in hotwords]
        if correct_words:
            context["correct_words"] = correct_words
        payload["asr"]["extra"]["context"] = context

    if settings.doubao_realtime_enable_websearch:
        extra = payload["dialog"]["extra"]
        extra["enable_volc_websearch"] = True
        extra["volc_websearch_type"] = settings.doubao_realtime_websearch_type
        extra["volc_websearch_result_count"] = max(1, min(settings.doubao_realtime_websearch_result_count, 10))
        extra["volc_websearch_no_result_message"] = settings.doubao_realtime_websearch_no_result_message
        if settings.doubao_realtime_websearch_api_key:
            extra["volc_websearch_api_key"] = settings.doubao_realtime_websearch_api_key
        if settings.doubao_realtime_websearch_bot_id:
            extra["volc_websearch_bot_id"] = settings.doubao_realtime_websearch_bot_id
        if settings.doubao_realtime_location_city:
            payload["dialog"]["location"] = {
                "city": settings.doubao_realtime_location_city,
                "country": "中国",
                "country_code": "CN",
            }

    return payload


def _comma_words(value: str) -> list[str]:
    return [item.strip() for item in (value or "").replace("，", ",").split(",") if item.strip()]


def _json_object(value: str) -> dict[str, str]:
    if not value.strip():
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, dict):
        return {}
    return {str(key): str(val) for key, val in parsed.items() if str(key).strip() and str(val).strip()}


def encode_json_event(event: int, payload: dict[str, Any] | None = None, session_id: str | None = None) -> bytes:
    payload_bytes = json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _encode_frame(
        message_type=FULL_CLIENT_REQUEST,
        serialization=SERIALIZATION_JSON,
        event=event,
        payload=payload_bytes,
        session_id=session_id,
    )


def encode_audio_event(event: int, audio: bytes, session_id: str) -> bytes:
    return _encode_frame(
        message_type=AUDIO_CLIENT_REQUEST,
        serialization=SERIALIZATION_RAW,
        event=event,
        payload=audio,
        session_id=session_id,
    )


def encode_server_json_event(event: int, payload: dict[str, Any] | None = None, session_id: str | None = None) -> bytes:
    payload_bytes = json.dumps(payload or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return _encode_frame(
        message_type=FULL_SERVER_RESPONSE,
        serialization=SERIALIZATION_JSON,
        event=event,
        payload=payload_bytes,
        session_id=session_id,
    )


def encode_server_audio_event(audio: bytes, session_id: str | None = None) -> bytes:
    return _encode_frame(
        message_type=AUDIO_SERVER_RESPONSE,
        serialization=SERIALIZATION_RAW,
        event=ServerEvent.TTS_RESPONSE,
        payload=audio,
        session_id=session_id,
    )


def decode_frame(data: bytes) -> RealtimeFrame:
    if len(data) < 8:
        raise ValueError("豆包实时语音帧长度不足。")

    header_size = (data[0] & 0x0F) * 4
    if header_size < 4 or len(data) < header_size + 4:
        raise ValueError("豆包实时语音帧头不完整。")

    message_type = data[1] >> 4
    flags = data[1] & 0x0F
    serialization = data[2] >> 4
    compression = data[2] & 0x0F
    offset = header_size
    code: int | None = None
    sequence: int | None = None
    event: int | None = None
    session_id: str | None = None

    if message_type == ERROR_INFORMATION or flags == 0x0F:
        code, offset = _read_i32(data, offset)

    if flags in (FLAG_POSITIVE_SEQUENCE, FLAG_NEGATIVE_SEQUENCE):
        sequence, offset = _read_i32(data, offset)

    if flags & FLAG_EVENT:
        event, offset = _read_u32(data, offset)
        if event in SESSION_LEVEL_EVENTS:
            session_id, offset = _read_optional_session_id(data, offset)

    payload_size, offset = _read_u32(data, offset)
    if payload_size < 0 or offset + payload_size > len(data):
        raise ValueError("豆包实时语音帧 payload 长度无效。")
    payload = data[offset : offset + payload_size]
    if compression == COMPRESSION_GZIP and payload:
        payload = gzip.decompress(payload)

    return RealtimeFrame(
        message_type=message_type,
        flags=flags,
        serialization=serialization,
        compression=compression,
        event=event,
        payload=payload,
        session_id=session_id,
        sequence=sequence,
        code=code,
    )


def _encode_frame(
    *,
    message_type: int,
    serialization: int,
    event: int,
    payload: bytes,
    session_id: str | None,
) -> bytes:
    header = bytes(
        [
            0x11,
            (message_type << 4) | FLAG_EVENT,
            (serialization << 4) | COMPRESSION_NONE,
            0x00,
        ]
    )
    optional = bytearray()
    optional.extend(_u32(event))
    if session_id:
        session_bytes = session_id.encode("utf-8")
        optional.extend(_u32(len(session_bytes)))
        optional.extend(session_bytes)
    return header + bytes(optional) + _u32(len(payload)) + payload


def _read_u32(data: bytes, offset: int) -> tuple[int, int]:
    _require(data, offset, 4)
    return int.from_bytes(data[offset : offset + 4], "big", signed=False), offset + 4


def _read_i32(data: bytes, offset: int) -> tuple[int, int]:
    _require(data, offset, 4)
    return int.from_bytes(data[offset : offset + 4], "big", signed=True), offset + 4


def _read_optional_session_id(data: bytes, offset: int) -> tuple[str | None, int]:
    if offset + 8 > len(data):
        return None, offset

    candidate_size = int.from_bytes(data[offset : offset + 4], "big", signed=False)
    remaining_after_size = len(data) - offset - 4
    if candidate_size == 0 or candidate_size > 128 or candidate_size + 4 > remaining_after_size:
        return None, offset

    raw = data[offset + 4 : offset + 4 + candidate_size]
    try:
        session_id = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, offset

    if not session_id or ("-" not in session_id and not session_id.startswith("session")):
        return None, offset
    return session_id, offset + 4 + candidate_size


def _require(data: bytes, offset: int, size: int) -> None:
    if offset + size > len(data):
        raise ValueError("豆包实时语音帧字段不完整。")


def _u32(value: int) -> bytes:
    return int(value).to_bytes(4, "big", signed=False)
