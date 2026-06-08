from __future__ import annotations

import json
import re
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterable

import yaml

from .config import KNOWLEDGE_DIR, settings


VALID_REVIEW_STATUSES = {"candidate", "needs_review", "approved", "rejected", "deprecated"}
VALID_SCOPES = {"raw", "curated"}
SEED_SOURCE_PATH = KNOWLEDGE_DIR / "rhinitis_seed_sources.yaml"
CURATED_SEED_PATH = KNOWLEDGE_DIR / "rhinitis_curated_evidence.json"

EVIDENCE_WEIGHTS = {
    "guideline": 100,
    "consensus": 95,
    "clinical_pathway": 88,
    "systematic_review": 82,
    "meta_analysis": 82,
    "rct": 74,
    "drug_label": 68,
    "hospital_education": 58,
    "review": 54,
    "observational": 48,
    "trial_registry": 36,
    "environment": 32,
    "webpage": 24,
}

STATUS_WEIGHTS = {
    "approved": 40,
    "needs_review": 12,
    "candidate": 0,
}

CURATION_PACK_GROUPS = [
    {
        "id": "guideline_core",
        "label": "指南 / 共识",
        "target": 12,
        "source_buckets": ["guideline_candidates"],
        "evidence_levels": ["guideline", "consensus", "clinical_pathway"],
        "topic_tags": [],
    },
    {
        "id": "drug_treatment",
        "label": "药物治疗",
        "target": 12,
        "source_buckets": ["drug_candidates", "literature_candidates", "guideline_candidates"],
        "evidence_levels": ["guideline", "consensus", "meta_analysis", "systematic_review", "rct", "review", "drug_label"],
        "topic_tags": ["鼻喷激素", "抗组胺", "白三烯"],
    },
    {
        "id": "immunotherapy",
        "label": "免疫治疗",
        "target": 8,
        "source_buckets": ["guideline_candidates", "literature_candidates"],
        "evidence_levels": ["guideline", "consensus", "meta_analysis", "systematic_review", "rct", "review"],
        "topic_tags": ["免疫治疗"],
    },
    {
        "id": "pediatric_asthma",
        "label": "儿童 / 合并哮喘",
        "target": 8,
        "source_buckets": ["guideline_candidates", "literature_candidates"],
        "evidence_levels": ["guideline", "consensus", "meta_analysis", "systematic_review", "rct", "review", "observational"],
        "topic_tags": ["儿童", "合并哮喘"],
    },
    {
        "id": "environment_pollen",
        "label": "花粉 / 环境暴露",
        "target": 8,
        "source_buckets": ["environment_candidates"],
        "evidence_levels": ["guideline", "consensus", "meta_analysis", "systematic_review", "rct", "review", "observational", "paper"],
        "topic_tags": ["花粉", "过敏原"],
    },
    {
        "id": "diagnostics_endoscopy",
        "label": "检查 / 鼻内镜",
        "target": 6,
        "source_buckets": ["guideline_candidates", "literature_candidates", "doctor_material_candidates"],
        "evidence_levels": ["guideline", "consensus", "meta_analysis", "systematic_review", "rct", "review", "observational", "paper"],
        "topic_tags": ["鼻内镜", "IgE", "过敏原"],
    },
]


def rhinitis_evidence_db_path() -> Path:
    configured = settings.rhinitis_evidence_db_path.strip()
    path = Path(configured) if configured else Path(settings.doctor_memory_db_path).parent / "rhinitis_evidence.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(rhinitis_evidence_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def init_rhinitis_evidence_db(*, seed_curated_snapshot: bool = True) -> None:
    with closing(_connect()) as conn:
        conn.executescript(
            """
            PRAGMA foreign_keys = ON;

            CREATE TABLE IF NOT EXISTS raw_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_key TEXT NOT NULL UNIQUE,
                source_bucket TEXT NOT NULL,
                source_type TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL DEFAULT '',
                pmid TEXT NOT NULL DEFAULT '',
                pmcid TEXT NOT NULL DEFAULT '',
                doi TEXT NOT NULL DEFAULT '',
                year INTEGER,
                journal_or_org TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT '',
                evidence_level TEXT NOT NULL DEFAULT 'webpage',
                review_status TEXT NOT NULL DEFAULT 'candidate',
                license_status TEXT NOT NULL DEFAULT '',
                open_access INTEGER NOT NULL DEFAULT 0,
                patient_visible INTEGER NOT NULL DEFAULT 0,
                doctor_visible INTEGER NOT NULL DEFAULT 1,
                research_visible INTEGER NOT NULL DEFAULT 1,
                topic_tags_json TEXT NOT NULL DEFAULT '[]',
                content_summary TEXT NOT NULL DEFAULT '',
                retrieved_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                raw_payload_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS raw_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL REFERENCES raw_documents(id) ON DELETE CASCADE,
                chunk_index INTEGER NOT NULL,
                heading TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                scenario TEXT NOT NULL DEFAULT '',
                topic_tags_json TEXT NOT NULL DEFAULT '[]',
                patient_visible INTEGER NOT NULL DEFAULT 0,
                doctor_visible INTEGER NOT NULL DEFAULT 1,
                research_visible INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(document_id, chunk_index)
            );

            CREATE TABLE IF NOT EXISTS curated_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                raw_document_id INTEGER REFERENCES raw_documents(id) ON DELETE SET NULL,
                source_key TEXT NOT NULL UNIQUE,
                source_bucket TEXT NOT NULL,
                source_type TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL DEFAULT '',
                pmid TEXT NOT NULL DEFAULT '',
                pmcid TEXT NOT NULL DEFAULT '',
                doi TEXT NOT NULL DEFAULT '',
                year INTEGER,
                journal_or_org TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT '',
                evidence_level TEXT NOT NULL DEFAULT 'webpage',
                review_status TEXT NOT NULL DEFAULT 'approved',
                license_status TEXT NOT NULL DEFAULT '',
                open_access INTEGER NOT NULL DEFAULT 0,
                patient_visible INTEGER NOT NULL DEFAULT 0,
                doctor_visible INTEGER NOT NULL DEFAULT 1,
                research_visible INTEGER NOT NULL DEFAULT 1,
                topic_tags_json TEXT NOT NULL DEFAULT '[]',
                content_summary TEXT NOT NULL DEFAULT '',
                approved_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS curated_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                curated_document_id INTEGER NOT NULL REFERENCES curated_documents(id) ON DELETE CASCADE,
                raw_chunk_id INTEGER REFERENCES raw_chunks(id) ON DELETE SET NULL,
                chunk_index INTEGER NOT NULL,
                heading TEXT NOT NULL DEFAULT '',
                content TEXT NOT NULL,
                scenario TEXT NOT NULL DEFAULT '',
                topic_tags_json TEXT NOT NULL DEFAULT '[]',
                patient_visible INTEGER NOT NULL DEFAULT 0,
                doctor_visible INTEGER NOT NULL DEFAULT 1,
                research_visible INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(curated_document_id, chunk_index)
            );

            CREATE TABLE IF NOT EXISTS aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                alias TEXT NOT NULL UNIQUE,
                canonical TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT '',
                weight REAL NOT NULL DEFAULT 1.0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS review_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_scope TEXT NOT NULL,
                document_id INTEGER NOT NULL,
                status TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                reviewer TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS import_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT NOT NULL,
                source_bucket TEXT NOT NULL DEFAULT '',
                query TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL,
                fetched_count INTEGER NOT NULL DEFAULT 0,
                imported_count INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                started_at TEXT NOT NULL,
                finished_at TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS answer_citations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                output_type TEXT NOT NULL,
                output_id TEXT NOT NULL,
                chunk_scope TEXT NOT NULL,
                chunk_id INTEGER NOT NULL,
                citation_label TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_raw_documents_status ON raw_documents(review_status);
            CREATE INDEX IF NOT EXISTS idx_raw_documents_bucket ON raw_documents(source_bucket);
            CREATE INDEX IF NOT EXISTS idx_curated_documents_status ON curated_documents(review_status);
            CREATE INDEX IF NOT EXISTS idx_import_runs_source ON import_runs(source_name, started_at DESC);

            CREATE VIRTUAL TABLE IF NOT EXISTS raw_chunks_fts USING fts5(
                chunk_id UNINDEXED,
                document_id UNINDEXED,
                title,
                heading,
                content,
                tags
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS curated_chunks_fts USING fts5(
                chunk_id UNINDEXED,
                document_id UNINDEXED,
                title,
                heading,
                content,
                tags
            );
            """
        )
        conn.commit()
        _seed_from_yaml(conn)
        if seed_curated_snapshot and settings.rhinitis_evidence_seed_snapshot_enabled:
            _seed_curated_snapshot(conn)
        _rebuild_fts(conn)


