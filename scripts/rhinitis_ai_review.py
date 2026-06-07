from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
import json
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - python-dotenv is in requirements, this keeps CLI usable.
    load_dotenv = None

if load_dotenv:
    load_dotenv(ROOT / ".env")

REVIEWER_VERSION = "rhinitis_evidence_reviewer_v1"
DEFAULT_MODEL = os.environ.get("RHINITIS_AI_REVIEW_MODEL") or os.environ.get("OPENAI_MODEL") or "gpt-5.5"
DEFAULT_REVIEW_DIR = Path(os.environ.get("RHINITIS_AI_REVIEW_DIR") or ROOT / "data" / "rhinitis_ai_review")
REVIEW_DECISIONS = {"ai_recommend_curate", "needs_human_spot_check", "reject"}
USE_FOR_VALUES = {"doctor_summary", "patient_education", "digital_human_script", "research_only"}
EVIDENCE_LEVELS = {
    "guideline",
    "consensus",
    "clinical_pathway",
    "systematic_review",
    "meta_analysis",
    "rct",
    "drug_label",
    "hospital_education",
    "review",
    "observational",
    "trial_registry",
    "environment",
    "webpage",
    "paper",
}


REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "document_id": {"type": "integer"},
        "decision": {"type": "string", "enum": sorted(REVIEW_DECISIONS)},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "evidence_level": {"type": "string", "enum": sorted(EVIDENCE_LEVELS)},
        "use_for": {
            "type": "array",
            "items": {"type": "string", "enum": sorted(USE_FOR_VALUES)},
            "minItems": 1,
        },
        "patient_visible": {"type": "boolean"},
        "doctor_visible": {"type": "boolean"},
        "topics": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 12,
        },
        "risk_flags": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 12,
        },
        "reason": {"type": "string", "minLength": 10, "maxLength": 1400},
        "human_check_needed": {"type": "boolean"},
        "summary_for_curated": {"type": "string", "minLength": 0, "maxLength": 1000},
        "citation_note": {"type": "string", "minLength": 0, "maxLength": 500},
    },
    "required": [
        "document_id",
        "decision",
        "confidence",
        "evidence_level",
        "use_for",
        "patient_visible",
        "doctor_visible",
        "topics",
        "risk_flags",
        "reason",
        "human_check_needed",
        "summary_for_curated",
        "citation_note",
    ],
}


REVIEWER_INSTRUCTIONS = """
你是鼻敏智诊项目的过敏性鼻炎医学证据预审 agent，按耳鼻咽喉科和变态反应学证据审查标准工作。

你的任务不是诊断患者，也不是代替医生终审。你的任务是审查候选资料是否适合进入鼻敏智诊精选证据库。

判断重点：
1. 是否确实与过敏性鼻炎、鼻炎诊疗、鼻内镜观察、过敏原检查、免疫治疗、常用药物、儿童/合并哮喘、环境诱因相关。
2. 是否适合用于医生端接诊摘要、患者宣教、数字人宣教脚本或仅研究检索。
3. 当前证据等级是否合理；必要时修正 evidence_level。
4. 是否存在药物剂量、儿童、孕妇、禁忌、自动诊断、图像诊断、证据冲突等风险。
5. 是否需要人工抽查。

Decision 规则：
- ai_recommend_curate：资料相关、可信、临床价值明确，适合进入医生端演示用精选库。
- needs_human_spot_check：资料可能有价值，但有边界、风险、不确定性、患者端风险或证据解释难度，需要人工抽查。
- reject：明显不相关、低价值、基础实验/动物实验为主、无可用临床信息，或摘要不足以支撑专病库使用。

可见性规则：
- doctor_visible 可以在资料适合医生摘要或医生端演示时设为 true。
- patient_visible 只有在低风险、通俗宣教、无剂量/禁忌/个体化治疗建议风险时才建议 true。
- 第一版系统回写时仍会默认把 AI 晋级资料 patient_visible 置为 false。

输出要求：
- 只输出符合 JSON schema 的 JSON。
- 不输出 Markdown、代码块或额外解释。
- reason 用中文，简洁说明为什么这样判断。
""".strip()


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def review_root() -> Path:
    root = DEFAULT_REVIEW_DIR
    root.mkdir(parents=True, exist_ok=True)
    (root / "batches").mkdir(parents=True, exist_ok=True)
    return root


def batch_id(status: str) -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{slugify(status or 'review')}"


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip())
    return value.strip("-").lower() or "batch"


