from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import websockets


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def validate_cloud() -> dict[str, Any]:
    from app.config import settings
    from app.doubao_realtime import (
        AUDIO_SERVER_RESPONSE,
        ClientEvent,
        ServerEvent,
        build_headers,
        build_start_session_payload,
        create_connect_id,
        create_session_id,
        decode_frame,
        doubao_realtime_missing_fields,
        encode_json_event,
        is_doubao_realtime_configured,
    )

    if not is_doubao_realtime_configured():
        missing = ", ".join(doubao_realtime_missing_fields())
        raise RuntimeError(f"缺少 {missing}，无法做真实豆包云端测试。")

    connect_id = create_connect_id()
    session_id = create_session_id()
    headers = build_headers(connect_id)
    messages: list[dict[str, Any]] = []
    audio_bytes = 0
    chat_text = ""
    chat_ended = False
    tts_ended = False

    async with websockets.connect(
        settings.doubao_realtime_ws_url,
        extra_headers=headers,
        max_size=None,
        open_timeout=10,
        ping_interval=20,
        ping_timeout=20,
    ) as ws:
        await ws.send(encode_json_event(ClientEvent.START_CONNECTION, {}))
        await ws.send(encode_json_event(ClientEvent.START_SESSION, build_start_session_payload(), session_id=session_id))

        query_sent = False
        deadline = asyncio.get_running_loop().time() + 35
        while asyncio.get_running_loop().time() < deadline:
            raw = await asyncio.wait_for(ws.recv(), timeout=10)
            frame = decode_frame(raw if isinstance(raw, bytes) else raw.encode("utf-8"))
            event = frame.event
            payload: dict[str, Any] = {}
            if frame.payload and frame.message_type != AUDIO_SERVER_RESPONSE:
                try:
                    payload = frame.json_payload()
                except Exception:
                    payload = {"raw": frame.payload.decode("utf-8", errors="replace")}

            if frame.message_type == AUDIO_SERVER_RESPONSE or event == ServerEvent.TTS_RESPONSE:
                audio_bytes += len(frame.payload)
                messages.append({"event": "TTSResponse", "audio_bytes": len(frame.payload)})
                continue

            messages.append({"event": event, "payload": payload})

            if event == ServerEvent.SESSION_STARTED and not query_sent:
                query_sent = True
                await ws.send(
                    encode_json_event(
                        ClientEvent.CHAT_TEXT_QUERY,
                        {"content": "请用一句话介绍你能为医院患者宣教做什么。"},
                        session_id=session_id,
                    )
                )
            elif event == ServerEvent.CHAT_RESPONSE:
                chat_text += str(payload.get("content") or "")
            elif event == ServerEvent.CHAT_ENDED:
                chat_ended = True
            elif event == ServerEvent.TTS_ENDED:
                tts_ended = True
            elif event in (ServerEvent.CONNECTION_FAILED, ServerEvent.SESSION_FAILED):
                raise RuntimeError(payload.get("error") or f"豆包云端返回失败事件: {event}")

            if chat_ended and audio_bytes > 0:
                break
            if tts_ended and chat_text.strip():
                break

        await ws.send(encode_json_event(ClientEvent.FINISH_SESSION, {}, session_id=session_id))
        await ws.send(encode_json_event(ClientEvent.FINISH_CONNECTION, {}))

    if not chat_text.strip():
        raise RuntimeError("豆包云端测试未收到 ChatResponse。")
    if audio_bytes <= 0:
        raise RuntimeError("豆包云端测试未收到 TTSResponse 音频。")

    return {
        "status": "ok",
        "model": settings.doubao_realtime_model,
        "speaker": settings.doubao_realtime_speaker,
        "chat_text": chat_text,
        "audio_bytes": audio_bytes,
        "events": messages,
    }


def main() -> None:
    try:
        result = asyncio.run(validate_cloud())
    except Exception as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1) from exc

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