def evidence_stats() -> dict[str, Any]:
    with closing(_connect()) as conn:
        raw_total = _scalar(conn, "SELECT COUNT(*) FROM raw_documents")
        curated_total = _scalar(conn, "SELECT COUNT(*) FROM curated_documents")
        approved_total = _scalar(conn, "SELECT COUNT(*) FROM raw_documents WHERE review_status = 'approved'")
        needs_review_total = _scalar(conn, "SELECT COUNT(*) FROM raw_documents WHERE review_status = 'needs_review'")
        candidate_total = _scalar(conn, "SELECT COUNT(*) FROM raw_documents WHERE review_status = 'candidate'")
        rejected_total = _scalar(conn, "SELECT COUNT(*) FROM raw_documents WHERE review_status IN ('rejected', 'deprecated')")
        raw_chunks = _scalar(conn, "SELECT COUNT(*) FROM raw_chunks")
        curated_chunks = _scalar(conn, "SELECT COUNT(*) FROM curated_chunks")
        aliases = _scalar(conn, "SELECT COUNT(*) FROM aliases")
        by_bucket = _group_count(conn, "raw_documents", "source_bucket")
        by_status = _group_count(conn, "raw_documents", "review_status")
        by_level = _group_count(conn, "raw_documents", "evidence_level")
        latest_runs = [
            _row_to_dict(row)
            for row in conn.execute(
                """
                SELECT id, source_name, source_bucket, query, status, fetched_count, imported_count,
                       error, started_at, finished_at, metadata_json
                FROM import_runs
                ORDER BY id DESC
                LIMIT 8
                """
            ).fetchall()
        ]
    return {
        "raw_documents": raw_total,
        "curated_documents": curated_total,
        "approved_documents": approved_total,
        "needs_review_documents": needs_review_total,
        "candidate_documents": candidate_total,
        "excluded_documents": rejected_total,
        "raw_chunks": raw_chunks,
        "curated_chunks": curated_chunks,
        "aliases": aliases,
        "by_bucket": by_bucket,
        "by_status": by_status,
        "by_evidence_level": by_level,
        "latest_import_runs": latest_runs,
        "review_writes_enabled": settings.rhinitis_evidence_review_enabled,
    }


def review_queue(
    *,
    status: str = "needs_review",
    source_bucket: str = "",
    evidence_level: str = "",
    topic_tag: str = "",
    limit: int = 20,
    offset: int = 0,
) -> dict[str, Any]:
    normalized_status = status if status in VALID_REVIEW_STATUSES else "needs_review"
    normalized_bucket = " ".join((source_bucket or "").split()).strip()
    normalized_level = " ".join((evidence_level or "").split()).strip()
    normalized_tag = " ".join((topic_tag or "").split()).strip()
    limit = max(1, min(int(limit), 50))
    offset = max(0, int(offset or 0))

    clauses = ["review_status = ?"]
    params: list[Any] = [normalized_status]
    if normalized_bucket:
        clauses.append("source_bucket = ?")
        params.append(normalized_bucket)
    if normalized_level:
        clauses.append("evidence_level = ?")
        params.append(normalized_level)
    if normalized_tag:
        clauses.append("topic_tags_json LIKE ?")
        params.append(f"%{normalized_tag}%")
    where_sql = " AND ".join(clauses)

    with closing(_connect()) as conn:
        total = _scalar(conn, f"SELECT COUNT(*) FROM raw_documents WHERE {where_sql}", params)
        rows = conn.execute(
            f"""
            SELECT *
            FROM raw_documents
            WHERE {where_sql}
            ORDER BY
              CASE source_bucket
                WHEN 'guideline_candidates' THEN 1
                WHEN 'drug_candidates' THEN 2
                WHEN 'literature_candidates' THEN 3
                WHEN 'hospital_education_candidates' THEN 4
                WHEN 'environment_candidates' THEN 5
                WHEN 'trial_candidates' THEN 6
                ELSE 7
              END ASC,
              CASE evidence_level
                WHEN 'guideline' THEN 1
                WHEN 'consensus' THEN 2
                WHEN 'clinical_pathway' THEN 3
                WHEN 'meta_analysis' THEN 4
                WHEN 'systematic_review' THEN 5
                WHEN 'rct' THEN 6
                WHEN 'drug_label' THEN 7
                WHEN 'review' THEN 8
                ELSE 9
              END ASC,
              year DESC,
              id ASC
            LIMIT ? OFFSET ?
            """,
            [*params, limit, offset],
        ).fetchall()
    return {
        "status": normalized_status,
        "source_bucket": normalized_bucket,
        "evidence_level": normalized_level,
        "topic_tag": normalized_tag,
        "limit": limit,
        "offset": offset,
        "total": total,
        "review_writes_enabled": settings.rhinitis_evidence_review_enabled,
        "results": [_review_queue_item(row) for row in rows],
    }


