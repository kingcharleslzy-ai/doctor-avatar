from __future__ import annotations

import json
import secrets
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .config import settings
from .knowledge import load_doctor_profile
from .models import (
    ChatRequest,
    ChatResponse,
    LiveAvatarSessionRequest,
    LiveAvatarStartRequest,
    LiveAvatarTokenResponse,
)
from .services import ChatService, HeyGenService


app = FastAPI(title="Doctor Avatar MVP", version="0.1.0")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
chat_service = ChatService()
heygen_service = HeyGenService()
doctor_profile = load_doctor_profile()
console_auth = HTTPBasic()
BUILD_META_PATH = Path(__file__).parent / "build_meta.json"


MOBILE_MARKERS = (
    "iphone",
    "android",
    "mobile",
    "ipad",
    "ipod",
    "windows phone",
    "blackberry",
    "opera mini",
)


def resolve_user_template(request: Request) -> str:
    view = request.query_params.get("view")
    if view == "mobile":
        return "user_mobile.html"
    if view == "desktop":
        return "user_desktop.html"

    user_agent = request.headers.get("user-agent", "").lower()
    if any(marker in user_agent for marker in MOBILE_MARKERS):
        return "user_mobile.html"
    return "user_desktop.html"


def require_console_auth(credentials: HTTPBasicCredentials = Depends(console_auth)) -> str:
    if settings.console_auth_mode == "off":
        return "console-auth-disabled"

    if not settings.console_username or not settings.console_password:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="控制台认证已启用，但尚未配置 CONSOLE_USERNAME / CONSOLE_PASSWORD。",
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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/app-config")
def app_config() -> dict[str, object]:
    build_meta = load_build_meta()
    return {
        "openai_configured": bool(settings.openai_api_key),
        "heygen_configured": bool(settings.heygen_api_key),
        "video_avatar_enabled": settings.enable_video_avatar,
        "runtime": build_meta,
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
