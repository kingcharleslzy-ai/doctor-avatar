from __future__ import annotations

import io
import json
import secrets
import time
from pathlib import Path

import asyncio

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import settings
from .db import create_memory_entry, delete_memory_entries, init_memory_db, list_memory_entries, memory_kind_counts
from .knowledge import invalidate_index, load_doctor_profile, search_knowledge
from .memory_snapshot import MARKER_KIND, get_memory_status
from .models import (
    ChatRequest,
    ChatResponse,
    DittoGenerateRequest,
    LiveAvatarSessionRequest,
    LiveAvatarStartRequest,
    LiveAvatarTokenResponse,
    MemoryEntryCreate,
    MemoryEntryDeleteRequest,
    MemoryEntryResponse,
    PresenceHeartbeatRequest,
    TTSRequest,
)
from .ops import monitor_snapshot, record_presence, record_request
from .speech import SpeechService
from .stt import TranscriptionService
from .services import ChatService, HeyGenService


from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(application):
    init_memory_db()
    yield

app = FastAPI(title="Doctor Avatar MVP", version="0.1.0", lifespan=lifespan)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
chat_service = ChatService()
heygen_service = HeyGenService()
speech_service = SpeechService()
transcription_service = TranscriptionService()
doctor_profile = load_doctor_profile()
console_auth = HTTPBasic(auto_error=False)
BUILD_META_PATH = Path(__file__).parent / "build_meta.json"
_CACHE_BUST = str(int(time.time()))



def resolve_user_template(request: Request) -> str:
    view = request.query_params.get("view")
    if view == "mobile":
        return "user_mobile.html"
    if view == "desktop":
        return "user_desktop.html"
    user_agent = (request.headers.get("user-agent") or "").lower()
    mobile_markers = (
        "iphone",
        "ipad",
        "android",
        "mobile",
        "harmonyos",
        "micromessenger",
    )
    if any(marker in user_agent for marker in mobile_markers):
        return "user_mobile.html"
    return "user_desktop.html"


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
  <defs>
    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#2563eb"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="18" fill="url(#g)"/>
  <path d="M20 18h7v12h10V18h7v28h-7V36H27v10h-7z" fill="#ffffff"/>