def review_pack() -> dict[str, Any]:
    seen_document_ids: set[int] = set()
    groups: list[dict[str, Any]] = []
    with closing(_connect()) as conn:
        for group in CURATION_PACK_GROUPS:
            rows = _review_pack_rows(conn, group, seen_document_ids)
            items = []
            for row in rows:
                seen_document_ids.add(int(row["id"]))
                items.append(_review_pack_item(row, group))
            groups.append(
                {
                    "id": group["id"],
                    "label": group["label"],
                    "target": group["target"],
                    "count": len(items),
                    "items": items,
                }
            )
    return {
        "review_writes_enabled": settings.rhinitis_evidence_review_enabled,
        "total": sum(group["count"] for group in groups),
        "target": sum(int(group["target"]) for group in CURATION_PACK_GROUPS),
        "groups": groups,
    }


def review_evidence_batch(
    *,
    document_ids: Iterable[int],
    status: str,
    note: str = "",
    reviewer: str = "",
    patient_visible: bool | None = None,
    doctor_visible: bool | None = None,
) -> dict[str, Any]:
    normalized_ids: list[int] = []
    seen: set[int] = set()
    for raw_id in document_ids:
        doc_id = int(raw_id)
        if doc_id > 0 and doc_id not in seen:
            seen.add(doc_id)
            normalized_ids.append(doc_id)
    if not normalized_ids:
        return {"status": status, "updated_count": 0, "results": [], "errors": []}
    if len(normalized_ids) > 50:
        raise ValueError("batch review supports at most 50 documents")

    updated = []
    errors = []
    for document_id in normalized_ids:
        try:
            reviewed = review_evidence_document(
                document_scope="raw",
                document_id=document_id,
                status=status,
                note=note,
                reviewer=reviewer,
                patient_visible=patient_visible,
                doctor_visible=doctor_visible,
            )
            updated.append(
                {
                    "document_id": document_id,
                    "review_status": reviewed.get("review_status"),
                    "title": reviewed.get("title"),
                }
            )
        except ValueError as exc:
            errors.append({"document_id": document_id, "error": str(exc)})
    return {
        "status": status,
        "updated_count": len(updated),
        "error_count": len(errors),
        "results": updated,
        "errors": errors,
    }


def search_evidence(
    query: str,
    *,
    scope: str = "curated",
    scenario: str = "",
    source_bucket: str = "",
    limit: int = 8,
) -> dict[str, Any]:
    normalized_scope = scope if scope in VALID_SCOPES else "curated"
    normalized_query = " ".join((query or "").split()).strip()
    if not normalized_query:
        return {"query": normalized_query, "scope": normalized_scope, "results": []}

    expanded_terms = _expand_query_terms(normalized_query)
    match_query = _build_fts_query(expanded_terms)
    limit = max(1, min(int(limit), 20))
    normalized_bucket = " ".join((source_bucket or "").split()).strip()

    with closing(_connect()) as conn:
        rows = _fts_search(conn, normalized_query, match_query, normalized_scope, scenario, normalized_bucket, limit)
        if len(rows) < limit:
            rows = _merge_results(
                rows,
                _like_search(conn, expanded_terms, normalized_scope, scenario, normalized_bucket, limit),
                limit,
            )
    return {
        "query": normalized_query,
        "scope": normalized_scope,
        "source_bucket": normalized_bucket,
        "expanded_terms": expanded_terms[:12],
        "results": rows,
    }


