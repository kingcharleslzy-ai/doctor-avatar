from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/chat", response_model=ChatResponse)
def chat(payload: ChatRequest) -> ChatResponse:
    try:
        result = chat_service.answer(payload.message, payload.conversation)
    except Exception as exc:  # pragma: no cover - runtime integration fallback
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return ChatResponse(**result)


@app.post("/api/liveavatar/token", response_model=LiveAvatarTokenResponse)
async def liveavatar_token(payload: LiveAvatarSessionRequest) -> LiveAvatarTokenResponse:
    request_payload = {
        "mode": payload.mode,
        "avatar_id": payload.avatar_id,
        "is_sandbox": payload.is_sandbox,
        "avatar_persona": {
            "voice_id": payload.voice_id,
            "context_id": payload.context_id,
            "language": payload.language,
        },
        **payload.extra,
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
async def liveavatar_session(payload: LiveAvatarStartRequest) -> LiveAvatarTokenResponse:
    try:
        result = await heygen_service.start_liveavatar_session(payload.session_token)
    except Exception as exc:  # pragma: no cover - runtime integration fallback
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return LiveAvatarTokenResponse(data=result)


@app.get("/api/liveavatar/sessions", response_model=LiveAvatarTokenResponse)
async def liveavatar_sessions() -> LiveAvatarTokenResponse:
    try:
        result = await heygen_service.list_sessions()
    except Exception as exc:  # pragma: no cover - runtime integration fallback
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return LiveAvatarTokenResponse(data=result)


@app.post("/api/liveavatar/keepalive", response_model=LiveAvatarTokenResponse)
async def liveavatar_keepalive(payload: LiveAvatarStartRequest) -> LiveAvatarTokenResponse:
    try:
        result = await heygen_service.keep_alive(payload.session_token)
    except Exception as exc:  # pragma: no cover - runtime integration fallback
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return LiveAvatarTokenResponse(data=result)
