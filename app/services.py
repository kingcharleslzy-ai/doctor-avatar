from __future__ import annotations

from typing import Any

import httpx
from openai import OpenAI

from .config import settings
from .db import search_memory_entries
from .knowledge import load_doctor_profile, search_knowledge
from .prompts import build_system_prompt, build_user_prompt


class ChatService:
    def __init__(self) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None
        self.profile = load_doctor_profile()

    def answer(self, message: str, conversation: list[dict[str, str]]) -> dict[str, Any]:
        if self.client is None:
            raise RuntimeError("OPENAI_API_KEY 未配置。")
        knowledge_hits = search_knowledge(message)
        memory_hits = search_memory_entries(message)

        knowledge_snippets = [hit.snippet for hit in knowledge_hits]
        memory_snippets = [
            f"{hit.title}：{hit.content}"
            for hit in memory_hits
        ]
        citations = [hit.source for hit in knowledge_hits] + [
            f"doctor-memory:{hit.entry_id}:{hit.kind}"
            for hit in memory_hits
        ]

        response = self.client.responses.create(
            model=settings.openai_model,
            input=[
                {"role": "system", "content": build_system_prompt(self.profile)},
                *conversation,
                {"role": "user", "content": build_user_prompt(message, knowledge_snippets, memory_snippets)},
            ],
        )

        return {
            "answer": response.output_text.strip(),
            "citations": citations,
            "context_snippets": [*memory_snippets, *knowledge_snippets],
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
