from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import init_memory_db, upsert_memory_entry
from scripts.write_memory_snapshot import write_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import structured doctor memory draft into SQLite.")
    parser.add_argument(
        "--path",
        default="research/doctor-li-memory-draft.yaml",
        help="Path to the draft YAML file.",
    )
    parser.add_argument(
        "--section",
        choices=["all", "public", "ppt"],
        default="all",
        help="Which section to import.",
    )
    parser.add_argument(
        "--refresh-snapshot",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Refresh research/doctor-memory-snapshot.json after import.",
    )
    return parser.parse_args()


def load_entries(path: Path, section: str) -> list[dict]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries: list[dict] = []
    if section in {"all", "public"}:
        entries.extend(payload.get("public_search_entries", []))
    if section in {"all", "ppt"}:
        entries.extend(payload.get("ppt_entries", []))
    return entries


def main() -> None:
    args = parse_args()
    draft_path = Path(args.path)
    if not draft_path.exists():
        raise SystemExit(f"Draft file not found: {draft_path}")

    init_memory_db()
    entries = load_entries(draft_path, args.section)
    created_count = 0
    updated_count = 0

    for item in entries:
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

    print(f"Imported {len(entries)} entries from {draft_path}")
    print(f"Created: {created_count}")
    print(f"Updated: {updated_count}")
    if args.refresh_snapshot:
        count, out_path, code = write_snapshot(ROOT / "data" / "doctor_memory.db", ROOT / "research" / "doctor-memory-snapshot.json")
        print(f"Snapshot rows: {count}")
        print(f"Snapshot: {out_path}")
        print(f"Memory code: {code}")


if __name__ == "__main__":
    main()
