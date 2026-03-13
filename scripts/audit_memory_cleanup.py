from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import delete_memory_entries, find_exact_duplicate_groups, init_memory_db, list_memory_entries

TEST_SOURCES = {"api-test", "manual-test"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit and safely clean doctor memory entries.")
    parser.add_argument(
        "--apply-safe",
        action="store_true",
        help="Delete exact duplicates and known test-noise entries.",
    )
    parser.add_argument(
        "--report",
        default="tmp/memory_cleanup_report.md",
        help="Where to write the cleanup report.",
    )
    return parser.parse_args()


def normalize_text(text: str) -> str:
    return re.sub(r"[\W_]+", "", text.lower())


def likely_overlap_groups(rows: list[dict]) -> list[list[dict]]:
    buckets: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        normalized = normalize_text(row["content"])
        key = (row["kind"], normalized[:36])
        buckets[key].append(row)

    groups: list[list[dict]] = []
    for entries in buckets.values():
        if len(entries) < 2:
            continue
        sorted_entries = sorted(entries, key=lambda item: item["id"])
        anchor = sorted_entries[0]
        related = [anchor]
        for candidate in sorted_entries[1:]:
            a = normalize_text(anchor["content"])
            b = normalize_text(candidate["content"])
            if not a or not b:
                continue
            shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
            if shorter and shorter in longer:
                related.append(candidate)
        if len(related) > 1:
            groups.append(related)
    return groups


def build_report(rows: list[dict], exact_groups: list[dict], test_rows: list[dict], overlap_groups: list[list[dict]]) -> str:
    lines: list[str] = []
    lines.append("# 资料库清洗报告")
    lines.append("")
    lines.append(f"- 当前总条目：{len(rows)}")
    lines.append(f"- 完全重复组：{len(exact_groups)}")
    lines.append(f"- 测试噪音条目：{len(test_rows)}")
    lines.append(f"- 需人工审核的近似重叠组：{len(overlap_groups)}")
    lines.append("")

    lines.append("## 可安全自动清理")
    lines.append("")
    if not exact_groups and not test_rows:
        lines.append("- 当前没有发现可安全自动清理的条目。")
    else:
        for group in exact_groups:
            lines.append(
                f"- 完全重复：`{group['kind']}` / `{group['title']}` / `{group['source']}` -> 保留 `{group['keep_id']}`，建议删除 `{group['delete_ids']}`"
            )
        for row in test_rows:
            lines.append(
                f"- 测试条目：删除 `{row['id']}` / `{row['kind']}` / `{row['title']}` / `{row['source']}`"
            )

    lines.append("")
    lines.append("## 需人工审核的近似重叠")
    lines.append("")
    if not overlap_groups:
        lines.append("- 当前没有发现明显的近似重叠组。")
    else:
        for idx, group in enumerate(overlap_groups, start=1):
            lines.append(f"### 候选组 {idx}")
            for row in group:
                snippet = row["content"][:120].replace("\n", " ")
                lines.append(
                    f"- `{row['id']}` / `{row['kind']}` / `{row['source']}` / `{row['title']}`: {snippet}"
                )
            lines.append("")

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    init_memory_db()
    rows = list_memory_entries(limit=None)
    exact_groups = find_exact_duplicate_groups()
    test_rows = [row for row in rows if row["source"] in TEST_SOURCES]

    if args.apply_safe:
        delete_ids: list[int] = []
        for group in exact_groups:
            delete_ids.extend(group["delete_ids"])
        delete_ids.extend(row["id"] for row in test_rows)
        deleted_count = delete_memory_entries(delete_ids)
        rows = list_memory_entries(limit=None)
        exact_groups = find_exact_duplicate_groups()
        test_rows = [row for row in rows if row["source"] in TEST_SOURCES]
        print(f"Deleted: {deleted_count}")

    overlap_groups = likely_overlap_groups(
        [
            row
            for row in rows
            if row["source"] not in TEST_SOURCES
            and row["kind"] in {"public_bio", "clinical_strength", "doctor_thought", "patient_education"}
        ]
    )

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        build_report(rows, exact_groups, test_rows, overlap_groups),
        encoding="utf-8",
    )

    print(f"Rows: {len(rows)}")
    print(f"Exact duplicate groups: {len(exact_groups)}")
    print(f"Test-noise rows: {len(test_rows)}")
    print(f"Overlap groups: {len(overlap_groups)}")
    print(f"Report: {report_path}")


if __name__ == "__main__":
    main()
