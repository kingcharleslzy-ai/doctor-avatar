from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from .db import upsert_memory_entry

MARKER_KIND = "system_marker"
MARKER_TITLE = "资料库暗号"
MARKER_SOURCE = "system:auto"


def _load_rows(db_path: Path, *, include_marker: bool = True) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        sql = """
            SELECT id, kind, title, content, tags_json, source, importance, created_at, updated_at
            FROM doctor_memory_entries
        """
        params: list[object] = []
        if not include_marker:
            sql += " WHERE kind != ?"
            params.append(MARKER_KIND)
        sql += " ORDER BY kind ASC, importance DESC, updated_at DESC, id ASC"
        rows = conn.execute(sql, params).fetchall()
    finally:
        conn.close()

    result: list[dict] = []
    for row in rows:
        try:
            tags = json.loads(row["tags_json"] or "[]")
        except json.JSONDecodeError:
            tags = []
        result.append(
            {
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
        )
    return result


def build_memory_code(rows: list[dict]) -> str:
    fingerprint_payload = [
        {
            "kind": row["kind"],
            "title": row["title"],
            "content": row["content"],
            "source": row["source"],
            "tags": row.get("tags", []),
        }
        for row in rows
    ]
    digest = hashlib.sha1(
        json.dumps(fingerprint_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:8].upper()
    return f"LYDB-{datetime.now().strftime('%Y%m%d')}-{digest}"


def upsert_memory_marker(db_path: Path) -> str:
    rows = _load_rows(db_path, include_marker=False)
    code = build_memory_code(rows)
    content = (
        f"当前资料库暗号：{code}。"
        f" 当前有效资料条数：{len(rows)}。"
        f" 如果有人问资料库是否已经更新，可让系统返回这个暗号进行人工核对。"
    )
    upsert_memory_entry(
        kind=MARKER_KIND,
        title=MARKER_TITLE,
        content=content,
        tags=["内部校验", "版本暗号"],
        source=MARKER_SOURCE,
        importance=99.0,
    )
    return code


def get_memory_marker(db_path: Path) -> dict | None:
    rows = _load_rows(db_path, include_marker=True)
    for row in rows:
        if row["kind"] == MARKER_KIND and row["title"] == MARKER_TITLE and row["source"] == MARKER_SOURCE:
            return row
    return None


def get_memory_status(db_path: Path) -> tuple[str, int]:
    code = upsert_memory_marker(db_path)
    row_count = len(_load_rows(db_path, include_marker=False))
    return code, row_count


def write_memory_snapshot(db_path: Path, out_path: Path) -> tuple[int, Path, str]:
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    code = upsert_memory_marker(db_path)
    rows = _load_rows(db_path, include_marker=True)
    payload = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "memory_code": code,
        "row_count": len(rows),
        "entries": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(rows), out_path, code