def relative_to_batch(path: Path, batch_dir: Path) -> str:
    return str(path.relative_to(batch_dir))


def clamp_text(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text or "").strip()
    if max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def json_dump(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def json_load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def doc_filename(document_id: int, suffix: str = ".md") -> str:
    return f"doc_{int(document_id):06d}{suffix}"


def render_candidate_markdown(document: dict[str, Any], *, max_chars: int) -> str:
    chunks = document.get("chunks") or []
    chunk_budget = max(1200, max_chars // max(1, min(len(chunks), 6)))
    identifiers = [
        f"PMID: {document.get('pmid')}" if document.get("pmid") else "",
        f"PMCID: {document.get('pmcid')}" if document.get("pmcid") else "",
        f"DOI: {document.get('doi')}" if document.get("doi") else "",
    ]
    identifiers = [item for item in identifiers if item]
    lines = [
        f"# Evidence Candidate {document['id']}",
        "",
        "## Metadata",
        f"- Document ID: {document['id']}",
        f"- Source key: {document.get('source_key') or ''}",
        f"- Title: {document.get('title') or ''}",
        f"- Year: {document.get('year') or ''}",
        f"- Journal / Org: {document.get('journal_or_org') or ''}",
        f"- URL: {document.get('url') or ''}",
        f"- Identifiers: {'; '.join(identifiers) if identifiers else ''}",
        f"- Source type: {document.get('source_type') or ''}",
        f"- Internal source bucket: {document.get('source_bucket') or ''}",
        f"- Current evidence level guess: {document.get('evidence_level') or ''}",
        f"- Current review status: {document.get('review_status') or ''}",
        f"- Open access: {bool(document.get('open_access'))}",
        f"- License status: {document.get('license_status') or ''}",
        f"- Topic tags: {', '.join(document.get('topic_tags') or [])}",
        "",
        "## Abstract / Summary",
        clamp_text(document.get("content_summary") or "", max_chars),
        "",
        "## Evidence Chunks",
    ]
    if not chunks:
        lines.extend(["", "No chunks available."])
    for chunk in chunks:
        heading = chunk.get("heading") or f"Chunk {chunk.get('chunk_index') or ''}"
        content = clamp_text(chunk.get("content") or "", chunk_budget)
        lines.extend(
            [
                "",
                f"### {heading}",
                f"- Scenario: {chunk.get('scenario') or ''}",
                f"- Chunk tags: {', '.join(chunk.get('topic_tags') or [])}",
                "",
                content or "No content.",
            ]
        )
    lines.extend(
        [
            "",
            "## Reviewer Task",
            "请判断这条资料是否适合进入鼻敏智诊精选证据库，并按预审 schema 输出 JSON。",
            "注意：不要做患者诊断，不要生成处方剂量，不要把 AI 预审等同于医生终审。",
            "",
        ]
    )
    return "\n".join(lines)


def export_batch(
    *,
    limit: int,
    status: str,
    source_bucket: str = "",
    evidence_level: str = "",
    topic_tag: str = "",
    output_dir: Path | None = None,
    max_chars_per_doc: int = 12000,
) -> dict[str, Any]:
    from app.rhinitis_evidence import get_evidence_document, init_rhinitis_evidence_db, review_queue

    init_rhinitis_evidence_db()
    root = output_dir or review_root()
    batches_dir = root / "batches"
    batches_dir.mkdir(parents=True, exist_ok=True)
    current_batch_id = batch_id(status)
    batch_dir = batches_dir / current_batch_id
    candidates_dir = batch_dir / "candidates"
    reviews_dir = batch_dir / "reviews"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    reviews_dir.mkdir(parents=True, exist_ok=True)

    exported: list[dict[str, Any]] = []
    offset = 0
    remaining = max(1, int(limit))
    while remaining > 0:
        page = review_queue(
            status=status,
            source_bucket=source_bucket,
            evidence_level=evidence_level,
            topic_tag=topic_tag,
            limit=min(remaining, 50),
            offset=offset,
        )
        results = page.get("results") or []
        if not results:
            break
        for item in results:
            document_id = int(item["document_id"])
            document = get_evidence_document(document_id, scope="raw")
            if not document:
                continue
            path = candidates_dir / doc_filename(document_id)
            path.write_text(render_candidate_markdown(document, max_chars=max_chars_per_doc), encoding="utf-8")
            exported.append(
                {
                    "document_id": document_id,
                    "title": document.get("title") or "",
                    "candidate_path": relative_to_batch(path, batch_dir),
                    "review_json_path": f"reviews/{doc_filename(document_id, '.review.json')}",
                    "review_md_path": f"reviews/{doc_filename(document_id, '.review.md')}",
                }
            )
            remaining -= 1
            if remaining <= 0:
                break
        offset += len(results)

    manifest = {
        "batch_id": current_batch_id,
        "created_at": utc_now(),
        "reviewer_version": REVIEWER_VERSION,
        "default_model": DEFAULT_MODEL,
        "filters": {
            "status": status,
            "source_bucket": source_bucket,
            "evidence_level": evidence_level,
            "topic_tag": topic_tag,
            "limit": limit,
        },
        "document_count": len(exported),
        "candidates": exported,
    }
    json_dump(batch_dir / "manifest.json", manifest)
    (batch_dir / "reviewer_prompt.md").write_text(REVIEWER_INSTRUCTIONS + "\n", encoding="utf-8")
    return {"batch_dir": str(batch_dir), "manifest": manifest}


def resolve_batch(batch: str | Path, *, root: Path | None = None) -> Path:
    root = root or review_root()
    if str(batch) == "latest":
        candidates = sorted((root / "batches").glob("*"), key=lambda path: path.name)
        if not candidates:
            raise FileNotFoundError("No AI review batches found.")
        return candidates[-1]
    path = Path(batch)
    if path.exists():
        return path
    path = root / "batches" / str(batch)
    if path.exists():
        return path
    raise FileNotFoundError(f"Batch not found: {batch}")


def load_manifest(batch_dir: Path) -> dict[str, Any]:
    path = batch_dir / "manifest.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing manifest: {path}")
    return json_load(path)


def review_batch(
    *,
    batch: str | Path,
    model: str,
    mock: bool = False,
    overwrite: bool = False,
    max_docs: int | None = None,
    sleep_seconds: float = 0,
    stop_on_error: bool = False,
    workers: int = 1,
) -> dict[str, Any]:
    batch_dir = resolve_batch(batch)
    manifest = load_manifest(batch_dir)
    reviewed = []
    skipped = []
    errors = []
    candidates = manifest.get("candidates") or []
    selected_candidates = candidates if max_docs is None else candidates[: max(0, int(max_docs))]
    total_candidates = len(selected_candidates)
    workers = max(1, min(int(workers or 1), max(1, total_candidates)))
    progress_lock = threading.Lock()

    def log(message: str) -> None:
        with progress_lock:
            progress(message)

    def review_one(index: int, entry: dict[str, Any]) -> dict[str, Any]:
        candidate_path = batch_dir / entry["candidate_path"]
        review_json_path = batch_dir / entry["review_json_path"]
        review_md_path = batch_dir / entry["review_md_path"]
        error_json_path = review_json_path.with_suffix(".error.json")
        if review_json_path.exists() and not overwrite:
            log(f"[{index}/{total_candidates}] skip doc {entry['document_id']} existing review")
            return {"kind": "skipped", "document_id": entry["document_id"], "reason": "exists"}
        candidate_md = candidate_path.read_text(encoding="utf-8")
        log(f"[{index}/{total_candidates}] review doc {entry['document_id']} with {model}")
        try:
            if mock:
                review = mock_review(candidate_md, int(entry["document_id"]), model=model)
            else:
                review = call_openai_reviewer(candidate_md, model=model)
            review = validate_review(review, expected_document_id=int(entry["document_id"]))
            review.update(
                {
                    "model": model,
                    "reviewer_version": REVIEWER_VERSION,
                    "reviewed_at": utc_now(),
                    "candidate_path": entry["candidate_path"],
                }
            )
            json_dump(review_json_path, review)
            if error_json_path.exists():
                error_json_path.unlink()
            review_md_path.write_text(render_review_markdown(review, entry), encoding="utf-8")
            log(f"[{index}/{total_candidates}] done doc {entry['document_id']}: {review['decision']}")
            result = {"kind": "reviewed", "document_id": entry["document_id"], "decision": review["decision"]}
        except Exception as exc:
            error = {
                "document_id": entry["document_id"],
                "model": model,
                "reviewer_version": REVIEWER_VERSION,
                "candidate_path": entry["candidate_path"],
                "failed_at": utc_now(),
                "error_type": type(exc).__name__,
                "error": str(exc),
            }
            json_dump(error_json_path, error)
            log(f"[{index}/{total_candidates}] error doc {entry['document_id']}: {type(exc).__name__}: {exc}")
            if stop_on_error:
                raise
            result = {"kind": "error", **error}
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        return result

    if total_candidates:
        if workers == 1:
            results = [review_one(index, entry) for index, entry in enumerate(selected_candidates, start=1)]
        else:
            progress(f"Running {total_candidates} reviews with {workers} workers")
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = [
                    executor.submit(review_one, index, entry)
                    for index, entry in enumerate(selected_candidates, start=1)
                ]
                results = [future.result() for future in as_completed(futures)]
        for result in results:
            kind = result.get("kind")
            if kind == "reviewed":
                reviewed.append({"document_id": result["document_id"], "decision": result["decision"]})
            elif kind == "skipped":
                skipped.append({"document_id": result["document_id"], "reason": result["reason"]})
            elif kind == "error":
                errors.append(result)
    return {
        "batch_dir": str(batch_dir),
        "reviewed_count": len(reviewed),
        "skipped_count": len(skipped),
        "error_count": len(errors),
        "workers": workers,
        "reviewed": reviewed,
        "skipped": skipped,
        "errors": errors,
    }


def call_openai_reviewer(candidate_markdown: str, *, model: str) -> dict[str, Any]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for real AI review. Use --mock for local smoke tests.")
    from openai import OpenAI

    kwargs: dict[str, Any] = {"api_key": api_key}
    if os.environ.get("OPENAI_BASE_URL"):
        kwargs["base_url"] = os.environ["OPENAI_BASE_URL"]
    client = OpenAI(**kwargs)
    response = client.responses.create(
        model=model,
        instructions=REVIEWER_INSTRUCTIONS,
        input=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": "请审查下面这条鼻敏智诊候选证据，并只输出 JSON。\n\n" + candidate_markdown,
                    }
                ],
            }
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "rhinitis_evidence_review",
                "schema": REVIEW_SCHEMA,
                "strict": True,
            }
        },
        max_output_tokens=1800,
    )
    text = getattr(response, "output_text", "") or ""
    if not text:
        text = extract_response_text(response)
    return parse_json_response(text)


