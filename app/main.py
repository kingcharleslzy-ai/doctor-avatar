from __future__ import annotations

import json
import secrets
import time
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import settings
from .db import create_memory_entry, delete_memory_entries, init_memory_db, list_memory_entries, memory_kind_counts
from .knowledge import invalidate_index, load_doctor_profile
from .memory_snapshot import MARKER_KIND, get_memory_status
from .models import (
    ChatRequest,
    ChatResponse,
    LiveAvatarSessionRequest,
    LiveAvatarStartRequest,
    LiveAvatarTokenResponse,
    MemoryEntryCreate,
    MemoryEntryDeleteRequest,
    MemoryEntryResponse,
    PresenceHeartbeatRequest,
)
from .ops import monitor_snapshot, record_presence, record_request
from .services import ChatService, HeyGenService


app = FastAPI(title="Doctor Avatar MVP", version="0.1.0")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
chat_service = ChatService()
heygen_service = HeyGenService()
doctor_profile = load_doctor_profile()
console_auth = HTTPBasic(auto_error=False)
BUILD_META_PATH = Path(__file__).parent / "build_meta.json"



def resolve_user_template(request: Request) -> str:
    view = request.query_params.get("view")
    if view == "mobile":
        return "user_mobile.html"
    if view == "desktop":
        return "user_desktop.html"
    return "index.html"


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


@app.on_event("startup")
def startup() -> None:
    init_memory_db()


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


@app.get("/api/app-config")
def app_config() -> dict[str, object]:
    build_meta = load_build_meta()
    memory_entries = list_memory_entries(limit=1)
    memory_code = get_memory_status(Path(settings.doctor_memory_db_path))[0] if memory_entries else None
    return {
        "openai_configured": bool(settings.openai_api_key),
        "heygen_configured": bool(settings.heygen_api_key),
        "video_avatar_enabled": settings.enable_video_avatar,
        "runtime": build_meta,
        "doctor_memory": {
            "db_path": settings.doctor_memory_db_path,
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
    return templates.TemplateResponse(resolve_user_template(request), {"request": request})


@app.get("/desktop", response_class=HTMLResponse)
def desktop(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("user_desktop.html", {"request": request})


@app.get("/mobile", response_class=HTMLResponse)
def mobile(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("user_mobile.html", {"request": request})


@app.get("/console", response_class=HTMLResponse)
def console(request: Request, _: str = Depends(require_console_auth)) -> HTMLResponse:
    return templates.TemplateResponse("console.html", {"request": request})


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    try:
        result = chat_service.answer(payload.message, payload.conversation)
    except Exception as exc:  # pragma: no cover - runtime integration fallback
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ChatResponse(**result)


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
