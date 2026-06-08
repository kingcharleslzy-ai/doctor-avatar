from __future__ import annotations

import asyncio
import base64
import json
import os
import socket
import sys
from contextlib import closing
from pathlib import Path
from typing import Any

import uvicorn
import websockets
import httpx


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def free_port() -> int:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def configure_environment(fake_upstream_url: str) -> None:
    os.environ["DOUBAO_REALTIME_ENABLED"] = "true"
    os.environ["DOUBAO_REALTIME_API_KEY"] = "test-api-key"
    os.environ["DOUBAO_REALTIME_WS_URL"] = fake_upstream_url
    os.environ["DOUBAO_REALTIME_MODEL"] = "2.2.0.0"
    os.environ["DOUBAO_REALTIME_SPEAKER"] = "S_rlFycKm22"


async def wait_for_http(url: str, timeout: float = 8.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    async with httpx.AsyncClient(timeout=1.0) as client:
        while True:
            try:
                response = await client.get(url)
                if response.status_code < 500:
                    return
            except Exception:
                pass
            if asyncio.get_running_loop().time() > deadline:
                raise TimeoutError(f"Timed out waiting for {url}")
            await asyncio.sleep(0.05)


async def run_fake_upstream(stop_event: asyncio.Event, observed: dict[str, Any]):
    from app.doubao_realtime import (
        ClientEvent,
        ServerEvent,
        decode_frame,
        encode_server_audio_event,
        encode_server_json_event,
    )

    async def handler(ws):
        observed["headers"] = {
            "api_key": ws.request_headers.get("X-Api-Key"),
            "app_id": ws.request_headers.get("X-Api-App-ID"),
            "access_key": ws.request_headers.get("X-Api-Access-Key"),
            "resource_id": ws.request_headers.get("X-Api-Resource-Id"),
            "app_key": ws.request_headers.get("X-Api-App-Key"),
        }

        start_connection = decode_frame(await ws.recv())
        start_session = decode_frame(await ws.recv())
        observed["start_connection_event"] = start_connection.event
        observed["start_session_event"] = start_session.event
        observed["start_session_payload"] = start_session.json_payload()
        session_id = start_session.session_id

        await ws.send(encode_server_json_event(ServerEvent.CONNECTION_STARTED, {}))
        await ws.send(encode_server_json_event(ServerEvent.SESSION_STARTED, {"dialog_id": "fake-dialog"}, session_id))

        while "say_hello_event" not in observed or "audio_event" not in observed:
            frame = decode_frame(await ws.recv())
            if frame.event == ClientEvent.SAY_HELLO:
                observed["say_hello_event"] = frame.event
                observed["say_hello_payload"] = frame.json_payload()
            elif frame.event == ClientEvent.TASK_REQUEST:
                observed["audio_event"] = frame.event
                observed["audio_payload_len"] = len(frame.payload)
            else:
                observed.setdefault("unexpected_client_events", []).append(frame.event)

        await ws.send(
            encode_server_json_event(
                ServerEvent.ASR_RESPONSE,
                {"results": [{"text": observed["say_hello_payload"]["content"], "is_interim": False}]},
                session_id,
            )
        )
        await ws.send(encode_server_json_event(ServerEvent.ASR_ENDED, {}, session_id))
        try:
            frame = decode_frame(await asyncio.wait_for(ws.recv(), timeout=1.5))
            observed["echo_unexpected_event"] = frame.event
            observed["echo_unexpected_payload"] = frame.json_payload() if frame.payload else {}
        except asyncio.TimeoutError:
            observed["echo_ignored"] = True

        await ws.send(
            encode_server_json_event(
                ServerEvent.ASR_RESPONSE,
                {"results": [{"text": "我鼻子流血。", "is_interim": False}]},
                session_id,
            )
        )
        try:
            frame = decode_frame(await asyncio.wait_for(ws.recv(), timeout=0.5))
            observed["rag_before_asr_end_event"] = frame.event
            observed["rag_before_asr_end_payload"] = frame.json_payload() if frame.payload else {}
        except asyncio.TimeoutError:
            observed["no_rag_before_asr_end"] = True

        await ws.send(encode_server_json_event(ServerEvent.ASR_ENDED, {}, session_id))

        while "chat_rag_event" not in observed:
            frame = decode_frame(await asyncio.wait_for(ws.recv(), timeout=2.0))
            if frame.event == ClientEvent.CHAT_RAG_TEXT:
                observed["chat_rag_event"] = frame.event
                observed["chat_rag_payload"] = frame.json_payload()
            else:
                observed.setdefault("voice_query_client_events", []).append(frame.event)

        await ws.send(
            encode_server_json_event(
                ServerEvent.CHAT_RESPONSE,
                {"content": "你现在最主要的不舒服是什么？", "question_id": "q-default", "reply_id": "r-default"},
                session_id,
            )
        )
        await ws.send(encode_server_json_event(ServerEvent.CHAT_ENDED, {"question_id": "q-default", "reply_id": "r-default"}, session_id))

        await ws.send(
            encode_server_json_event(
                ServerEvent.CHAT_RESPONSE,
                {"content": "这次流鼻血大概有多久了，", "question_id": "q1", "reply_id": "r1"},
                session_id,
            )
        )
        await ws.send(
            encode_server_json_event(
                ServerEvent.TTS_SENTENCE_START,
                {
                    "text": "",
                    "tts_type": "external_rag",
                    "question_id": "q1",
                    "reply_id": "r1",
                },
                session_id,
            )
        )
        await ws.send(
            encode_server_json_event(
                ServerEvent.CHAT_RESPONSE,
                {"content": "按压后能不能止住？", "question_id": "q1", "reply_id": "r1"},
                session_id,
            )
        )
        await ws.send(encode_server_json_event(ServerEvent.CHAT_ENDED, {"question_id": "q1", "reply_id": "r1"}, session_id))
        await ws.send(encode_server_audio_event(b"\x01\x00\x02\x00\x03\x00\x04\x00", session_id))
        await ws.send(encode_server_json_event(ServerEvent.TTS_ENDED, {"question_id": "q1", "reply_id": "r1"}, session_id))
        stop_event.set()

    return handler


async def run_app_server(port: int):
    from app.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    return server, task


async def validate() -> dict[str, Any]:
    upstream_port = free_port()
    app_port = free_port()
    stop_event = asyncio.Event()
    observed: dict[str, Any] = {}
    configure_environment(f"ws://127.0.0.1:{upstream_port}")

    fake_server = await websockets.serve(await run_fake_upstream(stop_event, observed), "127.0.0.1", upstream_port)
    app_server, app_task = await run_app_server(app_port)

    try:
        await wait_for_http(f"http://127.0.0.1:{app_port}/health")
        client_url = f"ws://127.0.0.1:{app_port}/ws/doubao/realtime"
        async with websockets.connect(client_url) as ws:
            messages: list[dict[str, Any]] = []
            await ws.send(b"\x00" * 640)
            while len(messages) < 16:
                message = await asyncio.wait_for(ws.recv(), timeout=5)
                payload = json.loads(message)
                messages.append(payload)
                if payload.get("type") == "chat_end":
                    break
            try:
                await ws.send(json.dumps({"type": "finish"}))
            except websockets.ConnectionClosed:
                pass

        await asyncio.wait_for(stop_event.wait(), timeout=5)

        from app.doubao_realtime import ClientEvent

        assert observed["headers"]["api_key"] == "test-api-key"
        assert observed["headers"]["app_id"] is None
        assert observed["headers"]["access_key"] is None
        assert observed["headers"]["resource_id"] == "volc.speech.dialog"
        assert observed["start_connection_event"] == 1
        assert observed["start_session_event"] == 100
        assert observed["start_session_payload"]["dialog"]["extra"]["model"] == "2.2.0.0"
        assert observed["start_session_payload"]["tts"]["speaker"] == "S_rlFycKm22"
        assert "character_manifest" in observed["start_session_payload"]["dialog"]
        assert "bot_name" not in observed["start_session_payload"]["dialog"]
        assert "system_role" not in observed["start_session_payload"]["dialog"]
        assert "speaking_style" not in observed["start_session_payload"]["dialog"]
        assert observed["say_hello_event"] == 300
        assert observed.get("echo_ignored") is True, observed
        assert "echo_unexpected_event" not in observed, observed
        assert observed["audio_event"] == 200
        assert observed["audio_payload_len"] == 640
        assert observed.get("no_rag_before_asr_end") is True, observed
        assert "rag_before_asr_end_event" not in observed, observed
        assert observed.get("chat_rag_event") == 502, observed
        assert ClientEvent.UPDATE_CONFIG not in observed.get("voice_query_client_events", []), observed
        assert ClientEvent.SAY_HELLO not in observed.get("voice_query_client_events", []), observed

        external_rag = observed["chat_rag_payload"]["external_rag"]
        rag_items = json.loads(external_rag)
        assert isinstance(rag_items, list) and rag_items, rag_items
        assert all({"title", "content"} <= set(item) for item in rag_items), rag_items
        packed_rag = json.dumps(rag_items, ensure_ascii=False)
        assert "我鼻子流血" in packed_rag, packed_rag
        assert "按鼻出血进行安全分层" in packed_rag, packed_rag
        assert "本轮优先补充信息：这次流鼻血现在按压能止住吗" in packed_rag, packed_rag
        assert "按压后能否止住" in packed_rag, packed_rag
        assert "本轮优先补充信息：鼻子不舒服持续几天了" not in packed_rag, packed_rag
        assert "本轮唯一允许追问的问题" not in packed_rag, packed_rag
        assert "你现在最主要的不舒服是什么" not in packed_rag, packed_rag

        types = [message.get("type") for message in messages]
        assert "status" in types
        assert "asr" in types
        assert "rag_context" in types
        assert "chat" in types
        assert "audio" in types, {"types": types, "messages": messages, "observed": observed}
        assert "chat_end" in types
        asr_texts = [message.get("text") for message in messages if message.get("type") == "asr"]
        assert observed["say_hello_payload"]["content"] not in asr_texts
        assert "我鼻子流血。" in asr_texts
        chat_texts = [message.get("content", "") for message in messages if message.get("type") == "chat"]
        joined_chat_text = "".join(chat_texts)
        assert "这次流鼻血大概有多久了，按压后能不能止住？" in joined_chat_text, chat_texts
        assert all("你现在最主要的不舒服是什么" not in text for text in chat_texts), chat_texts

        audio_message = next(message for message in messages if message.get("type") == "audio")
        assert base64.b64decode(audio_message["audio"]) == b"\x01\x00\x02\x00\x03\x00\x04\x00"

        return {
            "status": "ok",
            "client_message_types": types,
            "observed": observed,
        }
    finally:
        app_server.should_exit = True
        await app_task
        fake_server.close()
        await fake_server.wait_closed()


def main() -> None:
    result = asyncio.run(validate())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
