from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import delete_memory_entries, init_memory_db, list_memory_entries, upsert_memory_entry


DEFAULT_SNAPSHOT_PATH = ROOT / "research" / "doctor-memory-snapshot.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Sync SQLite doctor memory DB to the versioned JSON snapshot."
    )
    parser.add_argument(
        "--path",
        default=str(DEFAULT_SNAPSHOT_PATH),
        help="Path to the JSON snapshot file.",
    )
    parser.add_argument(
        "--prune-missing",
        action="store_true",
        help="Delete DB rows that are not present in the snapshot.",
    )
    return parser.parse_args()


def entry_key(item: dict) -> tuple[str, str, str]:
    return (
        (item.get("kind") or "").strip(),
        (item.get("title") or "").strip(),
        (item.get("source") or "manual").strip() or "manual",
    )


def load_snapshot(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise SystemExit(f"Invalid snapshot format: {path}")
    return entries


def main() -> None:
    args = parse_args()
    snapshot_path = Path(args.path)
    if not snapshot_path.exists():
        raise SystemExit(f"Snapshot not found: {snapshot_path}")

    init_memory_db()
    snapshot_entries = load_snapshot(snapshot_path)
    created_count = 0
    updated_count = 0

    for item in snapshot_entries:
        _, created = upsert_memory_entry(
            kind=item["kind"],
            title=item["title"],
            content=item["content"],
            tags=item.get("tags", []),
            source=item.get("source", "manual"),
            importance=item.get("importance", 1.0),
        )
        if created:
            created_count += 1
        else:
            updated_count += 1

    deleted_count = 0
    if args.prune_missing:
        snapshot_keys = {entry_key(item) for item in snapshot_entries}
        current_rows = list_memory_entries(limit=None)
        stale_ids = [
            row["id"]
            for row in current_rows
            if entry_key(row) not in snapshot_keys
        ]
        deleted_count = delete_memory_entries(stale_ids)

    final_count = len(list_memory_entries(limit=None))

    print(f"Snapshot: {snapshot_path}")
    print(f"Snapshot rows: {len(snapshot_entries)}")
    print(f"Created: {created_count}")
    print(f"Updated: {updated_count}")
    print(f"Deleted: {deleted_count}")
    print(f"Final rows: {final_count}")


if __name__ == "__main__":
    main()
