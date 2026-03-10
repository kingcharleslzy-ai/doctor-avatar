from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import KNOWLEDGE_DIR


WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+")


@dataclass
class KnowledgeHit:
    source: str
    snippet: str
    score: int


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in WORD_RE.findall(text)}


def load_doctor_profile() -> dict:
    profile_path = KNOWLEDGE_DIR / "doctor_profile.yaml"
    if not profile_path.exists():
        return {}
    return yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}


def search_knowledge(query: str, top_k: int = 3) -> list[KnowledgeHit]:
    query_tokens = _tokenize(query)
    hits: list[KnowledgeHit] = []

    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        sections = [section.strip() for section in re.split(r"\n##+\s+", content) if section.strip()]
        for section in sections:
            section_tokens = _tokenize(section)
            score = len(query_tokens & section_tokens)
            if score == 0:
                continue
            snippet = re.sub(r"\s+", " ", section)[:280]
            hits.append(KnowledgeHit(source=path.name, snippet=snippet, score=score))

    hits.sort(key=lambda item: item.score, reverse=True)
    return hits[:top_k]

