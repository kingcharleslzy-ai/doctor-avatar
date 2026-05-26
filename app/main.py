from __future__ import annotations

import json
import secrets
import time
import base64
from pathlib import Path

import asyncio

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import settings
from .consultation_flow import ConsultationOrchestrator
from .db import (
    create_memory_entry,
    delete_memory_entries,
    init_memory_db,
    list_memory_entries,
    memory_db_path,
    memory_kind_counts,
)
from .doubao_realtime import (
    AUDIO_SERVER_RESPONSE,
    ClientEvent,
    ServerEvent,
    build_headers,
    build_start_session_payload,
    create_connect_id,
    create_session_id,
    decode_frame,
    doubao_realtime_auth_mode,
    doubao_realtime_missing_fields,
    encode_audio_event,
    encode_json_event,
    is_doubao_realtime_configured,
)
from .knowledge import invalidate_index, load_doctor_profile
from .memory_snapshot import MARKER_KIND, get_memory_status
from .models import (
    MemoryEntryCreate,
    MemoryEntryDeleteRequest,
    MemoryEntryResponse,
    PresenceHeartbeatRequest,
)
from .ops import monitor_snapshot, record_presence, record_request


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(application):
    init_memory_db()
    yield

app = FastAPI(title="Doctor Avatar MVP", version="0.1.0", lifespan=lifespan)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
doctor_profile = load_doctor_profile()
console_auth = HTTPBasic(auto_error=False)
BUILD_META_PATH = Path(__file__).parent / "build_meta.json"
_CACHE_BUST = str(int(time.time()))



def resolve_user_template(request: Request) -> str:
    return "digital_human.html"


def require_console_auth(credentials: HTTPBasicCredentials | None = Depends(console_auth)) -> str:
    if settings.console_auth_mode == "off":
        return "console-auth-disabled"

    if not settings.console_username or not settings.console_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="控制台认证已启用，但尚未配置 CONSOLE_USERNAME / CONSOLE_PASSWORD。",
        )

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="控制台认证失败。",
            headers={"WWW-Authenticate": "Basic"},
        )

    username_ok = secrets.compare_digest(credentials.username, settings.console_username)
    password_ok = secrets.compare_digest(credentials.password, settings.console_password)

    if username_ok and password_ok:
        return credentials.username

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="控制台认证失败。",
        headers={"WWW-Authenticate": "Basic"},
    )


