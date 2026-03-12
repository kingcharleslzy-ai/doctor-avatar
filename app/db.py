from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable

import yaml

from .config import KNOWLEDGE_DIR, settings


def _db_path() -> Path:
    path = Path(settings.doctor_memory_db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _normalize_tags(tags: Iterable[str] | None) -> list[str]:
    return [tag.strip() for tag in (tags or []) if tag and tag.strip()]


def init_memory_db() -> None:
    with closing(_connect()) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS doctor_memory_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                tags_json TEXT NOT NULL DEFAULT '[]',
                source TEXT NOT NULL DEFAULT 'manual',
                importance REAL NOT NULL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_doctor_memory_kind
            ON doctor_memory_entries(kind)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_doctor_memory_updated_at
            ON doctor_memory_entries(updated_at DESC)
            """
        )
        conn.commit()

    if settings.doctor_memory_bootstrap:
        bootstrap_memory_if_empty()


def _insert_seed_entry(
    conn: sqlite3.Connection,
    *,
    kind: str,
    title: str,
    content: str,
    tags: Iterable[str] | None = None,
    source: str = "seed",
    importance: float = 1.0,
) -> None:
    now = _utc_now()
    conn.execute(
        """
        INSERT INTO doctor_memory_entries (
            kind, title, content, tags_json, source, importance, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            kind,
            title.strip(),
            content.strip(),
            json.dumps(_normalize_tags(tags), ensure_ascii=False),
            source,
            importance,
            now,
            now,
        ),
    )


def bootstrap_memory_if_empty() -> None:
    with closing(_connect()) as conn:
        count = conn.execute("SELECT COUNT(*) FROM doctor_memory_entries").fetchone()[0]
        if count:
            return

        profile_path = KNOWLEDGE_DIR / "doctor_profile.yaml"
        profile = {}
        if profile_path.exists():
            profile = yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}

        focus_tags = profile.get("focus_areas", [])
        specialty = profile.get("specialty", "耳鼻咽喉科")

        for idx, item in enumerate(profile.get("public_bio", []), start=1):
            _insert_seed_entry(
                conn,
                kind="public_bio",
                title=f"公开职业信息 {idx}",
                content=item,
                tags=[specialty, "公开资料"],
                source="doctor_profile.yaml",
                importance=0.8,
            )

        for idx, item in enumerate(profile.get("style_traits", []), start=1):
            _insert_seed_entry(
                conn,
                kind="thinking_style",
                title=f"沟通风格 {idx}",
                content=item,
                tags=["口吻", "风格"],
                source="doctor_profile.yaml",
                importance=1.2,
            )

        for idx, item in enumerate(profile.get("hard_boundaries", []), start=1):
            _insert_seed_entry(
                conn,
                kind="hard_boundary",
                title=f"医疗边界 {idx}",
                content=item,
                tags=["边界", "安全"],
                source="doctor_profile.yaml",
                importance=1.5,
            )

        for idx, item in enumerate(profile.get("escalation_rules", []), start=1):
            _insert_seed_entry(
                conn,
                kind="escalation_rule",
                title=f"升级规则 {idx}",
                content=item,
                tags=["风险升级", "安全"],
                source="doctor_profile.yaml",
                importance=1.5,
            )

        for idx, item in enumerate(profile.get("clinical_strengths", []), start=1):
            _insert_seed_entry(
                conn,
                kind="clinical_strength",
                title=f"临床强项 {idx}",
                content=item,
                tags=focus_tags,
                source="doctor_profile.yaml",
                importance=1.0,
            )

        conn.commit()


def list_memory_entries(
    kind: str | None = None,
    query: str | None = None,
    limit: int | None = 100,
) -> list[dict]:
    sql = """
        SELECT id, kind, title, content, tags_json, source, importance, created_at, updated_at
        FROM doctor_memory_entries
    """
    conditions: list[str] = []
    params: list[object] = []

    if kind:
        conditions.append("kind = ?")
        params.append(kind)
    if query:
        conditions.append("(title LIKE ? OR content LIKE ? OR tags_json LIKE ?)")
        like = f"%{query.strip()}%"
        params.extend([like, like, like])

    if conditions:
        sql += " WHERE " + " AND ".join(conditions)

    sql += " ORDER BY importance DESC, updated_at DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(max(1, min(limit, 5000)))

    with closing(_connect()) as conn:
        rows = conn.execute(sql, params).fetchall()

    return [_row_to_dict(row) for row in rows]


def create_memory_entry(
    *,
    kind: str,
    title: str,
    content: str,
    tags: Iterable[str] | None = None,
    source: str = "manual",
    importance: float = 1.0,
) -> dict:
    now = _utc_now()
    payload = (
        kind.strip(),
        title.strip(),
        content.strip(),
        json.dumps(_normalize_tags(tags), ensure_ascii=False),
        source.strip() or "manual",
        float(importance),
        now,
        now,
    )

    with closing(_connect()) as conn:
        cursor = conn.execute(
            """
            INSERT INTO doctor_memory_entries (
                kind, title, content, tags_json, source, importance, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
        conn.commit()
        row = conn.execute(
            """
            SELECT id, kind, title, content, tags_json, source, importance, created_at, updated_at
            FROM doctor_memory_entries
            WHERE id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()

    return _row_to_dict(row)



def _row_to_dict(row: sqlite3.Row) -> dict:
    tags = []
    try:
        tags = json.loads(row["tags_json"] or "[]")
    except json.JSONDecodeError:
        tags = []
    return {
        "id": row["id"],
        "kind": row["kind"],
        "title": row["title"],
        "content": row["content"],
        "tags": tags,
        "source": row["source"],
        "importance": row["importance"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }
