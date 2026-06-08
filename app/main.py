from __future__ import annotations

import json
import time
import base64
import re
from pathlib import Path

import asyncio

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import settings
from .consultation_flow import ConsultationOrchestrator
from .db import (
    init_memory_db,
    list_memory_entries,
    memory_db_path,
)
from .doubao_realtime import (
    AUDIO_SERVER_RESPONSE,
    ClientEvent,
    ServerEvent,
    adapt_dialog_persona,
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
from .knowledge import load_doctor_profile
from .memory_snapshot import get_memory_status
from .models import PresenceHeartbeatRequest, RhinitisEvidenceBatchReviewRequest, RhinitisEvidenceReviewRequest
from .ops import record_presence, record_request
from .rhinitis_evidence import (
    evidence_stats,
    get_evidence_document,
    init_rhinitis_evidence_db,
    review_evidence_batch,
    review_pack,
    review_queue,
    review_evidence_document,
    search_evidence,
)


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(application):
    init_memory_db()
    init_rhinitis_evidence_db()
    yield

app = FastAPI(title="Doctor Avatar MVP", version="0.1.0", lifespan=lifespan)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
doctor_profile = load_doctor_profile()
BUILD_META_PATH = Path(__file__).parent / "build_meta.json"
_CACHE_BUST = str(int(time.time()))
_REALTIME_ECHO_WINDOW_SECONDS = 20.0
_REALTIME_ECHO_MIN_CHARS = 4
_REALTIME_ECHO_PUNCT_RE = re.compile(r"[\s，。！？；：、,.!?;:]+")


def _normalize_realtime_echo_text(text: str) -> str:
    return _REALTIME_ECHO_PUNCT_RE.sub("", str(text or "")).strip().lower()



def resolve_user_template(request: Request) -> str:
    return "digital_human.html"


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


@app.get("/api/rhinitis/evidence/stats")
def rhinitis_evidence_stats() -> dict[str, object]:
    return evidence_stats()


@app.get("/api/rhinitis/evidence/search")
def rhinitis_evidence_search(
    q: str = Query(default="", max_length=240),
    scope: str = Query(default="curated", pattern="^(raw|curated)$"),
    scenario: str = Query(default="", max_length=80),
    source_bucket: str = Query(default="", max_length=120),
    limit: int = Query(default=8, ge=1, le=20),
) -> dict[str, object]:
    return search_evidence(q, scope=scope, scenario=scenario, source_bucket=source_bucket, limit=limit)


@app.get("/api/rhinitis/evidence/review-queue")
def rhinitis_evidence_review_queue(
    status: str = Query(default="needs_review", pattern="^(candidate|needs_review|approved|rejected|deprecated)$"),
    source_bucket: str = Query(default="", max_length=120),
    evidence_level: str = Query(default="", max_length=80),
    topic_tag: str = Query(default="", max_length=80),
    limit: int = Query(default=12, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> dict[str, object]:
    return review_queue(
        status=status,
        source_bucket=source_bucket,
        evidence_level=evidence_level,
        topic_tag=topic_tag,
        limit=limit,
        offset=offset,
    )


@app.get("/api/rhinitis/evidence/review-pack")
def rhinitis_evidence_review_pack() -> dict[str, object]:
    return review_pack()


@app.get("/api/rhinitis/evidence/documents/{document_id}")
def rhinitis_evidence_document(
    document_id: int,
    scope: str = Query(default="raw", pattern="^(raw|curated)$"),
) -> dict[str, object]:
    document = get_evidence_document(document_id, scope=scope)
    if not document:
        raise HTTPException(status_code=404, detail="Rhinitis evidence document not found")
    return document


@app.post("/api/rhinitis/evidence/review")
def rhinitis_evidence_review(payload: RhinitisEvidenceReviewRequest) -> dict[str, object]:
    if not settings.rhinitis_evidence_review_enabled:
        raise HTTPException(status_code=403, detail="Rhinitis evidence review writes are disabled.")
    try:
        return review_evidence_document(
            document_scope=payload.document_scope,
            document_id=payload.document_id,
            status=payload.status,
            note=payload.note,
            reviewer=payload.reviewer,
            patient_visible=payload.patient_visible,
            doctor_visible=payload.doctor_visible,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/rhinitis/evidence/review-batch")
def rhinitis_evidence_review_batch(payload: RhinitisEvidenceBatchReviewRequest) -> dict[str, object]:
    if not settings.rhinitis_evidence_review_enabled:
        raise HTTPException(status_code=403, detail="Rhinitis evidence review writes are disabled.")
    try:
        return review_evidence_batch(
            document_ids=payload.document_ids,
            status=payload.status,
            note=payload.note,
            reviewer=payload.reviewer,
            patient_visible=payload.patient_visible,
            doctor_visible=payload.doctor_visible,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/ops/presence")
def ops_presence(payload: PresenceHeartbeatRequest, request: Request) -> dict[str, str]:
    record_presence(payload.session_id, request.headers.get("user-agent"))
    return {"status": "ok"}


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


@app.get("/rhinitis-evidence", response_class=HTMLResponse)
def rhinitis_evidence_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("rhinitis_evidence.html", {"request": request, "v": _CACHE_BUST, "mode": "search"})


@app.get("/rhinitis-review", response_class=HTMLResponse)
def rhinitis_review_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("rhinitis_evidence.html", {"request": request, "v": _CACHE_BUST, "mode": "review"})


@app.websocket("/ws/doubao/realtime")
async def doubao_realtime_ws(ws: WebSocket) -> None:
    mode = (ws.query_params.get("mode") or "voice").strip().lower()
    should_send_opening = mode != "text"
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
            session_ready = asyncio.Event()
            last_guided_query = ""
            last_guided_at = 0.0
            rag_turn_active = False
            active_tts_type: str | None = None
            pending_chat_end_payload: dict | None = None
            pending_voice_query = ""
            recent_assistant_texts: list[tuple[str, float]] = []

            def _remember_assistant_text(content: str) -> None:
                normalized = _normalize_realtime_echo_text(content)
                if len(normalized) < _REALTIME_ECHO_MIN_CHARS:
                    return
                now = time.monotonic()
                recent_assistant_texts[:] = [
                    (text, ts)
                    for text, ts in recent_assistant_texts
                    if now - ts <= _REALTIME_ECHO_WINDOW_SECONDS
                ]
                recent_assistant_texts.append((normalized, now))
                del recent_assistant_texts[:-8]

            def _is_recent_assistant_echo(content: str) -> bool:
                normalized = _normalize_realtime_echo_text(content)
                if len(normalized) < _REALTIME_ECHO_MIN_CHARS:
                    return False
                now = time.monotonic()
                recent_assistant_texts[:] = [
                    (text, ts)
                    for text, ts in recent_assistant_texts
                    if now - ts <= _REALTIME_ECHO_WINDOW_SECONDS
                ]
                for assistant_text, _ in recent_assistant_texts:
                    if normalized == assistant_text:
                        return True
                    if len(normalized) >= 8 and (normalized in assistant_text or assistant_text in normalized):
                        return True
                return False

            def _should_send_direct_response(turn) -> bool:
                return bool(getattr(turn, "direct_response", ""))

            async def _send_direct_response(turn) -> None:
                nonlocal rag_turn_active, active_tts_type, pending_chat_end_payload
                content = turn.direct_response
                _remember_assistant_text(content)
                rag_turn_active = False
                active_tts_type = None
                pending_chat_end_payload = {"direct_response": True, "stage": turn.stage}
                await ws.send_json(
                    {
                        "type": "chat",
                        "content": content,
                        "question_id": None,
                        "reply_id": None,
                        "payload": pending_chat_end_payload,
                    }
                )
                await _send_json_event(ClientEvent.SAY_HELLO, {"content": content})

            async def _wait_session_ready() -> bool:
                if session_ready.is_set():
                    return True
                try:
                    await asyncio.wait_for(session_ready.wait(), timeout=10)
                except asyncio.TimeoutError:
                    await ws.send_json({"type": "error", "message": "MedFlow 实时语音会话尚未就绪，请稍后重试。"})
                    return False
                return True

            async def _send_json_event(event: int, payload: dict | None = None) -> None:
                if not await _wait_session_ready():
                    return
                async with upstream_send_lock:
                    await upstream.send(encode_json_event(event, payload or {}, session_id=session_id))

            async def _send_audio_event(audio_bytes: bytes) -> None:
                if not await _wait_session_ready():
                    return
                async with upstream_send_lock:
                    await upstream.send(encode_audio_event(ClientEvent.TASK_REQUEST, audio_bytes, session_id=session_id))

            async def _guide_user_query(
                user_text: str,
                *,
                send_rag: bool = True,
                update_config_enabled: bool = True,
                allow_direct_response: bool = True,
                voice_rag: bool = False,
            ):
                nonlocal rag_turn_active, active_tts_type, pending_chat_end_payload, last_guided_query, last_guided_at
                normalized = " ".join((user_text or "").split()).strip()
                if not normalized:
                    return None
                now = asyncio.get_running_loop().time()
                if normalized == last_guided_query and now - last_guided_at < 1.2:
                    return None
                last_guided_query = normalized
                last_guided_at = now
                try:
                    prepare = orchestrator.prepare_voice_rag_turn if voice_rag else orchestrator.prepare_turn
                    turn = await asyncio.to_thread(prepare, normalized)
                    update_config = dict(turn.update_config)
                    if isinstance(update_config.get("dialog"), dict):
                        update_config["dialog"] = adapt_dialog_persona(update_config["dialog"])
                    await ws.send_json(
                        {
                            "type": "rag_context",
                            "stage": turn.stage,
                            "stage_label": turn.stage_label,
                            "sources": turn.hit_sources,
                        }
                    )
                    if update_config_enabled and update_config:
                        await _send_json_event(ClientEvent.UPDATE_CONFIG, update_config)
                    if send_rag and allow_direct_response and _should_send_direct_response(turn):
                        await _send_direct_response(turn)
                    elif send_rag:
                        rag_turn_active = True
                        active_tts_type = None
                        pending_chat_end_payload = None
                        await _send_json_event(ClientEvent.CHAT_RAG_TEXT, {"external_rag": turn.external_rag})
                    return turn
                except Exception as exc:
                    await ws.send_json({"type": "error", "message": f"问诊资料检索失败: {exc}"})
                    return None

            await upstream.send(encode_json_event(ClientEvent.START_CONNECTION, {}))
            start_payload = build_start_session_payload()
            start_payload["dialog"].update(adapt_dialog_persona(orchestrator.start_dialog_config()))
            await upstream.send(
                encode_json_event(
                    ClientEvent.START_SESSION,
                    start_payload,
                    session_id=session_id,
                )
            )

            async def _upstream_to_browser() -> None:
                nonlocal rag_turn_active, active_tts_type, pending_chat_end_payload, pending_voice_query
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
                        session_ready.set()
                        await ws.send_json({"type": "status", "status": "session_started", "payload": payload})
                        greeting = settings.doubao_realtime_opening_remark.strip()
                        if greeting and should_send_opening:
                            _remember_assistant_text(greeting)
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
                        if best_text and _is_recent_assistant_echo(best_text):
                            continue
                        await ws.send_json(
                            {
                                "type": "asr",
                                "text": best_text,
                                "is_interim": is_interim,
                                "payload": payload,
                            }
                        )
                        if best_text and not is_interim and mode == "voice":
                            pending_voice_query = best_text
                        elif best_text and not is_interim:
                            await _guide_user_query(best_text)
                    elif event == ServerEvent.ASR_ENDED:
                        await ws.send_json({"type": "asr_end", "payload": payload})
                        if mode == "voice" and pending_voice_query:
                            user_query = pending_voice_query
                            pending_voice_query = ""
                            await _guide_user_query(
                                user_query,
                                update_config_enabled=False,
                                allow_direct_response=False,
                                voice_rag=True,
                            )
                    elif event == ServerEvent.CHAT_RESPONSE:
                        if rag_turn_active:
                            continue
                        _remember_assistant_text(payload.get("content", ""))
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
                        _remember_assistant_text(payload.get("text", ""))
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
                            turn = await _guide_user_query(content, send_rag=False)
                            if turn and _should_send_direct_response(turn):
                                await _send_direct_response(turn)
                            elif turn:
                                await _send_json_event(ClientEvent.CHAT_TEXT_QUERY, {"content": content})
                    elif msg_type == "say_hello":
                        content = str(payload.get("content") or "").strip()
                        if content:
                            _remember_assistant_text(content)
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
