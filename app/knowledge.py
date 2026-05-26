from __future__ import annotations

import re
from dataclasses import dataclass

import yaml

from .config import KNOWLEDGE_DIR


WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+")
CJK_RE = re.compile(r"[\u4e00-\u9fff]+")

@dataclass
class KnowledgeHit:
    source: str
    snippet: str
    score: float


def _tokenize(text: str) -> set[str]:
    tokens: set[str] = set()
    for token in WORD_RE.findall(text):
        lowered = token.lower()
        tokens.add(lowered)
        for cjk in CJK_RE.findall(token):
            tokens.update(cjk)
            tokens.update(cjk[i : i + 2] for i in range(max(0, len(cjk) - 1)))
            tokens.update(cjk[i : i + 3] for i in range(max(0, len(cjk) - 2)))
    return {token for token in tokens if token}


def load_doctor_profile() -> dict:
    profile_path = KNOWLEDGE_DIR / "doctor_profile.yaml"
    if not profile_path.exists():
        return {}
    return yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}


def _load_db_chunks() -> list[dict[str, str]]:
    """从 SQLite doctor_memory 读取条目作为检索块。"""
    try:
        from .db import list_memory_entries
        entries = list_memory_entries(limit=None)
        return [
            {
                "source": f"memory:{e['kind']}",
                "text": f"{e['title']}：{e['content']}",
            }
            for e in entries
        ]
    except Exception:
        return []


def invalidate_index() -> None:
    """保留给资料库写入后的统一调用点；当前检索不使用远端 embedding 缓存。"""
    return None


def search_knowledge(query: str, top_k: int = 5) -> list[KnowledgeHit]:
    """本地检索：知识库 Markdown + SQLite 医生资料，不依赖外部 LLM/Embedding 服务。"""
    return _token_search(query, top_k)


def _token_search(query: str, top_k: int) -> list[KnowledgeHit]:
    """关键词匹配，覆盖文件和 SQLite 两个来源。"""
    query_tokens = _tokenize(query)
    hits: list[KnowledgeHit] = []

    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        sections = [s.strip() for s in re.split(r"\n##+\s+", content) if s.strip()]
        for section in sections:
            score = len(query_tokens & _tokenize(section))
            if score:
                hits.append(KnowledgeHit(
                    source=path.name,
                    snippet=re.sub(r"\s+", " ", section)[:300],
                    score=float(score),
                ))

    for chunk in _load_db_chunks():
        score = len(query_tokens & _tokenize(chunk["text"]))
        if score:
            hits.append(KnowledgeHit(
                source=chunk["source"],
                snippet=re.sub(r"\s+", " ", chunk["text"])[:300],
                score=float(score),
            ))

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]
