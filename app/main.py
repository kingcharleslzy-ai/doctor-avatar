from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .models import ChatRequest, ChatResponse, LiveAvatarSessionRequest, LiveAvatarTokenResponse
from .services import ChatService, HeyGenService


app = FastAPI(title="Doctor Avatar MVP", version="0.1.0")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
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
async def liveavatar_token() -> LiveAvatarTokenResponse:
    try:
        result = await heygen_service.create_liveavatar_token()
    except Exception as exc:  # pragma: no cover - runtime integration fallback
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return LiveAvatarTokenResponse(data=result)


@app.post("/api/liveavatar/session", response_model=LiveAvatarTokenResponse)
async def liveavatar_session(payload: LiveAvatarSessionRequest) -> LiveAvatarTokenResponse:
    request_payload = {
        "version": payload.version,
        "avatar_name": payload.avatar_name,
        "voice": {"voice_id": payload.voice_id} if payload.voice_id else None,
        "knowledge_base_id": payload.knowledge_id,
        "video_encoding": payload.video_encoding,
        "quality": payload.quality,
        "source": payload.source,
        **payload.extra,
    }
    request_payload = {key: value for key, value in request_payload.items() if value is not None}

    try:
        result = await heygen_service.start_liveavatar_session(request_payload)
    except Exception as exc:  # pragma: no cover - runtime integration fallback
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return LiveAvatarTokenResponse(data=result)
