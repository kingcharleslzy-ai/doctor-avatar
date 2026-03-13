from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "doctor_memory.db"
DEFAULT_OUTPUT_PATH = ROOT / "research" / "doctor-memory-snapshot.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a versioned JSON snapshot from the SQLite doctor memory DB.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to SQLite database.")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT_PATH), help="Path to output JSON snapshot.")
    return parser.parse_args()


def load_rows(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, kind, title, content, tags_json, source, importance, created_at, updated_at
            FROM doctor_memory_entries
            ORDER BY kind ASC, importance DESC, updated_at DESC, id ASC
            """
        ).fetchall()
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


def write_snapshot(db_path: Path, out_path: Path) -> tuple[int, Path]:
    if not db_path.exists():
        raise SystemExit(f"Database not found: {db_path}")

    rows = load_rows(db_path)
    payload = {
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "row_count": len(rows),
        "entries": rows,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(rows), out_path


def main() -> None:
    args = parse_args()
    count, out_path = write_snapshot(Path(args.db), Path(args.out))
    print(f"Rows: {count}")
    print(f"Snapshot: {out_path}")


if __name__ == "__main__":
    main()