def extract_response_text(response: Any) -> str:
    chunks: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            text = getattr(content, "text", "")
            if text:
                chunks.append(text)
    return "\n".join(chunks).strip()


def parse_json_response(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return json.loads(cleaned)


def mock_review(candidate_markdown: str, document_id: int, *, model: str) -> dict[str, Any]:
    text = candidate_markdown.lower()
    if any(term in text for term in ["mouse model", "murine", "cell line"]):
        decision = "reject"
        confidence = 0.82
        reason = "资料以基础实验或动物/细胞研究为主，不适合第一版鼻敏智诊精选证据库。"
        use_for = ["research_only"]
        risk_flags = ["basic_science_only"]
        human_check_needed = False
    elif any(term in text for term in ["guideline", "consensus", "intranasal", "allergic rhinitis", "过敏性鼻炎"]):
        decision = "ai_recommend_curate"
        confidence = 0.86
        reason = "资料与过敏性鼻炎诊疗直接相关，证据类型较高，适合先进入医生端演示用精选库。"
        use_for = ["doctor_summary"]
        risk_flags = []
        human_check_needed = False
    else:
        decision = "needs_human_spot_check"
        confidence = 0.64
        reason = "资料可能与鼻炎相关，但临床用途或证据边界不够清晰，建议人工抽查后再晋级。"
        use_for = ["research_only"]
        risk_flags = ["unclear_clinical_use"]
        human_check_needed = True
    level = "guideline" if "guideline" in text else "review"
    return {
        "document_id": document_id,
        "decision": decision,
        "confidence": confidence,
        "evidence_level": level,
        "use_for": use_for,
        "patient_visible": False,
        "doctor_visible": decision == "ai_recommend_curate",
        "topics": ["过敏性鼻炎"],
        "risk_flags": risk_flags,
        "reason": reason,
        "human_check_needed": human_check_needed,
        "summary_for_curated": "AI 预审认为该资料可用于鼻敏智诊医生端证据演示。" if decision == "ai_recommend_curate" else "",
        "citation_note": "mock review for local validation",
        "model": model,
    }


def validate_review(review: dict[str, Any], *, expected_document_id: int) -> dict[str, Any]:
    if int(review.get("document_id") or 0) != int(expected_document_id):
        raise ValueError(f"review document_id mismatch: expected {expected_document_id}, got {review.get('document_id')}")
    decision = str(review.get("decision") or "")
    if decision not in REVIEW_DECISIONS:
        raise ValueError(f"invalid decision: {decision}")
    confidence = float(review.get("confidence") or 0)
    if confidence < 0 or confidence > 1:
        raise ValueError(f"invalid confidence: {confidence}")
    level = str(review.get("evidence_level") or "paper")
    if level not in EVIDENCE_LEVELS:
        review["evidence_level"] = "paper"
    use_for = [str(item) for item in review.get("use_for") or [] if str(item) in USE_FOR_VALUES]
    if not use_for:
        use_for = ["research_only"]
    review["use_for"] = sorted(set(use_for))
    review["confidence"] = round(confidence, 3)
    review["patient_visible"] = bool(review.get("patient_visible"))
    review["doctor_visible"] = bool(review.get("doctor_visible"))
    review["human_check_needed"] = bool(review.get("human_check_needed"))
    review["topics"] = [str(item).strip() for item in review.get("topics") or [] if str(item).strip()][:12] or ["过敏性鼻炎"]
    review["risk_flags"] = [str(item).strip() for item in review.get("risk_flags") or [] if str(item).strip()][:12]
    review["reason"] = str(review.get("reason") or "").strip()
    review["summary_for_curated"] = str(review.get("summary_for_curated") or "").strip()
    review["citation_note"] = str(review.get("citation_note") or "").strip()
    return review


def render_review_markdown(review: dict[str, Any], entry: dict[str, Any]) -> str:
    return "\n".join(
        [
            f"# AI Evidence Review {review['document_id']}",
            "",
            f"- Title: {entry.get('title') or ''}",
            f"- Decision: {review['decision']}",
            f"- Confidence: {review['confidence']}",
            f"- Evidence level: {review['evidence_level']}",
            f"- Use for: {', '.join(review['use_for'])}",
            f"- Doctor visible recommendation: {review['doctor_visible']}",
            f"- Patient visible recommendation: {review['patient_visible']}",
            f"- Human check needed: {review['human_check_needed']}",
            f"- Topics: {', '.join(review['topics'])}",
            f"- Risk flags: {', '.join(review['risk_flags']) if review['risk_flags'] else 'none'}",
            "",
            "## Reason",
            review["reason"],
            "",
            "## Summary For Curated",
            review["summary_for_curated"] or "N/A",
            "",
            "## Citation Note",
            review["citation_note"] or "N/A",
            "",
        ]
    )


def load_reviews(batch_dir: Path) -> list[dict[str, Any]]:
    manifest = load_manifest(batch_dir)
    reviews: list[dict[str, Any]] = []
    for entry in manifest.get("candidates") or []:
        path = batch_dir / entry["review_json_path"]
        if not path.exists():
            continue
        review = json_load(path)
        review["_entry"] = entry
        reviews.append(review)
    return reviews


def apply_batch(
    *,
    batch: str | Path,
    confidence_threshold: float = 0.75,
    promote_doctor_only: bool = False,
    mark_rejected: bool = False,
    write_notes: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    from app.rhinitis_evidence import get_evidence_document, init_rhinitis_evidence_db, review_evidence_document

    init_rhinitis_evidence_db()
    batch_dir = resolve_batch(batch)
    reviews = load_reviews(batch_dir)
    actions: list[dict[str, Any]] = []
    write_enabled = not dry_run and (promote_doctor_only or mark_rejected or write_notes)
    for review in reviews:
        document_id = int(review["document_id"])
        confidence = float(review.get("confidence") or 0)
        decision = str(review.get("decision") or "")
        current_doc = get_evidence_document(document_id, scope="raw")
        if not current_doc:
            actions.append({"document_id": document_id, "action": "missing"})
            continue
        action = "no_write"
        target_status = current_doc.get("review_status") or "needs_review"
        patient_visible: bool | None = None
        doctor_visible: bool | None = None
        if decision == "ai_recommend_curate" and confidence >= confidence_threshold and promote_doctor_only:
            action = "promote_doctor_only"
            target_status = "approved"
            patient_visible = False
            doctor_visible = True
        elif decision == "reject" and confidence >= confidence_threshold and mark_rejected:
            action = "mark_rejected"
            target_status = "rejected"
            patient_visible = False
            doctor_visible = False
        elif write_notes:
            action = "write_note_only"
        note = build_review_note(review, action=action)
        if write_enabled and action != "no_write":
            review_evidence_document(
                document_scope="raw",
                document_id=document_id,
                status=target_status,
                note=note,
                reviewer=reviewer_name(review),
                patient_visible=patient_visible,
                doctor_visible=doctor_visible,
            )
        actions.append(
            {
                "document_id": document_id,
                "decision": decision,
                "confidence": confidence,
                "action": action,
                "would_write": bool(write_enabled and action != "no_write"),
                "title": current_doc.get("title") or "",
            }
        )
    summary = {
        "batch_dir": str(batch_dir),
        "dry_run": dry_run,
        "confidence_threshold": confidence_threshold,
        "total_reviews": len(reviews),
        "actions": actions,
        "counts": {},
    }
    counts: dict[str, int] = {}
    for action in actions:
        key = str(action["action"])
        counts[key] = counts.get(key, 0) + 1
    summary["counts"] = counts
    return summary


def reviewer_name(review: dict[str, Any]) -> str:
    model = str(review.get("model") or DEFAULT_MODEL)
    return f"ai:{model}:{REVIEWER_VERSION}"[:120]


def build_review_note(review: dict[str, Any], *, action: str) -> str:
    parts = [
        f"AI evidence pre-review {REVIEWER_VERSION}",
        f"decision={review.get('decision')}",
        f"confidence={review.get('confidence')}",
        f"action={action}",
        f"use_for={','.join(review.get('use_for') or [])}",
        f"risk_flags={','.join(review.get('risk_flags') or []) or 'none'}",
        f"human_check_needed={bool(review.get('human_check_needed'))}",
        f"reason={review.get('reason') or ''}",
    ]
    summary = str(review.get("summary_for_curated") or "").strip()
    if summary:
        parts.append(f"summary_for_curated={summary}")
    return "\n".join(parts)[:1200]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export and AI-review Rhinitis evidence candidates.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser("export", help="Export raw candidates into Markdown evidence packages.")
    export.add_argument("--limit", type=int, default=20)
    export.add_argument("--status", default="needs_review")
    export.add_argument("--source-bucket", default="")
    export.add_argument("--evidence-level", default="")
    export.add_argument("--topic-tag", default="")
    export.add_argument("--output-dir", type=Path, default=None)
    export.add_argument("--max-chars-per-doc", type=int, default=12000)

    review = subparsers.add_parser("review", help="Review a Markdown batch with GPT-5.5 or a local mock.")
    review.add_argument("--batch", default="latest")
    review.add_argument("--model", default=DEFAULT_MODEL)
    review.add_argument("--mock", action="store_true", help="Use deterministic local mock output for smoke tests.")
    review.add_argument("--overwrite", action="store_true")
    review.add_argument("--max-docs", type=int, default=None)
    review.add_argument("--workers", type=int, default=1)
    review.add_argument("--sleep-seconds", type=float, default=0)
    review.add_argument("--stop-on-error", action="store_true")

    apply = subparsers.add_parser("apply", help="Dry-run or apply AI review results to the database.")
    apply.add_argument("--batch", default="latest")
    apply.add_argument("--confidence-threshold", type=float, default=0.75)
    apply.add_argument("--promote-doctor-only", action="store_true")
    apply.add_argument("--mark-rejected", action="store_true")
    apply.add_argument("--write-notes", action="store_true")
    apply.add_argument("--write", action="store_true", help="Actually write requested actions; default is dry-run.")

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "export":
        result = export_batch(
            limit=args.limit,
            status=args.status,
            source_bucket=args.source_bucket,
            evidence_level=args.evidence_level,
            topic_tag=args.topic_tag,
            output_dir=args.output_dir,
            max_chars_per_doc=args.max_chars_per_doc,
        )
    elif args.command == "review":
        result = review_batch(
            batch=args.batch,
            model=args.model,
            mock=args.mock,
            overwrite=args.overwrite,
            max_docs=args.max_docs,
            workers=args.workers,
            sleep_seconds=args.sleep_seconds,
            stop_on_error=args.stop_on_error,
        )
    elif args.command == "apply":
        result = apply_batch(
            batch=args.batch,
            confidence_threshold=args.confidence_threshold,
            promote_doctor_only=args.promote_doctor_only,
            mark_rejected=args.mark_rejected,
            write_notes=args.write_notes,
            dry_run=not args.write,
        )
    else:
        parser.error("unknown command")
        return
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