</svg>
""".strip()
    return Response(content=svg, media_type="image/svg+xml")


@app.get("/api/app-config")
def app_config() -> dict[str, object]:
    build_meta = load_build_meta()
    memory_entries = list_memory_entries(limit=1)
    memory_code = get_memory_status(Path(settings.doctor_memory_db_path))[0] if memory_entries else None
    return {
        "openai_configured": bool(settings.openai_api_key),
        "heygen_configured": bool(settings.heygen_api_key),
        "video_avatar_enabled": settings.enable_video_avatar,
        "ditto_enabled": settings.ditto_enabled,
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
        "ditto_stream": {
            "enabled": settings.ditto_stream_enabled,
            "ws_url_configured": bool(settings.ditto_ws_url),
        },
        "stt": transcription_service.provider_status(),
        "tts": speech_service.provider_status(),
        "liveavatar": {
            "mode": settings.heygen_mode,
            "language": settings.heygen_language,
            "sandbox": settings.heygen_use_sandbox,
            "push_to_talk": settings.heygen_push_to_talk,
            "avatar_configured": bool(settings.heygen_avatar_id),
            "voice_configured": bool(settings.heygen_voice_id),
            "context_configured": bool(settings.heygen_context_id),
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
        "memory_code": get_memory_status(Path(settings.doctor_memory_db_path))[0] if rows else None,
    }


@app.get("/api/ops/overview")
def ops_overview(_: str = Depends(require_console_auth)) -> dict[str, object]:
    rows = [row for row in list_memory_entries(limit=None) if row["kind"] != MARKER_KIND]
    counts = [item for item in memory_kind_counts() if item["kind"] != MARKER_KIND]
    snapshot = monitor_snapshot(Path(settings.doctor_memory_db_path))
    snapshot["doctor_memory"] = {
        "total": len(rows),
        "kinds": counts,
        "memory_code": get_memory_status(Path(settings.doctor_memory_db_path))[0] if rows else None,
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
    get_memory_status(Path(settings.doctor_memory_db_path))
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
    get_memory_status(Path(settings.doctor_memory_db_path))
    invalidate_index()
    return {"deleted": deleted}


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(resolve_user_template(request), {"request": request, "v": _CACHE_BUST})


@app.get("/desktop", response_class=HTMLResponse)
def desktop(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("user_desktop.html", {"request": request, "v": _CACHE_BUST})


@app.get("/mobile", response_class=HTMLResponse)
def mobile(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("user_mobile.html", {"request": request, "v": _CACHE_BUST})


@app.get("/hospital-ai", response_class=HTMLResponse)
def hospital_ai(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("hospital_ai.html", {"request": request, "v": _CACHE_BUST})


@app.get("/console", response_class=HTMLResponse)
def console(request: Request, _: str = Depends(require_console_auth)) -> HTMLResponse:
    return templates.TemplateResponse("console.html", {"request": request})


@app.post("/api/voice-chat")
async def voice_chat(payload: ChatRequest):
    """流式语音聊天：DeepSeek streaming → 句级 Edge TTS → SSE 返回文本+音频。
    前端只需一个请求，就能实现"边说边听"的实时通话体验。"""
    import base64
    import re
    import edge_tts
    from fastapi.responses import StreamingResponse

    if chat_service.client is None:
        raise HTTPException(status_code=503, detail="Chat 未配置。")

    hits = search_knowledge(payload.message)
    snippets = [hit.snippet for hit in hits]

    async def _tts_bytes(text: str) -> bytes:
        voice = settings.edge_tts_voice or "zh-CN-YunjianNeural"
        communicate = edge_tts.Communicate(text, voice, rate="+10%", pitch="-5Hz")
        buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return buf.getvalue()

    async def _generate():
        from .prompts import build_system_prompt, build_user_prompt
        from .ops import record_openai_usage, record_openai_error

        # Handle memory-code special case (same as ChatService.answer)
        if chat_service._looks_like_memory_code_request(payload.message):
            code_answer = chat_service._answer_memory_code()
            if code_answer:
                text = code_answer["answer"]
                yield f"data: {json.dumps({'type': 'text', 'token': text}, ensure_ascii=False)}\n\n"
                try:
                    audio = await _tts_bytes(text)
                    audio_b64 = base64.b64encode(audio).decode()
                    yield f"data: {json.dumps({'type': 'audio', 'index': 1, 'audio': audio_b64, 'format': 'audio/mpeg'}, ensure_ascii=False)}\n\n"
                except Exception:
                    pass
                yield f"data: {json.dumps({'type': 'done', 'full_text': text}, ensure_ascii=False)}\n\n"
                return

        try:
            stream = chat_service.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": build_system_prompt(chat_service.profile)},
                    *payload.conversation,
                    {"role": "user", "content": build_user_prompt(payload.message, snippets)},
                ],
                stream=True,
            )
        except Exception:
            record_openai_error()
            raise

        full_text = ""
        sentence_buf = ""
        sent_count = 0
        sentence_ends = re.compile(r'[。！？\n.!?]')
        MIN_TTS_LEN = 8

        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta.content:
                token = delta.content
                full_text += token
                sentence_buf += token

                # Send text token immediately for live display
                yield f"data: {json.dumps({'type': 'text', 'token': token}, ensure_ascii=False)}\n\n"

                # Check if we completed a sentence (and it's long enough)
                if sentence_ends.search(token) and len(sentence_buf.strip()) >= MIN_TTS_LEN:
                    sentence = sentence_buf.strip()
                    sentence_buf = ""
                    sent_count += 1
                    try:
                        audio = await _tts_bytes(sentence)
                        audio_b64 = base64.b64encode(audio).decode()
                        yield f"data: {json.dumps({'type': 'audio', 'index': sent_count, 'audio': audio_b64, 'format': 'audio/mpeg'}, ensure_ascii=False)}\n\n"
                    except Exception:
                        pass  # Skip TTS errors, text still shows

        # Handle remaining text
        if sentence_buf.strip() and len(sentence_buf.strip()) > 2:
            sent_count += 1
            try:
                audio = await _tts_bytes(sentence_buf.strip())
                audio_b64 = base64.b64encode(audio).decode()
                yield f"data: {json.dumps({'type': 'audio', 'index': sent_count, 'audio': audio_b64, 'format': 'audio/mpeg'}, ensure_ascii=False)}\n\n"
            except Exception:
                pass

        yield f"data: {json.dumps({'type': 'done', 'full_text': full_text}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    try:
        result = chat_service.answer(payload.message, payload.conversation)
    except Exception as exc:  # pragma: no cover - runtime integration fallback
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ChatResponse(**result)


@app.post("/api/stt")
async def speech_to_text(request: Request) -> dict[str, str]:
    if not (settings.stt_api_key or settings.openai_api_key):
        raise HTTPException(status_code=503, detail="语音识别 API key 未配置。")
    form = await request.form()
    audio_file = form.get("audio")
    if audio_file is None:
        raise HTTPException(status_code=400, detail="缺少音频文件。")
    try:
        audio_bytes = await audio_file.read()
        filename = getattr(audio_file, "filename", None) or "audio.webm"
        result = await transcription_service.transcribe(audio_bytes, filename=filename)
        return {
            "text": result.text,
            "provider": result.provider,
            "model": result.model,
        }
    except Exception as exc:
        message = str(exc).lower()
        if "authentication" in message or "unauthorized" in message or "invalid api key" in message or "invalid_api_key" in message:
            raise HTTPException(
                status_code=503,
                detail="语音识别服务认证失败，请检查服务器上的 STT_API_KEY 是否为有效的 OpenAI API key。",
            ) from exc
        raise HTTPException(status_code=500, detail=f"语音识别失败: {exc}") from exc


@app.post("/api/tts")
async def text_to_speech(payload: TTSRequest) -> Response:
    try:
        result = await speech_service.synthesize(
            payload.text,
            provider=payload.provider,
            voice=payload.voice,
        )
        return Response(
            content=result.audio,
            media_type=result.media_type,
            headers={
                "X-TTS-Provider": result.provider,
                "X-TTS-Voice": result.voice,
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"TTS 失败: {exc}") from exc


@app.post("/api/tts/stream")
async def text_to_speech_stream(payload: TTSRequest):
    """流式 TTS：边生成边返回 MP3 音频块，首包延迟 <400ms。默认走 Edge TTS。"""
    from fastapi.responses import StreamingResponse
    import edge_tts

    voice = payload.voice or settings.edge_tts_voice or "zh-CN-YunjianNeural"

    async def _generate():
        communicate = edge_tts.Communicate(payload.text, voice, rate="+10%", pitch="-5Hz")
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                yield chunk["data"]

    return StreamingResponse(
        _generate(),
        media_type="audio/mpeg",
        headers={
            "X-TTS-Provider": "edge-stream",
            "X-TTS-Voice": voice,
            "Cache-Control": "no-cache",
        },
    )


def _ditto_clip_text(text: str, max_chars: int = 60) -> str:
    """取第一个完整句子（不超过 max_chars 字），用于 Ditto 生成短片段而非全文。"""
    for ch in "。！？.!?":
        idx = text.find(ch)
        if 0 < idx < max_chars:
            return text[: idx + 1]
    return text[:max_chars]


@app.post("/api/ditto/generate")
async def ditto_generate(payload: DittoGenerateRequest) -> Response:
    if not settings.ditto_enabled:
        raise HTTPException(status_code=409, detail="Ditto 视频生成未启用。")
    try:
        clip_text = _ditto_clip_text(payload.text)
        speech = await speech_service.synthesize(clip_text)
        audio_buf = io.BytesIO(speech.audio)
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{settings.ditto_service_url}/generate",
                files={
                    "audio": (
                        f"audio{'.wav' if speech.media_type.endswith('wav') else '.mp3'}",
                        audio_buf,
                        speech.media_type,
                    )
                },
            )
        if resp.status_code != 200:
            raise HTTPException(status_code=500, detail=f"Ditto 服务错误: {resp.text[:300]}")
        return Response(content=resp.content, media_type="video/mp4")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"视频生成失败: {exc}") from exc


@app.post("/api/liveavatar/token", response_model=LiveAvatarTokenResponse)
async def liveavatar_token(
    payload: LiveAvatarSessionRequest | None = None,
    _: str = Depends(require_console_auth),
) -> LiveAvatarTokenResponse:
    if not settings.enable_video_avatar:
        raise HTTPException(status_code=409, detail="视频分身能力当前未启用。")
    payload = payload or LiveAvatarSessionRequest()
    request_payload = {
        "mode": payload.mode or settings.heygen_mode,
        "avatar_id": payload.avatar_id or settings.heygen_avatar_id,
        "is_sandbox": payload.is_sandbox if payload.is_sandbox is not None else settings.heygen_use_sandbox,
        "avatar_persona": {
            "voice_id": payload.voice_id or settings.heygen_voice_id,
            "context_id": payload.context_id or settings.heygen_context_id,
            "language": payload.language or settings.heygen_language,
        },
        **(
            payload.extra
            if payload.extra
            else ({"interactivity_type": "PUSH_TO_TALK"} if settings.heygen_push_to_talk else {})
        ),
    }
    avatar_persona = {key: value for key, value in request_payload["avatar_persona"].items() if value is not None}
    if avatar_persona:
        request_payload["avatar_persona"] = avatar_persona
    else:
        request_payload.pop("avatar_persona")
    request_payload = {key: value for key, value in request_payload.items() if value is not None}

    try:
        result = await heygen_service.create_liveavatar_token(request_payload)
    except Exception as exc:  # pragma: no cover - runtime integration fallback
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return LiveAvatarTokenResponse(data=result)


@app.post("/api/liveavatar/session", response_model=LiveAvatarTokenResponse)
async def liveavatar_session(
    payload: LiveAvatarStartRequest,
    _: str = Depends(require_console_auth),
) -> LiveAvatarTokenResponse:
    if not settings.enable_video_avatar:
        raise HTTPException(status_code=409, detail="视频分身能力当前未启用。")
    try:
        result = await heygen_service.start_liveavatar_session(payload.session_token)
    except Exception as exc:  # pragma: no cover - runtime integration fallback
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return LiveAvatarTokenResponse(data=result)


# ---------------------------------------------------------------------------
# Ditto 流式 WebSocket 端点
# 协议：
#   浏览器 → 服务端：JSON {"text": "..."} 触发一次流式请求
#   服务端 → 4090D：原始 PCM bytes（16kHz mono 16-bit），最后发 b"END"
#   4090D → 服务端：JPEG 帧（bytes）或 JSON {"done":true}
#   服务端 → 浏览器：转发 JPEG bytes；会话结束发 JSON {"done":true}
# ---------------------------------------------------------------------------
@app.websocket("/ws/ditto/stream")
async def ditto_ws_stream(ws: WebSocket) -> None:
    await ws.accept()
    try:
        if not settings.ditto_stream_enabled:
            await ws.send_json({"error": "流式视频未启用。"})
            await ws.close(code=1008)
            return

        # 1. 从浏览器接收待合成文本
        try:
            msg = await asyncio.wait_for(ws.receive_json(), timeout=10.0)
        except asyncio.TimeoutError:
            await ws.close(code=1008)
            return
        text = (msg.get("text") or "").strip()
        if not text:
            await ws.close(code=1003)
            return

        # 2. edge-tts → MP3 → ffmpeg → 16kHz mono PCM WAV
        speech = await speech_service.synthesize(text)
        audio_bytes = speech.audio

        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", "pipe:0",
            "-ar", "16000", "-ac", "1", "-f", "wav", "pipe:1",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        wav_data, _ = await proc.communicate(input=audio_bytes)
        if not wav_data or len(wav_data) <= 44:
            await ws.send_json({"error": "TTS 转换失败。"})
            await ws.close(code=1011)
            return

        pcm_data = wav_data[44:]  # 跳过 WAV 头，取裸 PCM

        # 3. 连接 4090D 流式服务
        import websockets as _ws_lib
        try:
            ditto_conn = await _ws_lib.connect(
                settings.ditto_ws_url,
                max_size=20 * 1024 * 1024,
                open_timeout=10,
            )
        except Exception as exc:
            await ws.send_json({"error": f"无法连接 Ditto 流式服务：{exc}"})
            await ws.close(code=1011)
            return

        try:
            CHUNK = int(0.4 * 16000 * 2)  # 0.4s × 16kHz × 2bytes = 12800 bytes

            async def _send() -> None:
                for i in range(0, len(pcm_data), CHUNK):
                    await ditto_conn.send(pcm_data[i : i + CHUNK])
                    await asyncio.sleep(0.01)
                await ditto_conn.send(b"END")

            async def _recv() -> None:
                async for frame in ditto_conn:
                    if isinstance(frame, bytes):
                        await ws.send_bytes(frame)
                    else:
                        try:
                            payload = json.loads(frame)
                        except Exception:
                            payload = {}
                        if payload.get("done"):
                            await ws.send_json({"done": True})
                            return

            results = await asyncio.gather(_send(), _recv(), return_exceptions=True)
            for r in results:
                if isinstance(r, BaseException) and not isinstance(r, asyncio.CancelledError):
                    raise r
        finally:
            await ditto_conn.close()

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await ws.send_json({"error": str(exc)})
        except Exception:
            pass
    finally:
        try:
            await ws.close()
        except Exception:
            pass


@app.get("/api/liveavatar/sessions", response_model=LiveAvatarTokenResponse)
async def liveavatar_sessions(_: str = Depends(require_console_auth)) -> LiveAvatarTokenResponse:
    if not settings.enable_video_avatar:
        raise HTTPException(status_code=409, detail="视频分身能力当前未启用。")
    try:
        result = await heygen_service.list_sessions()
    except Exception as exc:  # pragma: no cover - runtime integration fallback
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return LiveAvatarTokenResponse(data=result)


@app.post("/api/liveavatar/keepalive", response_model=LiveAvatarTokenResponse)
async def liveavatar_keepalive(
    payload: LiveAvatarStartRequest,
    _: str = Depends(require_console_auth),
) -> LiveAvatarTokenResponse:
    if not settings.enable_video_avatar:
        raise HTTPException(status_code=409, detail="视频分身能力当前未启用。")
    try:
        result = await heygen_service.keep_alive(payload.session_token)
    except Exception as exc:  # pragma: no cover - runtime integration fallback
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return LiveAvatarTokenResponse(data=result)
