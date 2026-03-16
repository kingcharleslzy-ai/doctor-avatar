from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI

from .config import settings
from .memory_snapshot import get_memory_marker, get_memory_status
from .knowledge import load_doctor_profile, search_knowledge
from .ops import record_openai_error, record_openai_usage
from .prompts import build_system_prompt, build_user_prompt


class ChatService:
    def __init__(self) -> None:
        self.client = (
            OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)
            if settings.openai_api_key
            else None
        )
        self.profile = load_doctor_profile()

    def answer(self, message: str, conversation: list[dict[str, str]]) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("OPENAI_API_KEY 未配置。")

        if self._looks_like_memory_code_request(message):
            code_answer = self._answer_memory_code()
            if code_answer:
                return code_answer

        hits = search_knowledge(message)
        snippets = [hit.snippet for hit in hits]
        citations = [hit.source for hit in hits]

        try:
            response = self.client.chat.completions.create(
                model=settings.openai_model,
                messages=[
                    {"role": "system", "content": build_system_prompt(self.profile)},
                    *conversation,
                    {"role": "user", "content": build_user_prompt(message, snippets)},
                ],
            )
        except Exception:
            record_openai_error()
            raise

        record_openai_usage(settings.openai_model, getattr(response, "usage", None))

        return {
            "answer": response.choices[0].message.content.strip(),
            "citations": citations,
            "context_snippets": snippets,
        }

    def _looks_like_memory_code_request(self, message: str) -> bool:
        lowered = message.lower()
        direct_keywords = ("暗号", "口令", "memory code", "校验码")
        if any(keyword in lowered for keyword in direct_keywords):
            return True
        return (
            ("资料库" in lowered or "数据库" in lowered)
            and any(keyword in lowered for keyword in ("更新", "版本", "同步", "校验"))
        )

    def _answer_memory_code(self) -> dict[str, Any] | None:
        db_path = Path(settings.doctor_memory_db_path)
        code, row_count = get_memory_status(db_path)
        marker = get_memory_marker(Path(db_path))
        if not marker:
            return None
        answer = (
            f"当前资料库暗号：{code}\n"
            f"当前有效资料条数：{row_count}。"
        )
        return {
            "answer": answer,
            "citations": [f"memory:{marker['kind']}"],
            "context_snippets": [marker["content"]],
        }


class HeyGenService:
    def __init__(self) -> None:
        self.api_key = settings.heygen_api_key

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("HEYGEN_API_KEY 未配置。")
        return {
            "X-API-KEY": self.api_key,
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def create_liveavatar_token(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{settings.liveavatar_api_base.rstrip('/')}/v1/sessions/token"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, headers=self._headers(), json=payload)
            response.raise_for_status()
            return response.json()

    async def start_liveavatar_session(self, session_token: str) -> dict[str, Any]:
        url = f"{settings.liveavatar_api_base.rstrip('/')}/v1/sessions/start"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {session_token}",
                },
            )
            response.raise_for_status()
            return response.json()

    async def list_sessions(self) -> dict[str, Any]:
        url = f"{settings.liveavatar_api_base.rstrip('/')}/v1/sessions"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url, headers=self._headers())
            response.raise_for_status()
            return response.json()

    async def keep_alive(self, session_token: str) -> dict[str, Any]:
        url = f"{settings.liveavatar_api_base.rstrip('/')}/v1/sessions/keep-alive"
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                url,
                headers={
                    "Accept": "application/json",
                    "Authorization": f"Bearer {session_token}",
                },
            )
            response.raise_for_status()
            return response.json()
