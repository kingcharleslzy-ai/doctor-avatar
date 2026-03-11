from __future__ import annotations

import json
import re
from dataclasses import dataclass

import yaml

from .config import KNOWLEDGE_DIR, settings


WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+")

# 进程内索引缓存，只在首次查询时构建一次
_index: list[dict] | None = None
_index_ready = False


@dataclass
class KnowledgeHit:
    source: str
    snippet: str
    score: float


def _tokenize(text: str) -> set[str]:
    return {token.lower() for token in WORD_RE.findall(text)}


def load_doctor_profile() -> dict:
    profile_path = KNOWLEDGE_DIR / "doctor_profile.yaml"
    if not profile_path.exists():
        return {}
    return yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}


def _load_chunks() -> list[dict[str, str]]:
    chunks = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        sections = [s.strip() for s in re.split(r"\n##+\s+", content) if s.strip()]
        for section in sections:
            chunks.append({"source": path.name, "text": section})
    return chunks


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _embed(texts: list[str], client) -> list[list[float]]:
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [item.embedding for item in resp.data]


def _cache_file() -> Path:
    """返回缓存文件路径。生产环境通过 EMBED_CACHE_DIR 指向持久卷，本地开发默认存在 knowledge/ 内。"""
    cache_dir = settings.embed_cache_dir
    if cache_dir:
        p = Path(cache_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p / "embed_cache.json"
    return KNOWLEDGE_DIR / ".embed_cache.json"


def _get_index(client) -> list[dict] | None:
    global _index, _index_ready
    if _index_ready:
        return _index

    chunks = _load_chunks()
    if not chunks:
        _index_ready = True
        return None

    chunk_texts = [c["text"] for c in chunks]
    cache_file = _cache_file()

    # 优先读磁盘缓存（知识库未变动时跳过 API 调用）
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
            if cache.get("texts") == chunk_texts:
                _index = cache["entries"]
                _index_ready = True
                return _index
        except Exception:
            pass

    # 构建新索引并写入磁盘缓存
    embeddings = _embed(chunk_texts, client)
    _index = [
        {"source": c["source"], "text": c["text"], "embedding": emb}
        for c, emb in zip(chunks, embeddings)
    ]
    cache_file.write_text(
        json.dumps({"texts": chunk_texts, "entries": _index}, ensure_ascii=False),
        encoding="utf-8",
    )
    _index_ready = True
    return _index


def search_knowledge(query: str, top_k: int = 3) -> list[KnowledgeHit]:
    """语义检索知识库。有 OpenAI key 时用 embedding，否则降级为 token 匹配。"""
    if not settings.openai_api_key:
        return _token_search(query, top_k)

    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key)
        index = _get_index(client)
        if index is None:
            return _token_search(query, top_k)

        query_emb = _embed([query], client)[0]
        hits = [
            KnowledgeHit(
                source=entry["source"],
                snippet=re.sub(r"\s+", " ", entry["text"])[:280],
                score=_cosine(query_emb, entry["embedding"]),
            )
            for entry in index
        ]
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]
    except Exception:
        # Embedding 接口偶发失败时，退回关键词检索，避免直接把问答打成 500。
        return _token_search(query, top_k)


def _token_search(query: str, top_k: int) -> list[KnowledgeHit]:
    """降级方案：基于 token 重叠的关键词匹配。"""
    query_tokens = _tokenize(query)
    hits: list[KnowledgeHit] = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        sections = [s.strip() for s in re.split(r"\n##+\s+", content) if s.strip()]
        for section in sections:
            score = len(query_tokens & _tokenize(section))
            if score == 0:
                continue
            hits.append(KnowledgeHit(
                source=path.name,
                snippet=re.sub(r"\s+", " ", section)[:280],
                score=float(score),
            ))
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:top_k]

