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
    os.environ["DOUBAO_REALTIME_MODEL"] = "1.2.1.1"
    os.environ["DOUBAO_REALTIME_SPEAKER"] = "zh_male_yunzhou_jupiter_bigtts"


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
                {"results": [{"text": "我有点鼻塞", "is_interim": False}]},
                session_id,
            )
        )
        await ws.send(encode_server_json_event(ServerEvent.ASR_ENDED, {}, session_id))

        while "direct_question_event" not in observed and "rag_event" not in observed:
            frame = decode_frame(await ws.recv())
            if frame.event == ClientEvent.UPDATE_CONFIG:
                observed["update_config_event"] = frame.event
                observed["update_config_payload"] = frame.json_payload()
                await ws.send(encode_server_json_event(ServerEvent.CONFIG_UPDATED, {}, session_id))
            elif frame.event == ClientEvent.CHAT_RAG_TEXT:
                observed["rag_event"] = frame.event
                observed["rag_payload"] = frame.json_payload()
            elif frame.event == ClientEvent.SAY_HELLO:
                observed["direct_question_event"] = frame.event
                observed["direct_question_payload"] = frame.json_payload()
            else:
                observed.setdefault("post_asr_client_events", []).append(frame.event)

        await ws.send(
            encode_server_json_event(
                ServerEvent.TTS_SENTENCE_START,
                {
                    "text": "这个情况先看鼻塞持续多久，有没有喷嚏流涕和过敏诱因。",
                    "tts_type": "external_rag",
                    "question_id": "q1",
                    "reply_id": "r1",
                },
                session_id,
            )
        )
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

        assert observed["headers"]["api_key"] == "test-api-key"
        assert observed["headers"]["app_id"] is None
        assert observed["headers"]["access_key"] is None
        assert observed["headers"]["resource_id"] == "volc.speech.dialog"
        assert observed["start_connection_event"] == 1
        assert observed["start_session_event"] == 100
        assert observed["start_session_payload"]["dialog"]["extra"]["model"] == "1.2.1.1"
        assert observed["say_hello_event"] == 300
        assert observed["audio_event"] == 200
        assert observed["audio_payload_len"] == 640
        assert observed["update_config_event"] == 201
        assert observed.get("direct_question_event") == 300 or observed.get("rag_event") == 502
        if "direct_question_payload" in observed:
            assert observed["direct_question_payload"]["content"].count("？") <= 1
        if "rag_payload" in observed:
            assert "external_rag" in observed["rag_payload"]

        types = [message.get("type") for message in messages]
        assert "status" in types
        assert "asr" in types
        assert "rag_context" in types
        assert "chat" in types
        assert "audio" in types, {"types": types, "messages": messages, "observed": observed}
        assert "chat_end" in types

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
