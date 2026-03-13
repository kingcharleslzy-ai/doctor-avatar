from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT / "data" / "doctor_memory.db"
DEFAULT_OUTPUT_PATH = ROOT / "research" / "doctor-memory-snapshot.json"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.memory_snapshot import write_memory_snapshot


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a versioned JSON snapshot from the SQLite doctor memory DB.")
    parser.add_argument("--db", default=str(DEFAULT_DB_PATH), help="Path to SQLite database.")
    parser.add_argument("--out", default=str(DEFAULT_OUTPUT_PATH), help="Path to output JSON snapshot.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    count, out_path, code = write_memory_snapshot(Path(args.db), Path(args.out))
    print(f"Rows: {count}")
    print(f"Snapshot: {out_path}")
    print(f"Memory code: {code}")


if __name__ == "__main__":
    main()