def record_answer_citations(
    *,
    output_type: str,
    output_id: str,
    citations: Iterable[dict[str, Any]],
    chunk_scope: str = "curated",
) -> list[dict[str, Any]]:
    normalized_type = " ".join((output_type or "").split()).strip()
    normalized_output_id = " ".join((output_id or "").split()).strip()
    normalized_scope = chunk_scope if chunk_scope in VALID_SCOPES else "curated"
    if not normalized_type or not normalized_output_id:
        raise ValueError("output_type and output_id are required")

    now = _utc_now()
    rows: list[dict[str, Any]] = []
    seen: set[int] = set()
    with closing(_connect()) as conn:
        for citation in citations:
            chunk_id = int(citation.get("chunk_id") or 0)
            if chunk_id <= 0 or chunk_id in seen:
                continue
            seen.add(chunk_id)
            label = str(citation.get("citation_label") or citation.get("label") or "").strip()
            cursor = conn.execute(
                """
                INSERT INTO answer_citations (output_type, output_id, chunk_scope, chunk_id, citation_label, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (normalized_type, normalized_output_id, normalized_scope, chunk_id, label[:200], now),
            )
            rows.append(
                {
                    "id": int(cursor.lastrowid),
                    "output_type": normalized_type,
                    "output_id": normalized_output_id,
                    "chunk_scope": normalized_scope,
                    "chunk_id": chunk_id,
                    "citation_label": label[:200],
                    "created_at": now,
                }
            )
        conn.commit()
    return rows


def list_answer_citations(output_id: str, *, output_type: str = "") -> list[dict[str, Any]]:
    normalized_output_id = " ".join((output_id or "").split()).strip()
    normalized_type = " ".join((output_type or "").split()).strip()
    if not normalized_output_id:
        return []
    clauses = ["output_id = ?"]
    params: list[Any] = [normalized_output_id]
    if normalized_type:
        clauses.append("output_type = ?")
        params.append(normalized_type)
    with closing(_connect()) as conn:
        rows = conn.execute(
            f"""
            SELECT id, output_type, output_id, chunk_scope, chunk_id, citation_label, created_at
            FROM answer_citations
            WHERE {' AND '.join(clauses)}
            ORDER BY id ASC
            """,
            params,
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def get_evidence_document(document_id: int, *, scope: str = "raw") -> dict[str, Any] | None:
    normalized_scope = scope if scope in VALID_SCOPES else "raw"
    doc_table = "curated_documents" if normalized_scope == "curated" else "raw_documents"
    chunk_table = "curated_chunks" if normalized_scope == "curated" else "raw_chunks"
    fk = "curated_document_id" if normalized_scope == "curated" else "document_id"

    with closing(_connect()) as conn:
        row = conn.execute(f"SELECT * FROM {doc_table} WHERE id = ?", (int(document_id),)).fetchone()
        if not row:
            return None
        chunks = conn.execute(
            f"SELECT * FROM {chunk_table} WHERE {fk} = ? ORDER BY chunk_index ASC",
            (int(document_id),),
        ).fetchall()
        notes = conn.execute(
            """
            SELECT id, document_scope, document_id, status, note, reviewer, created_at
            FROM review_notes
            WHERE document_scope = ? AND document_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 20
            """,
            (normalized_scope, int(document_id)),
        ).fetchall()
    payload = _document_payload(row)
    payload["scope"] = normalized_scope
    payload["chunks"] = [_chunk_payload(chunk) for chunk in chunks]
    payload["review_notes"] = [_row_to_dict(note) for note in notes]
    return payload


def review_evidence_document(
    *,
    document_scope: str,
    document_id: int,
    status: str,
    note: str = "",
    reviewer: str = "",
    patient_visible: bool | None = None,
    doctor_visible: bool | None = None,
) -> dict[str, Any]:
    normalized_scope = document_scope if document_scope in VALID_SCOPES else "raw"
    normalized_status = status if status in VALID_REVIEW_STATUSES else "needs_review"
    now = _utc_now()
    with closing(_connect()) as conn:
        if normalized_scope == "raw":
            doc = conn.execute("SELECT * FROM raw_documents WHERE id = ?", (int(document_id),)).fetchone()
            if not doc:
                raise ValueError("raw document not found")
            updates = ["review_status = ?", "updated_at = ?"]
            params: list[Any] = [normalized_status, now]
            if patient_visible is not None:
                updates.append("patient_visible = ?")
                params.append(int(bool(patient_visible)))
            if doctor_visible is not None:
                updates.append("doctor_visible = ?")
                params.append(int(bool(doctor_visible)))
            params.append(int(document_id))
            conn.execute(f"UPDATE raw_documents SET {', '.join(updates)} WHERE id = ?", params)
            conn.execute(
                """
                UPDATE raw_chunks
                SET patient_visible = COALESCE(?, patient_visible),
                    doctor_visible = COALESCE(?, doctor_visible),
                    updated_at = ?
                WHERE document_id = ?
                """,
                (
                    None if patient_visible is None else int(bool(patient_visible)),
                    None if doctor_visible is None else int(bool(doctor_visible)),
                    now,
                    int(document_id),
                ),
            )
            conn.execute(
                """
                INSERT INTO review_notes (document_scope, document_id, status, note, reviewer, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (normalized_scope, int(document_id), normalized_status, note.strip(), reviewer.strip(), now),
            )
            if normalized_status == "approved":
                _promote_raw_document(conn, int(document_id), now)
            elif normalized_status in {"rejected", "deprecated"}:
                _delete_curated_by_raw_id(conn, int(document_id))
            conn.commit()
            _rebuild_fts(conn)
            return get_evidence_document(document_id, scope="raw") or {}

        doc = conn.execute("SELECT * FROM curated_documents WHERE id = ?", (int(document_id),)).fetchone()
        if not doc:
            raise ValueError("curated document not found")
        conn.execute(
            "UPDATE curated_documents SET review_status = ?, updated_at = ? WHERE id = ?",
            (normalized_status, now, int(document_id)),
        )
        conn.execute(
            """
            INSERT INTO review_notes (document_scope, document_id, status, note, reviewer, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (normalized_scope, int(document_id), normalized_status, note.strip(), reviewer.strip(), now),
        )
        conn.commit()
        _rebuild_fts(conn)
    return get_evidence_document(document_id, scope="curated") or {}


def record_import_run(
    *,
    source_name: str,
    source_bucket: str = "",
    query: str = "",
    status: str,
    fetched_count: int = 0,
    imported_count: int = 0,
    error: str = "",
    metadata: dict[str, Any] | None = None,
    started_at: str | None = None,
) -> dict[str, Any]:
    now = _utc_now()
    started = started_at or now
    with closing(_connect()) as conn:
        cursor = conn.execute(
            """
            INSERT INTO import_runs (
                source_name, source_bucket, query, status, fetched_count, imported_count,
                error, started_at, finished_at, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_name.strip(),
                source_bucket.strip(),
                query.strip(),
                status.strip(),
                int(fetched_count or 0),
                int(imported_count or 0),
                error.strip(),
                started,
                now,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM import_runs WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return _row_to_dict(row)


def upsert_raw_document(document: dict[str, Any]) -> tuple[int, bool]:
    now = _utc_now()
    source_key = str(document["source_key"]).strip()
    payload = _normalize_document(document)
    with closing(_connect()) as conn:
        existing = conn.execute("SELECT id FROM raw_documents WHERE source_key = ?", (source_key,)).fetchone()
        if existing:
            row_id = int(existing["id"])
            conn.execute(
                """
                UPDATE raw_documents
                SET source_bucket = ?, source_type = ?, title = ?, url = ?, pmid = ?, pmcid = ?,
                    doi = ?, year = ?, journal_or_org = ?, language = ?, evidence_level = ?,
                    review_status = ?, license_status = ?, open_access = ?, patient_visible = ?,
                    doctor_visible = ?, research_visible = ?, topic_tags_json = ?, content_summary = ?,
                    retrieved_at = ?, updated_at = ?, raw_payload_json = ?
                WHERE id = ?
                """,
                (
                    payload["source_bucket"],
                    payload["source_type"],
                    payload["title"],
                    payload["url"],
                    payload["pmid"],
                    payload["pmcid"],
                    payload["doi"],
                    payload["year"],
                    payload["journal_or_org"],
                    payload["language"],
                    payload["evidence_level"],
                    payload["review_status"],
                    payload["license_status"],
                    payload["open_access"],
                    payload["patient_visible"],
                    payload["doctor_visible"],
                    payload["research_visible"],
                    payload["topic_tags_json"],
                    payload["content_summary"],
                    payload["retrieved_at"],
                    now,
                    payload["raw_payload_json"],
                    row_id,
                ),
            )
            created = False
        else:
            cursor = conn.execute(
                """
                INSERT INTO raw_documents (
                    source_key, source_bucket, source_type, title, url, pmid, pmcid, doi, year,
                    journal_or_org, language, evidence_level, review_status, license_status,
                    open_access, patient_visible, doctor_visible, research_visible, topic_tags_json,
                    content_summary, retrieved_at, created_at, updated_at, raw_payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    source_key,
                    payload["source_bucket"],
                    payload["source_type"],
                    payload["title"],
                    payload["url"],
                    payload["pmid"],
                    payload["pmcid"],
                    payload["doi"],
                    payload["year"],
                    payload["journal_or_org"],
                    payload["language"],
                    payload["evidence_level"],
                    payload["review_status"],
                    payload["license_status"],
                    payload["open_access"],
                    payload["patient_visible"],
                    payload["doctor_visible"],
                    payload["research_visible"],
                    payload["topic_tags_json"],
                    payload["content_summary"],
                    payload["retrieved_at"],
                    now,
                    now,
                    payload["raw_payload_json"],
                ),
            )
            row_id = int(cursor.lastrowid)
            created = True

        conn.execute("DELETE FROM raw_chunks WHERE document_id = ?", (row_id,))
        for index, chunk in enumerate(document.get("chunks") or [{"heading": "摘要", "content": payload["content_summary"]}], start=1):
            conn.execute(
                """
                INSERT INTO raw_chunks (
                    document_id, chunk_index, heading, content, scenario, topic_tags_json,
                    patient_visible, doctor_visible, research_visible, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row_id,
                    index,
                    str(chunk.get("heading") or "").strip(),
                    str(chunk.get("content") or "").strip(),
                    str(chunk.get("scenario") or "").strip(),
                    json.dumps(_normalize_list(chunk.get("topic_tags") or document.get("topic_tags")), ensure_ascii=False),
                    _bool_int(chunk.get("patient_visible", document.get("patient_visible", False))),
                    _bool_int(chunk.get("doctor_visible", document.get("doctor_visible", True))),
                    _bool_int(chunk.get("research_visible", document.get("research_visible", True))),
                    now,
                    now,
                ),
            )
        if payload["review_status"] == "approved":
            _promote_raw_document(conn, row_id, now)
        conn.commit()
        _rebuild_fts(conn)
    return row_id, created


def import_curated_snapshot(snapshot_path: Path | str | None = None) -> dict[str, Any]:
    init_rhinitis_evidence_db(seed_curated_snapshot=False)
    path = Path(snapshot_path) if snapshot_path else CURATED_SEED_PATH
    with closing(_connect()) as conn:
        result = _import_curated_snapshot_in_conn(conn, path)
        _rebuild_fts(conn)
    return result


def _seed_from_yaml(conn: sqlite3.Connection) -> None:
    if not SEED_SOURCE_PATH.exists():
        return
    payload = yaml.safe_load(SEED_SOURCE_PATH.read_text(encoding="utf-8")) or {}
    for alias in payload.get("aliases", []):
        _upsert_alias(conn, alias)
    for document in payload.get("documents", []):
        _upsert_raw_document_in_conn(conn, document)
    conn.commit()


def _seed_curated_snapshot(conn: sqlite3.Connection) -> dict[str, Any]:
    return _import_curated_snapshot_in_conn(conn, CURATED_SEED_PATH)


def _import_curated_snapshot_in_conn(conn: sqlite3.Connection, path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "snapshot_path": str(path),
            "status": "missing",
            "document_count": 0,
            "created_count": 0,
            "updated_count": 0,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid curated evidence snapshot: {path}") from exc

    documents = payload.get("documents") or []
    if not isinstance(documents, list):
        raise ValueError("curated evidence snapshot documents must be a list")

    created_count = 0
    updated_count = 0
    for raw_document in documents:
        if not isinstance(raw_document, dict):
            continue
        document = _snapshot_document_for_import(raw_document, payload)
        source_key = str(document.get("source_key") or "").strip()
        if not source_key:
            continue
        existing = conn.execute("SELECT id FROM raw_documents WHERE source_key = ?", (source_key,)).fetchone()
        _upsert_raw_document_in_conn(conn, document)
        if existing:
            updated_count += 1
        else:
            created_count += 1
    conn.commit()
    return {
        "snapshot_path": str(path),
        "status": "imported",
        "snapshot_version": payload.get("snapshot_version"),
        "exported_at": payload.get("exported_at"),
        "document_count": len(documents),
        "created_count": created_count,
        "updated_count": updated_count,
    }


def _snapshot_document_for_import(document: dict[str, Any], snapshot_payload: dict[str, Any]) -> dict[str, Any]:
    raw_payload = document.get("raw_payload") if isinstance(document.get("raw_payload"), dict) else {}
    raw_payload = {
        **raw_payload,
        "curated_snapshot": {
            "snapshot_version": snapshot_payload.get("snapshot_version"),
            "exported_at": snapshot_payload.get("exported_at"),
            "source": snapshot_payload.get("source") or "knowledge/rhinitis_curated_evidence.json",
        },
    }
    imported = {
        key: document.get(key)
        for key in [
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
        ]
    }
    imported["review_status"] = "approved"
    imported["raw_payload"] = raw_payload
    imported["chunks"] = document.get("chunks") if isinstance(document.get("chunks"), list) else []
    return imported


def _upsert_raw_document_in_conn(conn: sqlite3.Connection, document: dict[str, Any]) -> int:
    now = _utc_now()
    source_key = str(document["source_key"]).strip()
    payload = _normalize_document(document)
    existing = conn.execute("SELECT id FROM raw_documents WHERE source_key = ?", (source_key,)).fetchone()
    if existing:
        row_id = int(existing["id"])
        conn.execute(
            """
            UPDATE raw_documents
            SET source_bucket = ?, source_type = ?, title = ?, url = ?, pmid = ?, pmcid = ?,
                doi = ?, year = ?, journal_or_org = ?, language = ?, evidence_level = ?,
                review_status = ?, license_status = ?, open_access = ?, patient_visible = ?,
                doctor_visible = ?, research_visible = ?, topic_tags_json = ?, content_summary = ?,
                retrieved_at = ?, updated_at = ?, raw_payload_json = ?
            WHERE id = ?
            """,
            (
                payload["source_bucket"],
                payload["source_type"],
                payload["title"],
                payload["url"],
                payload["pmid"],
                payload["pmcid"],
                payload["doi"],
                payload["year"],
                payload["journal_or_org"],
                payload["language"],
                payload["evidence_level"],
                payload["review_status"],
                payload["license_status"],
                payload["open_access"],
                payload["patient_visible"],
                payload["doctor_visible"],
                payload["research_visible"],
                payload["topic_tags_json"],
                payload["content_summary"],
                payload["retrieved_at"],
                now,
                payload["raw_payload_json"],
                row_id,
            ),
        )
    else:
        cursor = conn.execute(
            """
            INSERT INTO raw_documents (
                source_key, source_bucket, source_type, title, url, pmid, pmcid, doi, year,
                journal_or_org, language, evidence_level, review_status, license_status,
                open_access, patient_visible, doctor_visible, research_visible, topic_tags_json,
                content_summary, retrieved_at, created_at, updated_at, raw_payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_key,
                payload["source_bucket"],
                payload["source_type"],
                payload["title"],
                payload["url"],
                payload["pmid"],
                payload["pmcid"],
                payload["doi"],
                payload["year"],
                payload["journal_or_org"],
                payload["language"],
                payload["evidence_level"],
                payload["review_status"],
                payload["license_status"],
                payload["open_access"],
                payload["patient_visible"],
                payload["doctor_visible"],
                payload["research_visible"],
                payload["topic_tags_json"],
                payload["content_summary"],
                payload["retrieved_at"],
                now,
                now,
                payload["raw_payload_json"],
            ),
        )
        row_id = int(cursor.lastrowid)

    conn.execute("DELETE FROM raw_chunks WHERE document_id = ?", (row_id,))
    for index, chunk in enumerate(document.get("chunks") or [{"heading": "摘要", "content": payload["content_summary"]}], start=1):
        content = str(chunk.get("content") or "").strip()
        if not content:
            continue
        conn.execute(
            """
            INSERT INTO raw_chunks (
                document_id, chunk_index, heading, content, scenario, topic_tags_json,
                patient_visible, doctor_visible, research_visible, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                index,
                str(chunk.get("heading") or "").strip(),
                content,
                str(chunk.get("scenario") or "").strip(),
                json.dumps(_normalize_list(chunk.get("topic_tags") or document.get("topic_tags")), ensure_ascii=False),
                _bool_int(chunk.get("patient_visible", document.get("patient_visible", False))),
                _bool_int(chunk.get("doctor_visible", document.get("doctor_visible", True))),
                _bool_int(chunk.get("research_visible", document.get("research_visible", True))),
                now,
                now,
            ),
        )
    if payload["review_status"] == "approved":
        _promote_raw_document(conn, row_id, now)
    return row_id


def _promote_raw_document(conn: sqlite3.Connection, raw_document_id: int, now: str) -> int:
    doc = conn.execute("SELECT * FROM raw_documents WHERE id = ?", (raw_document_id,)).fetchone()
    if not doc:
        raise ValueError("raw document not found")

    existing = conn.execute(
        "SELECT id FROM curated_documents WHERE source_key = ?",
        (doc["source_key"],),
    ).fetchone()
    values = (
        raw_document_id,
        doc["source_key"],
        doc["source_bucket"],
        doc["source_type"],
        doc["title"],
        doc["url"],
        doc["pmid"],
        doc["pmcid"],
        doc["doi"],
        doc["year"],
        doc["journal_or_org"],
        doc["language"],
        doc["evidence_level"],
        "approved",
        doc["license_status"],
        doc["open_access"],
        doc["patient_visible"],
        doc["doctor_visible"],
        doc["research_visible"],
        doc["topic_tags_json"],
        doc["content_summary"],
        now,
        now,
        now,
    )
    if existing:
        curated_id = int(existing["id"])
        conn.execute(
            """
            UPDATE curated_documents
            SET raw_document_id = ?, source_bucket = ?, source_type = ?, title = ?, url = ?,
                pmid = ?, pmcid = ?, doi = ?, year = ?, journal_or_org = ?, language = ?,
                evidence_level = ?, review_status = ?, license_status = ?, open_access = ?,
                patient_visible = ?, doctor_visible = ?, research_visible = ?, topic_tags_json = ?,
                content_summary = ?, approved_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                raw_document_id,
                doc["source_bucket"],
                doc["source_type"],
                doc["title"],
                doc["url"],
                doc["pmid"],
                doc["pmcid"],
                doc["doi"],
                doc["year"],
                doc["journal_or_org"],
                doc["language"],
                doc["evidence_level"],
                "approved",
                doc["license_status"],
                doc["open_access"],
                doc["patient_visible"],
                doc["doctor_visible"],
                doc["research_visible"],
                doc["topic_tags_json"],
                doc["content_summary"],
                now,
                now,
                curated_id,
            ),
        )
    else:
        cursor = conn.execute(
            """
            INSERT INTO curated_documents (
                raw_document_id, source_key, source_bucket, source_type, title, url, pmid,
                pmcid, doi, year, journal_or_org, language, evidence_level, review_status,
                license_status, open_access, patient_visible, doctor_visible, research_visible,
                topic_tags_json, content_summary, approved_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        curated_id = int(cursor.lastrowid)

    conn.execute("DELETE FROM curated_chunks WHERE curated_document_id = ?", (curated_id,))
    chunks = conn.execute(
        "SELECT * FROM raw_chunks WHERE document_id = ? ORDER BY chunk_index ASC",
        (raw_document_id,),
    ).fetchall()
    for chunk in chunks:
        conn.execute(
            """
            INSERT INTO curated_chunks (
                curated_document_id, raw_chunk_id, chunk_index, heading, content, scenario,
                topic_tags_json, patient_visible, doctor_visible, research_visible, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                curated_id,
                chunk["id"],
                chunk["chunk_index"],
                chunk["heading"],
                chunk["content"],
                chunk["scenario"],
                chunk["topic_tags_json"],
                chunk["patient_visible"],
                chunk["doctor_visible"],
                chunk["research_visible"],
                now,
                now,
            ),
        )
    return curated_id


def _delete_curated_by_raw_id(conn: sqlite3.Connection, raw_document_id: int) -> None:
    conn.execute("DELETE FROM curated_documents WHERE raw_document_id = ?", (raw_document_id,))


def _upsert_alias(conn: sqlite3.Connection, alias: dict[str, Any]) -> None:
    now = _utc_now()
    alias_text = str(alias.get("alias") or "").strip()
    canonical = str(alias.get("canonical") or "").strip()
    if not alias_text or not canonical:
        return
    conn.execute(
        """
        INSERT INTO aliases (alias, canonical, category, language, weight, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(alias) DO UPDATE SET
            canonical = excluded.canonical,
            category = excluded.category,
            language = excluded.language,
            weight = excluded.weight,
            updated_at = excluded.updated_at
        """,
        (
            alias_text,
            canonical,
            str(alias.get("category") or "").strip(),
            str(alias.get("language") or "").strip(),
            float(alias.get("weight") or 1.0),
            now,
            now,
        ),
    )


def _rebuild_fts(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM raw_chunks_fts")
    conn.execute("DELETE FROM curated_chunks_fts")
    for row in conn.execute(
        """
        SELECT c.id AS chunk_id, c.document_id, d.title, c.heading, c.content, c.topic_tags_json
        FROM raw_chunks c
        JOIN raw_documents d ON d.id = c.document_id
        """
    ).fetchall():
        conn.execute(
            "INSERT INTO raw_chunks_fts (chunk_id, document_id, title, heading, content, tags) VALUES (?, ?, ?, ?, ?, ?)",
            (
                row["chunk_id"],
                row["document_id"],
                row["title"],
                row["heading"],
                row["content"],
                " ".join(_json_list(row["topic_tags_json"])),
            ),
        )
    for row in conn.execute(
        """
        SELECT c.id AS chunk_id, c.curated_document_id AS document_id, d.title, c.heading, c.content, c.topic_tags_json
        FROM curated_chunks c
        JOIN curated_documents d ON d.id = c.curated_document_id
        WHERE d.review_status = 'approved'
        """
    ).fetchall():
        conn.execute(
            "INSERT INTO curated_chunks_fts (chunk_id, document_id, title, heading, content, tags) VALUES (?, ?, ?, ?, ?, ?)",
            (
                row["chunk_id"],
                row["document_id"],
                row["title"],
                row["heading"],
                row["content"],
                " ".join(_json_list(row["topic_tags_json"])),
            ),
        )
    conn.commit()


def _fts_search(
    conn: sqlite3.Connection,
    query: str,
    match_query: str,
    scope: str,
    scenario: str,
    source_bucket: str,
    limit: int,
) -> list[dict[str, Any]]:
    if not match_query:
        return []
    bucket_clause = "AND d.source_bucket = ?" if source_bucket else ""
    if scope == "curated":
        sql = f"""
            SELECT d.*, c.id AS chunk_id, c.heading, c.content, c.scenario, c.topic_tags_json AS chunk_tags,
                   bm25(curated_chunks_fts) AS bm25_score
            FROM curated_chunks_fts
            JOIN curated_chunks c ON c.id = curated_chunks_fts.chunk_id
            JOIN curated_documents d ON d.id = c.curated_document_id
            WHERE curated_chunks_fts MATCH ?
              AND d.review_status = 'approved'
              AND d.patient_visible >= CASE WHEN ? = 'patient' THEN 1 ELSE 0 END
              AND d.doctor_visible >= CASE WHEN ? = 'doctor' THEN 1 ELSE 0 END
              {bucket_clause}
            LIMIT ?
        """
    else:
        sql = f"""
            SELECT d.*, c.id AS chunk_id, c.heading, c.content, c.scenario, c.topic_tags_json AS chunk_tags,
                   bm25(raw_chunks_fts) AS bm25_score
            FROM raw_chunks_fts
            JOIN raw_chunks c ON c.id = raw_chunks_fts.chunk_id
            JOIN raw_documents d ON d.id = c.document_id
            WHERE raw_chunks_fts MATCH ?
              AND d.review_status NOT IN ('rejected', 'deprecated')
              {bucket_clause}
            LIMIT ?
        """
    try:
        if scope == "curated":
            params: list[Any] = [match_query, scenario, scenario]
        else:
            params = [match_query]
        if source_bucket:
            params.append(source_bucket)
        params.append(limit * 3)
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return _rank_rows(rows, query, scenario, limit)


def _like_search(
    conn: sqlite3.Connection,
    terms: list[str],
    scope: str,
    scenario: str,
    source_bucket: str,
    limit: int,
) -> list[dict[str, Any]]:
    like_terms = [term for term in terms if term][:8]
    if not like_terms:
        return []
    clauses = []
    params: list[Any] = []
    for term in like_terms:
        clauses.append("(d.title LIKE ? OR c.heading LIKE ? OR c.content LIKE ? OR c.topic_tags_json LIKE ?)")
        like = f"%{term}%"
        params.extend([like, like, like, like])
    bucket_clause = "AND d.source_bucket = ?" if source_bucket else ""

    if scope == "curated":
        sql = f"""
            SELECT d.*, c.id AS chunk_id, c.heading, c.content, c.scenario, c.topic_tags_json AS chunk_tags,
                   0 AS bm25_score
            FROM curated_chunks c
            JOIN curated_documents d ON d.id = c.curated_document_id
            WHERE ({' OR '.join(clauses)})
              AND d.review_status = 'approved'
              AND d.patient_visible >= CASE WHEN ? = 'patient' THEN 1 ELSE 0 END
              AND d.doctor_visible >= CASE WHEN ? = 'doctor' THEN 1 ELSE 0 END
              {bucket_clause}
            LIMIT ?
        """
        params.extend([scenario, scenario])
    else:
        sql = f"""
            SELECT d.*, c.id AS chunk_id, c.heading, c.content, c.scenario, c.topic_tags_json AS chunk_tags,
                   0 AS bm25_score
            FROM raw_chunks c
            JOIN raw_documents d ON d.id = c.document_id
            WHERE ({' OR '.join(clauses)})
              AND d.review_status NOT IN ('rejected', 'deprecated')
              {bucket_clause}
            LIMIT ?
        """
    if source_bucket:
        params.append(source_bucket)
    params.append(limit * 3)
    rows = conn.execute(sql, params).fetchall()
    return _rank_rows(rows, " ".join(terms), scenario, limit)


def _rank_rows(rows: Iterable[sqlite3.Row], query: str, scenario: str, limit: int) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    query_terms = set(_tokenize(query))
    for row in rows:
        key = (int(row["id"]), int(row["chunk_id"]))
        if key in seen:
            continue
        seen.add(key)
        tags = _json_list(row["chunk_tags"])
        content = str(row["content"] or "")
        title = str(row["title"] or "")
        overlap = len(query_terms & set(_tokenize(" ".join([title, content, " ".join(tags)]))))
        scenario_bonus = 14 if scenario and (row["scenario"] == scenario or scenario in tags) else 0
        evidence_bonus = EVIDENCE_WEIGHTS.get(row["evidence_level"], 20)
        status_bonus = STATUS_WEIGHTS.get(row["review_status"], -20)
        bm25_score = float(row["bm25_score"] or 0)
        score = evidence_bonus + status_bonus + scenario_bonus + (overlap * 5) - min(max(bm25_score, -20), 20)
        ranked.append(
            {
                "scope": "curated" if "approved_at" in row.keys() else "raw",
                "document_id": row["id"],
                "chunk_id": row["chunk_id"],
                "title": title,
                "heading": row["heading"],
                "snippet": _snippet(content),
                "url": row["url"],
                "pmid": row["pmid"],
                "pmcid": row["pmcid"],
                "doi": row["doi"],
                "year": row["year"],
                "journal_or_org": row["journal_or_org"],
                "source_bucket": row["source_bucket"],
                "source_type": row["source_type"],
                "evidence_level": row["evidence_level"],
                "review_status": row["review_status"],
                "patient_visible": bool(row["patient_visible"]),
                "doctor_visible": bool(row["doctor_visible"]),
                "topic_tags": tags,
                "score": round(score, 2),
            }
        )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked[:limit]


def _merge_results(left: list[dict[str, Any]], right: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str]] = set()
    for item in left + right:
        key = (int(item["document_id"]), int(item["chunk_id"]), item["scope"])
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    merged.sort(key=lambda item: item["score"], reverse=True)
    return merged[:limit]


def _expand_query_terms(query: str) -> list[str]:
    terms = _tokenize(query)
    with closing(_connect()) as conn:
        alias_rows = conn.execute("SELECT alias, canonical FROM aliases ORDER BY weight DESC").fetchall()
    compact_query = query.lower()
    for row in alias_rows:
        alias = str(row["alias"] or "")
        canonical = str(row["canonical"] or "")
        if alias and alias.lower() in compact_query:
            terms.extend(_tokenize(alias))
            terms.extend(_tokenize(canonical))
        elif canonical and canonical.lower() in compact_query:
            terms.extend(_tokenize(alias))
            terms.extend(_tokenize(canonical))
    deduped: list[str] = []
    seen: set[str] = set()
    for term in terms:
        if term not in seen:
            seen.add(term)
            deduped.append(term)
    return deduped


def _build_fts_query(terms: list[str]) -> str:
    cleaned = []
    for term in terms[:10]:
        safe = term.replace('"', "").strip()
        if safe:
            cleaned.append(f'"{safe}"')
    return " OR ".join(cleaned)


def _tokenize(text: str) -> list[str]:
    tokens = []
    for token in re.findall(r"[\w\u4e00-\u9fff]+", text.lower()):
        tokens.append(token)
        if re.search(r"[\u4e00-\u9fff]", token) and len(token) >= 2:
            tokens.extend(token[i : i + 2] for i in range(len(token) - 1))
            tokens.extend(token[i : i + 3] for i in range(max(0, len(token) - 2)))
    return [token for token in tokens if token]


def _normalize_document(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_bucket": str(document.get("source_bucket") or "literature_candidates").strip(),
        "source_type": str(document.get("source_type") or "paper").strip(),
        "title": str(document.get("title") or "").strip(),
        "url": str(document.get("url") or "").strip(),
        "pmid": str(document.get("pmid") or "").strip(),
        "pmcid": str(document.get("pmcid") or "").strip(),
        "doi": str(document.get("doi") or "").strip(),
        "year": _int_or_none(document.get("year")),
        "journal_or_org": str(document.get("journal_or_org") or "").strip(),
        "language": str(document.get("language") or "").strip(),
        "evidence_level": str(document.get("evidence_level") or "webpage").strip(),
        "review_status": str(document.get("review_status") or "candidate").strip(),
        "license_status": str(document.get("license_status") or "").strip(),
        "open_access": _bool_int(document.get("open_access", False)),
        "patient_visible": _bool_int(document.get("patient_visible", False)),
        "doctor_visible": _bool_int(document.get("doctor_visible", True)),
        "research_visible": _bool_int(document.get("research_visible", True)),
        "topic_tags_json": json.dumps(_normalize_list(document.get("topic_tags")), ensure_ascii=False),
        "content_summary": str(document.get("content_summary") or "").strip(),
        "retrieved_at": str(document.get("retrieved_at") or "").strip(),
        "raw_payload_json": json.dumps(document.get("raw_payload") or {}, ensure_ascii=False),
    }


def _document_payload(row: sqlite3.Row) -> dict[str, Any]:
    payload = _row_to_dict(row)
    payload["topic_tags"] = _json_list(row["topic_tags_json"])
    payload.pop("topic_tags_json", None)
    payload["open_access"] = bool(row["open_access"])
    payload["patient_visible"] = bool(row["patient_visible"])
    payload["doctor_visible"] = bool(row["doctor_visible"])
    payload["research_visible"] = bool(row["research_visible"])
    return payload


def _chunk_payload(row: sqlite3.Row) -> dict[str, Any]:
    payload = _row_to_dict(row)
    payload["topic_tags"] = _json_list(row["topic_tags_json"])
    payload.pop("topic_tags_json", None)
    payload["patient_visible"] = bool(row["patient_visible"])
    payload["doctor_visible"] = bool(row["doctor_visible"])
    payload["research_visible"] = bool(row["research_visible"])
    return payload


def _review_pack_rows(
    conn: sqlite3.Connection,
    group: dict[str, Any],
    seen_document_ids: set[int],
) -> list[sqlite3.Row]:
    clauses = ["review_status = 'needs_review'"]
    params: list[Any] = []
    source_buckets = list(group.get("source_buckets") or [])
    evidence_levels = list(group.get("evidence_levels") or [])
    topic_tags = list(group.get("topic_tags") or [])
    if source_buckets:
        clauses.append(f"source_bucket IN ({','.join('?' for _ in source_buckets)})")
        params.extend(source_buckets)
    if evidence_levels:
        clauses.append(f"evidence_level IN ({','.join('?' for _ in evidence_levels)})")
        params.extend(evidence_levels)
    if topic_tags:
        tag_clauses = []
        for tag in topic_tags:
            tag_clauses.append("topic_tags_json LIKE ?")
            params.append(f"%{tag}%")
        clauses.append(f"({' OR '.join(tag_clauses)})")
    if seen_document_ids:
        clauses.append(f"id NOT IN ({','.join('?' for _ in seen_document_ids)})")
        params.extend(sorted(seen_document_ids))

    rows = conn.execute(
        f"""
        SELECT *
        FROM raw_documents
        WHERE {' AND '.join(clauses)}
        ORDER BY
          CASE evidence_level
            WHEN 'guideline' THEN 1
            WHEN 'consensus' THEN 2
            WHEN 'clinical_pathway' THEN 3
            WHEN 'meta_analysis' THEN 4
            WHEN 'systematic_review' THEN 5
            WHEN 'rct' THEN 6
            WHEN 'drug_label' THEN 7
            WHEN 'review' THEN 8
            WHEN 'observational' THEN 9
            ELSE 10
          END ASC,
          CASE source_bucket
            WHEN 'guideline_candidates' THEN 1
            WHEN 'drug_candidates' THEN 2
            WHEN 'literature_candidates' THEN 3
            WHEN 'environment_candidates' THEN 4
            ELSE 5
          END ASC,
          year DESC,
          id ASC
        LIMIT ?
        """,
        [*params, int(group.get("target") or 8) * 4],
    ).fetchall()
    return rows[: int(group.get("target") or 8)]


def _review_queue_item(row: sqlite3.Row) -> dict[str, Any]:
    payload = _document_payload(row)
    raw_payload = payload.get("raw_payload") or {}
    screening = raw_payload.get("rescreening") or raw_payload.get("screening") or {}
    evidence_score = EVIDENCE_WEIGHTS.get(str(payload.get("evidence_level") or ""), 20)
    return {
        "document_id": payload["id"],
        "source_key": payload["source_key"],
        "title": payload["title"],
        "url": payload["url"],
        "pmid": payload["pmid"],
        "pmcid": payload["pmcid"],
        "doi": payload["doi"],
        "year": payload["year"],
        "journal_or_org": payload["journal_or_org"],
        "source_bucket": payload["source_bucket"],
        "source_type": payload["source_type"],
        "evidence_level": payload["evidence_level"],
        "review_status": payload["review_status"],
        "license_status": payload["license_status"],
        "open_access": payload["open_access"],
        "patient_visible": payload["patient_visible"],
        "doctor_visible": payload["doctor_visible"],
        "topic_tags": payload["topic_tags"],
        "content_summary": _snippet(payload.get("content_summary") or "", 360),
        "screening": screening if isinstance(screening, dict) else {},
        "priority_score": evidence_score + STATUS_WEIGHTS.get(payload["review_status"], 0),
    }


def _review_pack_item(row: sqlite3.Row, group: dict[str, Any]) -> dict[str, Any]:
    item = _review_queue_item(row)
    matched_tags = [
        tag
        for tag in group.get("topic_tags") or []
        if tag in item.get("topic_tags", [])
    ]
    reasons = [group["label"], item["evidence_level"]]
    if matched_tags:
        reasons.append(" / ".join(matched_tags[:3]))
    if item.get("year"):
        reasons.append(str(item["year"]))
    item["pack_group"] = group["id"]
    item["recommendation_reason"] = " · ".join(str(reason) for reason in reasons if reason)
    return item


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    result = dict(row)
    if "metadata_json" in result:
        try:
            result["metadata"] = json.loads(result.pop("metadata_json") or "{}")
        except json.JSONDecodeError:
            result["metadata"] = {}
    if "raw_payload_json" in result:
        try:
            result["raw_payload"] = json.loads(result.pop("raw_payload_json") or "{}")
        except json.JSONDecodeError:
            result["raw_payload"] = {}
    return result


def _group_count(conn: sqlite3.Connection, table: str, field: str) -> list[dict[str, Any]]:
    return [
        {"name": row["name"], "count": row["count"]}
        for row in conn.execute(
            f"SELECT {field} AS name, COUNT(*) AS count FROM {table} GROUP BY {field} ORDER BY count DESC, name ASC"
        ).fetchall()
    ]


def _scalar(conn: sqlite3.Connection, sql: str, params: Iterable[Any] = ()) -> int:
    return int(conn.execute(sql, tuple(params)).fetchone()[0])


def _snippet(content: str, max_len: int = 220) -> str:
    cleaned = re.sub(r"\s+", " ", content or "").strip()
    if len(cleaned) <= max_len:
        return cleaned
    return cleaned[: max_len - 1] + "…"


def _normalize_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, Iterable):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _json_list(value: str) -> list[str]:
    try:
        parsed = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return _normalize_list(parsed)


def _bool_int(value: Any) -> int:
    return 1 if bool(value) else 0


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
