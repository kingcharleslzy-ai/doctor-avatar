from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


DEFAULT_SNAPSHOT_PATH = ROOT / "knowledge" / "rhinitis_curated_evidence.json"
SNAPSHOT_VERSION = 1

DOCUMENT_FIELDS = [
    "source_key",
    "source_bucket",
    "source_type",
    "title",
    "url",
    "pmid",
    "pmcid",
    "doi",
    "year",
    "journal_or_org",
    "language",
    "evidence_level",
    "license_status",
    "open_access",
    "patient_visible",
    "doctor_visible",
    "research_visible",
    "topic_tags",
    "content_summary",
    "retrieved_at",
    "raw_payload",
]

CHUNK_FIELDS = [
    "chunk_index",
    "heading",
    "content",
    "scenario",
    "topic_tags",
    "patient_visible",
    "doctor_visible",
    "research_visible",
]


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def export_curated_snapshot(path: Path) -> dict[str, Any]:
    from app.rhinitis_evidence import get_evidence_document, init_rhinitis_evidence_db, rhinitis_evidence_db_path

    init_rhinitis_evidence_db(seed_curated_snapshot=False)
    conn = sqlite3.connect(rhinitis_evidence_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, raw_document_id, source_bucket, evidence_level, title
        FROM curated_documents
        WHERE review_status = 'approved'
        ORDER BY
          CASE source_bucket
            WHEN 'guideline_candidates' THEN 1
            WHEN 'literature_candidates' THEN 2
            WHEN 'drug_candidates' THEN 3
            WHEN 'hospital_education_candidates' THEN 4
            WHEN 'environment_candidates' THEN 5
            ELSE 6
          END ASC,
          CASE evidence_level
            WHEN 'guideline' THEN 1
            WHEN 'consensus' THEN 2
            WHEN 'clinical_pathway' THEN 3
            WHEN 'meta_analysis' THEN 4
            WHEN 'systematic_review' THEN 5
            WHEN 'rct' THEN 6
            WHEN 'review' THEN 7
            ELSE 8
          END ASC,
          year DESC,
          id ASC
        """
    ).fetchall()
    conn.close()

    documents = []
    for row in rows:
        raw_document_id = int(row["raw_document_id"] or 0)
        if raw_document_id:
            document = get_evidence_document(raw_document_id, scope="raw")
            exported_scope = "raw"
        else:
            document = get_evidence_document(int(row["id"]), scope="curated")
            exported_scope = "curated"
        if not document:
            continue
        documents.append(clean_document_for_snapshot(document, exported_scope=exported_scope))

    by_bucket = Counter(str(document.get("source_bucket") or "") for document in documents)
    by_level = Counter(str(document.get("evidence_level") or "") for document in documents)
    payload = {
        "snapshot_version": SNAPSHOT_VERSION,
        "exported_at": utc_now(),
        "source": "local curated_documents",
        "document_count": len(documents),
        "by_source_bucket": dict(sorted(by_bucket.items())),
        "by_evidence_level": dict(sorted(by_level.items())),
        "documents": documents,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {
        "snapshot_path": str(path),
        "document_count": len(documents),
        "by_source_bucket": payload["by_source_bucket"],
        "by_evidence_level": payload["by_evidence_level"],
    }


def clean_document_for_snapshot(document: dict[str, Any], *, exported_scope: str) -> dict[str, Any]:
    cleaned = {field: document.get(field) for field in DOCUMENT_FIELDS if field in document}
    cleaned["review_status"] = "approved"
    raw_payload = cleaned.get("raw_payload") if isinstance(cleaned.get("raw_payload"), dict) else {}
    raw_payload = {
        key: value
        for key, value in raw_payload.items()
        if key not in {"snapshot_export", "curated_snapshot"}
    }
    cleaned["raw_payload"] = {
        **raw_payload,
        "snapshot_export": {
            "exported_scope": exported_scope,
            "source_document_id": document.get("id"),
        },
    }
    chunks = []
    for chunk in document.get("chunks") or []:
        content = str(chunk.get("content") or "").strip()
        if not content:
            continue
        chunks.append({field: chunk.get(field) for field in CHUNK_FIELDS if field in chunk})
    cleaned["chunks"] = chunks
    return cleaned


def import_curated_snapshot(path: Path) -> dict[str, Any]:
    from app.rhinitis_evidence import import_curated_snapshot as import_snapshot

    return import_snapshot(path)


def snapshot_stats(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    documents = payload.get("documents") or []
    return {
        "snapshot_path": str(path),
        "snapshot_version": payload.get("snapshot_version"),
        "exported_at": payload.get("exported_at"),
        "document_count": len(documents),
        "by_source_bucket": payload.get("by_source_bucket") or {},
        "by_evidence_level": payload.get("by_evidence_level") or {},
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export/import the Rhinitis AI curated evidence seed snapshot.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser("export", help="Export approved curated evidence to a commit-friendly JSON seed.")
    export.add_argument("--path", type=Path, default=DEFAULT_SNAPSHOT_PATH)

    import_cmd = subparsers.add_parser("import", help="Import the curated evidence JSON seed into SQLite.")
    import_cmd.add_argument("--path", type=Path, default=DEFAULT_SNAPSHOT_PATH)

    stats = subparsers.add_parser("stats", help="Print snapshot metadata without touching SQLite.")
    stats.add_argument("--path", type=Path, default=DEFAULT_SNAPSHOT_PATH)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "export":
        result = export_curated_snapshot(args.path)
    elif args.command == "import":
        result = import_curated_snapshot(args.path)
    elif args.command == "stats":
        result = snapshot_stats(args.path)
    else:  # pragma: no cover
        parser.error(f"unknown command: {args.command}")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
