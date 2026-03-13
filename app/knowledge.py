from __future__ import annotations

import hashlib
import json
import re
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path

import yaml

from .config import KNOWLEDGE_DIR, settings


WORD_RE = re.compile(r"[\w\u4e00-\u9fff]+")

# 进程内索引缓存，首次请求时构建
_index: list[dict] | None = None
_index_ready = False
_index_signature: str | None = None
# 快路径缓存：仅用于检查是否需要重建，避免每次请求都读文件+DB
_fast_sig: str | None = None


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


def _load_file_chunks() -> list[dict[str, str]]:
    chunks = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        content = path.read_text(encoding="utf-8")
        sections = [s.strip() for s in re.split(r"\n##+\s+", content) if s.strip()]
        for section in sections:
            chunks.append({"source": path.name, "text": section})
    return chunks


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


def _sqlite_fingerprint() -> str:
    """SQLite 内容指纹：条数 + 最新更新时间，用于缓存失效判断。"""
    try:
        from .db import _connect
        with closing(_connect()) as conn:
            row = conn.execute(
                "SELECT COUNT(*), MAX(updated_at) FROM doctor_memory_entries"
            ).fetchone()
            return f"{row[0]}:{row[1] or ''}"
    except Exception:
        return ""


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


def _embed(texts: list[str], client) -> list[list[float]]:
    resp = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [item.embedding for item in resp.data]


def _cache_file() -> Path:
    cache_dir = settings.embed_cache_dir
    if cache_dir:
        p = Path(cache_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p / "embed_cache.json"
    return KNOWLEDGE_DIR / ".embed_cache.json"


def _build_index_signature(chunk_texts: list[str], sqlite_fp: str) -> str:
    """用 SHA256 摘要生成签名，避免把全量文本存入内存。"""
    text_hash = hashlib.sha256("\n".join(chunk_texts).encode()).hexdigest()
    return json.dumps({"text_hash": text_hash, "sqlite_fp": sqlite_fp})


def _compute_fast_sig() -> str:
    """仅用 SQLite 指纹 + 文件 mtime 做快速变更检测，无需加载文件内容。"""
    sqlite_fp = _sqlite_fingerprint()
    file_mtimes = "|".join(
        f"{p.name}:{p.stat().st_mtime_ns}"
        for p in sorted(KNOWLEDGE_DIR.glob("*.md"))
        if p.exists()
    )
    return f"{sqlite_fp}||{file_mtimes}"


def invalidate_index() -> None:
    """手动失效进程内索引缓存（新增 DB 条目后调用）。"""
    global _index, _index_ready, _index_signature, _fast_sig
    _index = None
    _index_ready = False
    _index_signature = None
    _fast_sig = None


def _get_index(client) -> list[dict] | None:
    global _index, _index_ready, _index_signature, _fast_sig

    # 快路径：仅用 SQLite 指纹 + 文件 mtime 检查，避免每次请求读文件内容
    if _index_ready:
        current_fast = _compute_fast_sig()
        if current_fast == _fast_sig:
            return _index

    file_chunks = _load_file_chunks()
    db_chunks = _load_db_chunks()
    all_chunks = file_chunks + db_chunks

    if not all_chunks:
        _index_ready = True
        return None

    chunk_texts = [c["text"] for c in all_chunks]
    sqlite_fp = _sqlite_fingerprint()
    signature = _build_index_signature(chunk_texts, sqlite_fp)

    if _index_ready and _index_signature == signature:
        _fast_sig = _compute_fast_sig()
        return _index

    cache_file = _cache_file()

    # 磁盘缓存命中：签名一致则直接用，无需再调 OpenAI
    if cache_file.exists():
        try:
            cache = json.loads(cache_file.read_text(encoding="utf-8"))
            if cache.get("signature") == signature:
                _index = cache["entries"]
                _index_ready = True
                _index_signature = signature
                _fast_sig = _compute_fast_sig()
                return _index
        except Exception:
            pass

    # 调 OpenAI 重建索引
    embeddings = _embed(chunk_texts, client)
    _index = [
        {"source": c["source"], "text": c["text"], "embedding": emb}
        for c, emb in zip(all_chunks, embeddings)
    ]
    cache_file.write_text(
        json.dumps({"signature": signature, "entries": _index}, ensure_ascii=False),
        encoding="utf-8",
    )
    _index_ready = True
    _index_signature = signature
    _fast_sig = _compute_fast_sig()
    return _index


def search_knowledge(query: str, top_k: int = 5) -> list[KnowledgeHit]:
    """统一语义检索：知识库文件 + SQLite 医生想法，失败时降级为关键词匹配。"""
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
                snippet=re.sub(r"\s+", " ", entry["text"])[:300],
                score=_cosine(query_emb, entry["embedding"]),
            )
            for entry in index
        ]
        hits.sort(key=lambda h: h.score, reverse=True)
        return hits[:top_k]
    except Exception:
        return _token_search(query, top_k)


def _token_search(query: str, top_k: int) -> list[KnowledgeHit]:
    """降级方案：关键词匹配，覆盖文件和 SQLite 两个来源。"""
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