def load_build_meta() -> dict[str, str]:
    defaults = {
        "version": app.version,
        "git_sha": "unknown",
        "git_short_sha": "unknown",
        "ref_name": "local",
        "deployed_at": "unknown",
        "source": "local-dev",
    }
    if not BUILD_META_PATH.exists():
        return defaults

    try:
        payload = json.loads(BUILD_META_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return defaults

    return {
        **defaults,
        **{key: value for key, value in payload.items() if isinstance(value, str) and value},
    }


@app.middleware("http")
async def request_metrics(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - started) * 1000
        record_request(request.url.path, 500, duration_ms)
        raise
    duration_ms = (time.perf_counter() - started) * 1000
    record_request(request.url.path, response.status_code, duration_ms)
    return response


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    return "User-agent: *\nAllow: /\n"


@app.get("/favicon.ico")
def favicon() -> Response:
    svg = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" fill="#171512"/>
  <rect x="45" y="45" width="14" height="14" fill="#0fa18d"/>
  <path d="M16 45V19h6.8l9.2 14.3L41.2 19H48v26h-6.2V29.2L34 41h-4L22.2 29.2V45z" fill="#fbf7ef"/>
</svg>
""".strip()
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/api/app-config")
def app_config() -> dict[str, object]:
    build_meta = load_build_meta()
    memory_entries = list_memory_entries(limit=1)
    memory_code = get_memory_status(memory_db_path())[0] if memory_entries else None
    return {
        "runtime": build_meta,
        "doctor_memory": {
            # db_path removed — don't expose internal filesystem paths
            "bootstrap_enabled": settings.doctor_memory_bootstrap,
            "has_entries": bool(memory_entries),
            "memory_code": memory_code,
            "write_enabled": settings.console_memory_write_enabled,
        },
        "doctor": {
            "name": doctor_profile.get("name"),
            "title": doctor_profile.get("title"),
            "hospital": doctor_profile.get("hospital"),
            "department": doctor_profile.get("department"),
        },
        "doubao_realtime": {
            "enabled": settings.doubao_realtime_enabled,
            "configured": is_doubao_realtime_configured(),
            "auth_mode": doubao_realtime_auth_mode(),
            "missing_fields": doubao_realtime_missing_fields(),
            "model": settings.doubao_realtime_model,
            "input_sample_rate": 16000,
            "output_sample_rate": 24000,
            "output_format": "pcm_s16le",
            "bot_name": settings.doubao_realtime_bot_name,
            "speaker": settings.doubao_realtime_speaker,
            "opening_enabled": bool(settings.doubao_realtime_opening_remark.strip()),
            "websearch_enabled": settings.doubao_realtime_enable_websearch,
        },
    }


@app.get("/api/doctor-profile")
def public_doctor_profile() -> dict[str, object]:
    return {
        "name": doctor_profile.get("name"),
        "title": doctor_profile.get("title"),
        "hospital": doctor_profile.get("hospital"),
        "hospital_alias": doctor_profile.get("hospital_alias"),
        "department": doctor_profile.get("department"),
        "specialty": doctor_profile.get("specialty"),
        "public_tagline": doctor_profile.get("public_tagline"),
        "public_bio": doctor_profile.get("public_bio", []),
        "focus_areas": doctor_profile.get("focus_areas", []),
        "clinical_strengths": doctor_profile.get("clinical_strengths", []),
        "achievements": doctor_profile.get("achievements", []),
        "clinic_note": doctor_profile.get("clinic_note"),
        "address": doctor_profile.get("address"),
        "telephone": doctor_profile.get("telephone"),
        "official_sources": doctor_profile.get("official_sources", []),
    }


@app.get("/api/memory/entries", response_model=list[MemoryEntryResponse])
def memory_entries(
    kind: str | None = None,
    q: str | None = None,
    limit: int = 100,
    _: str = Depends(require_console_auth),
) -> list[MemoryEntryResponse]:
    rows = list_memory_entries(kind=kind, query=q, limit=None)
    if kind != MARKER_KIND:
        rows = [row for row in rows if row["kind"] != MARKER_KIND]
    rows = rows[: max(1, min(limit, 5000))]
    return [MemoryEntryResponse(**row) for row in rows]


@app.get("/api/memory/summary")
def memory_summary(_: str = Depends(require_console_auth)) -> dict[str, object]:
    rows = [row for row in list_memory_entries(limit=None) if row["kind"] != MARKER_KIND]
    counts = [item for item in memory_kind_counts() if item["kind"] != MARKER_KIND]
    return {
        "total": len(rows),
        "kinds": counts,
        "memory_code": get_memory_status(memory_db_path())[0] if rows else None,
    }


@app.get("/api/ops/overview")
def ops_overview(_: str = Depends(require_console_auth)) -> dict[str, object]:
    rows = [row for row in list_memory_entries(limit=None) if row["kind"] != MARKER_KIND]
    counts = [item for item in memory_kind_counts() if item["kind"] != MARKER_KIND]
    snapshot = monitor_snapshot(memory_db_path())
    snapshot["doctor_memory"] = {
        "total": len(rows),
        "kinds": counts,
        "memory_code": get_memory_status(memory_db_path())[0] if rows else None,
        "write_enabled": settings.console_memory_write_enabled,
    }
    return snapshot


@app.post("/api/ops/presence")
def ops_presence(payload: PresenceHeartbeatRequest, request: Request) -> dict[str, str]:
    record_presence(payload.session_id, request.headers.get("user-agent"))
    return {"status": "ok"}


@app.post("/api/memory/entries", response_model=MemoryEntryResponse)
def create_memory(payload: MemoryEntryCreate, _: str = Depends(require_console_auth)) -> MemoryEntryResponse:
    if not settings.console_memory_write_enabled:
        raise HTTPException(status_code=403, detail="当前控制台处于只读模式，已禁用资料写入。")
    row = create_memory_entry(
        kind=payload.kind,
        title=payload.title,
        content=payload.content,
        tags=payload.tags,
        source=payload.source,
        importance=payload.importance,
    )
    get_memory_status(memory_db_path())
    invalidate_index()
    return MemoryEntryResponse(**row)


@app.post("/api/memory/entries/delete")
def delete_memory(payload: MemoryEntryDeleteRequest, _: str = Depends(require_console_auth)) -> dict[str, int | str]:
    if not settings.console_memory_write_enabled:
        raise HTTPException(status_code=403, detail="当前控制台处于只读模式，已禁用资料删除。")
    protected_ids = {
        row["id"]
        for row in list_memory_entries(kind=MARKER_KIND, limit=None)
    }
    candidate_ids = [entry_id for entry_id in payload.entry_ids if entry_id not in protected_ids]
    deleted = delete_memory_entries(candidate_ids)
    get_memory_status(memory_db_path())
    invalidate_index()
    return {"deleted": deleted}


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("hospital_ai.html", {"request": request, "v": _CACHE_BUST})


@app.get("/desktop", response_class=HTMLResponse)
def desktop(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("digital_human.html", {"request": request, "v": _CACHE_BUST})


@app.get("/mobile", response_class=HTMLResponse)
def mobile(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("digital_human.html", {"request": request, "v": _CACHE_BUST})


@app.get("/hospital-ai", response_class=HTMLResponse)
def hospital_ai(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("digital_human.html", {"request": request, "v": _CACHE_BUST})


@app.get("/rhinitis-ai", response_class=HTMLResponse)
def rhinitis_ai(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("rhinitis_ai.html", {"request": request, "v": _CACHE_BUST})


@app.get("/console", response_class=HTMLResponse)
def console(request: Request, _: str = Depends(require_console_auth)) -> HTMLResponse:
    return templates.TemplateResponse("console.html", {"request": request})


@app.websocket("/ws/doubao/realtime")
async def doubao_realtime_ws(ws: WebSocket) -> None:
    await ws.accept()
    if not is_doubao_realtime_configured():
        missing = ", ".join(doubao_realtime_missing_fields())
        await ws.send_json({"type": "error", "message": f"MedFlow 实时语音未配置：{missing}。"})
        await ws.close(code=1008)
        return

    try:
        import websockets
    except Exception:
        await ws.send_json({"type": "error", "message": "缺少 websockets 依赖，无法连接 MedFlow 实时语音。"})
        await ws.close(code=1011)
        return

    connect_id = create_connect_id()
    session_id = create_session_id()
    headers = build_headers(connect_id)
    orchestrator = ConsultationOrchestrator(doctor_profile)

    try:
        async with websockets.connect(
            settings.doubao_realtime_ws_url,
            extra_headers=headers,
            max_size=None,
            open_timeout=10,
            ping_interval=20,
            ping_timeout=20,
        ) as upstream:
            response_headers = getattr(upstream, "response_headers", {}) or {}
            await ws.send_json(
                {
                    "type": "status",
                    "status": "upstream_connected",
                    "connect_id": connect_id,
                    "session_id": session_id,
                    "log_id": response_headers.get("X-Tt-Logid") or response_headers.get("x-tt-logid"),
                }
            )
            upstream_send_lock = asyncio.Lock()
            guided_queries: set[str] = set()
            rag_turn_active = False
            active_tts_type: str | None = None
            pending_chat_end_payload: dict | None = None

            async def _send_json_event(event: int, payload: dict | None = None) -> None:
                async with upstream_send_lock:
                    await upstream.send(encode_json_event(event, payload or {}, session_id=session_id))

            async def _send_audio_event(audio_bytes: bytes) -> None:
                async with upstream_send_lock:
                    await upstream.send(encode_audio_event(ClientEvent.TASK_REQUEST, audio_bytes, session_id=session_id))

            async def _guide_user_query(user_text: str, *, send_rag: bool = True) -> None:
                nonlocal rag_turn_active, active_tts_type
                normalized = " ".join((user_text or "").split()).strip()
                if not normalized or normalized in guided_queries:
                    return
                guided_queries.add(normalized)
                try:
                    turn = await asyncio.to_thread(orchestrator.prepare_turn, normalized)
                    await ws.send_json(
                        {
                            "type": "rag_context",
                            "stage": turn.stage,
                            "stage_label": turn.stage_label,
                            "sources": turn.hit_sources,
                        }
                    )
                    await _send_json_event(ClientEvent.UPDATE_CONFIG, turn.update_config)
                    if send_rag:
                        rag_turn_active = True
                        active_tts_type = None
                        await _send_json_event(ClientEvent.CHAT_RAG_TEXT, {"external_rag": turn.external_rag})
                except Exception as exc:
                    await ws.send_json({"type": "error", "message": f"问诊资料检索失败: {exc}"})

            await upstream.send(encode_json_event(ClientEvent.START_CONNECTION, {}))
            start_payload = build_start_session_payload()
            start_payload["dialog"].update(orchestrator.start_dialog_config())
            await upstream.send(
                encode_json_event(
                    ClientEvent.START_SESSION,
                    start_payload,
                    session_id=session_id,
                )
            )

            async def _upstream_to_browser() -> None:
                nonlocal rag_turn_active, active_tts_type, pending_chat_end_payload
                async for upstream_message in upstream:
                    if isinstance(upstream_message, str):
                        upstream_bytes = upstream_message.encode("utf-8")
                    else:
                        upstream_bytes = bytes(upstream_message)

                    try:
                        frame = decode_frame(upstream_bytes)
                    except Exception as exc:
                        await ws.send_json({"type": "error", "message": f"MedFlow 响应解析失败: {exc}"})
                        continue

                    if frame.message_type == AUDIO_SERVER_RESPONSE or frame.event == ServerEvent.TTS_RESPONSE:
                        if rag_turn_active and active_tts_type not in ("external_rag", "chat_tts_text"):
                            continue
                        await ws.send_json(
                            {
                                "type": "audio",
                                "format": "pcm_s16le",
                                "sample_rate": 24000,
                                "audio": base64.b64encode(frame.payload).decode("ascii"),
                            }
                        )
                        continue

                    payload = {}
                    if frame.payload:
                        try:
                            payload = frame.json_payload()
                        except Exception:
                            payload = {"raw": frame.payload.decode("utf-8", errors="replace")}

                    event = frame.event
                    if event == ServerEvent.CONNECTION_STARTED:
                        await ws.send_json({"type": "status", "status": "connection_started", "payload": payload})
                    elif event == ServerEvent.SESSION_STARTED:
                        await ws.send_json({"type": "status", "status": "session_started", "payload": payload})
                        greeting = settings.doubao_realtime_opening_remark.strip()
                        if greeting:
                            await _send_json_event(ClientEvent.SAY_HELLO, {"content": greeting})
                    elif event in (ServerEvent.CONNECTION_FAILED, ServerEvent.SESSION_FAILED):
                        await ws.send_json({"type": "error", "message": payload.get("error") or "MedFlow 实时语音连接失败。"})
                    elif event == ServerEvent.ASR_INFO:
                        await ws.send_json({"type": "asr_start", "payload": payload})
                    elif event == ServerEvent.ASR_RESPONSE:
                        results = payload.get("results") or []
                        best = results[-1] if results else {}
                        best_text = best.get("text", "")
                        is_interim = bool(best.get("is_interim"))
                        await ws.send_json(
                            {
                                "type": "asr",
                                "text": best_text,
                                "is_interim": is_interim,
                                "payload": payload,
                            }
                        )
                        if best_text and not is_interim:
                            await _guide_user_query(best_text)
                    elif event == ServerEvent.ASR_ENDED:
                        await ws.send_json({"type": "asr_end", "payload": payload})
                    elif event == ServerEvent.CHAT_RESPONSE:
                        if rag_turn_active:
                            continue
                        await ws.send_json(
                            {
                                "type": "chat",
                                "content": payload.get("content", ""),
                                "question_id": payload.get("question_id"),
                                "reply_id": payload.get("reply_id"),
                                "payload": payload,
                            }
                        )
                    elif event == ServerEvent.CHAT_ENDED:
                        if rag_turn_active:
                            continue
                        pending_chat_end_payload = payload
                    elif event == ServerEvent.TTS_SENTENCE_START:
                        active_tts_type = str(payload.get("tts_type") or "")
                        if rag_turn_active and active_tts_type not in ("external_rag", "chat_tts_text"):
                            continue
                        if rag_turn_active and payload.get("text"):
                            await ws.send_json(
                                {
                                    "type": "chat",
                                    "content": payload.get("text", ""),
                                    "question_id": payload.get("question_id"),
                                    "reply_id": payload.get("reply_id"),
                                    "payload": payload,
                                }
                            )
                        await ws.send_json({"type": "tts_start", "text": payload.get("text", ""), "payload": payload})
                    elif event == ServerEvent.TTS_SENTENCE_END:
                        await ws.send_json({"type": "tts_sentence_end", "payload": payload})
                    elif event == ServerEvent.TTS_ENDED:
                        if payload.get("status_code") == "20000002":
                            await ws.send_json({"type": "status", "status": "user_exit_intent", "payload": payload})
                        if rag_turn_active and active_tts_type in ("external_rag", "chat_tts_text"):
                            rag_turn_active = False
                            await ws.send_json({"type": "chat_end", "payload": payload})
                            active_tts_type = None
                        elif pending_chat_end_payload is not None:
                            await ws.send_json({"type": "chat_end", "payload": pending_chat_end_payload})
                            pending_chat_end_payload = None
                        await ws.send_json({"type": "tts_end", "payload": payload})
                    elif event == ServerEvent.USAGE_RESPONSE:
                        await ws.send_json({"type": "usage", "payload": payload})
                    elif event in (ServerEvent.SESSION_FINISHED, ServerEvent.CONNECTION_FINISHED):
                        if pending_chat_end_payload is not None:
                            await ws.send_json({"type": "chat_end", "payload": pending_chat_end_payload})
                            pending_chat_end_payload = None
                        await ws.send_json({"type": "status", "status": "finished", "payload": payload})
                        return
                    else:
                        await ws.send_json({"type": "event", "event": event, "payload": payload})

            async def _browser_to_upstream() -> None:
                while True:
                    message = await ws.receive()
                    if message["type"] == "websocket.disconnect":
                        return

                    audio_bytes = message.get("bytes")
                    if audio_bytes:
                        await _send_audio_event(audio_bytes)
                        continue

                    text = message.get("text")
                    if not text:
                        continue

                    try:
                        payload = json.loads(text)
                    except json.JSONDecodeError:
                        await ws.send_json({"type": "error", "message": "浏览器消息不是有效 JSON。"})
                        continue

                    msg_type = payload.get("type")
                    if msg_type == "end_asr":
                        await _send_json_event(ClientEvent.END_ASR, {})
                    elif msg_type == "interrupt":
                        await _send_json_event(ClientEvent.CLIENT_INTERRUPT, {})
                    elif msg_type == "text":
                        content = str(payload.get("content") or "").strip()
                        if content:
                            await _guide_user_query(content)
                    elif msg_type == "say_hello":
                        content = str(payload.get("content") or "").strip()
                        if content:
                            await _send_json_event(ClientEvent.SAY_HELLO, {"content": content})
                    elif msg_type == "finish":
                        await _send_json_event(ClientEvent.FINISH_SESSION, {})
                        async with upstream_send_lock:
                            await upstream.send(encode_json_event(ClientEvent.FINISH_CONNECTION, {}))
                        return

            tasks = [
                asyncio.create_task(_upstream_to_browser()),
                asyncio.create_task(_browser_to_upstream()),
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await ws.send_json({"type": "error", "message": f"MedFlow 实时语音代理异常: {exc}"})
        except Exception:
            pass
        try:
            await ws.close(code=1011)
        except Exception:
            pass
