from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
from html.parser import HTMLParser
import json
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

import yaml


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


USER_AGENT = "MedFlowRhinitisEvidence/0.1"
PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
SEED_SOURCE_PATH = ROOT / "knowledge" / "rhinitis_seed_sources.yaml"


PUBMED_QUERY_SPECS = {
    "pubmed_allergic_rhinitis_all": {
        "bucket": "literature_candidates",
        "term": '("Rhinitis, Allergic"[Mesh] OR "allergic rhinitis"[tiab] OR "hay fever"[tiab] '
        'OR "seasonal allergic rhinitis"[tiab] OR "perennial allergic rhinitis"[tiab])',
    },
    "pubmed_guideline_consensus": {
        "bucket": "guideline_candidates",
        "term": '("Rhinitis, Allergic"[Mesh] OR "allergic rhinitis"[tiab]) '
        "AND (guideline[pt] OR practice guideline[pt] OR consensus[tiab] OR guideline[tiab] OR consensus[Title])",
    },
    "pubmed_systematic_meta": {
        "bucket": "literature_candidates",
        "term": '("Rhinitis, Allergic"[Mesh] OR "allergic rhinitis"[tiab]) '
        "AND (systematic review[pt] OR meta-analysis[pt] OR systematic[tiab] OR meta-analysis[tiab])",
    },
    "pubmed_rct": {
        "bucket": "literature_candidates",
        "term": '("Rhinitis, Allergic"[Mesh] OR "allergic rhinitis"[tiab]) '
        "AND (randomized controlled trial[pt] OR randomised[tiab] OR randomized[tiab])",
    },
    "pubmed_immunotherapy_ar": {
        "bucket": "literature_candidates",
        "term": '("Rhinitis, Allergic"[Mesh] OR "allergic rhinitis"[tiab]) '
        'AND ("Allergen Immunotherapy"[Mesh] OR immunotherapy[tiab] OR sublingual[tiab] OR subcutaneous[tiab])',
    },
    "pubmed_nasal_endoscopy_ar": {
        "bucket": "literature_candidates",
        "term": '("allergic rhinitis"[tiab] OR "Rhinitis, Allergic"[Mesh]) '
        'AND ("nasal endoscopy"[tiab] OR endoscopic[tiab] OR "inferior turbinate"[tiab])',
    },
    "pubmed_pediatric_ar": {
        "bucket": "literature_candidates",
        "term": '("Rhinitis, Allergic"[Mesh] OR "allergic rhinitis"[tiab]) '
        'AND (child[Mesh] OR adolescent[Mesh] OR children[tiab] OR pediatric[tiab] OR paediatric[tiab])',
    },
    "pubmed_intranasal_steroid_ar": {
        "bucket": "literature_candidates",
        "term": '("Rhinitis, Allergic"[Mesh] OR "allergic rhinitis"[tiab]) '
        'AND ("intranasal corticosteroid"[tiab] OR fluticasone[tiab] OR mometasone[tiab] OR budesonide[tiab])',
    },
    "pubmed_antihistamine_ar": {
        "bucket": "literature_candidates",
        "term": '("Rhinitis, Allergic"[Mesh] OR "allergic rhinitis"[tiab]) '
        "AND (antihistamine[tiab] OR cetirizine[tiab] OR loratadine[tiab] OR fexofenadine[tiab] OR azelastine[tiab])",
    },
    "pubmed_asthma_comorbidity_ar": {
        "bucket": "literature_candidates",
        "term": '("Rhinitis, Allergic"[Mesh] OR "allergic rhinitis"[tiab]) AND (asthma[Mesh] OR asthma[tiab])',
    },
    "pubmed_pollen_environment_ar": {
        "bucket": "environment_candidates",
        "term": '("Rhinitis, Allergic"[Mesh] OR "allergic rhinitis"[tiab] OR "hay fever"[tiab]) '
        "AND (pollen[tiab] OR aeroallergen[tiab] OR seasonality[tiab] OR air pollution[tiab])",
    },
    "pmc_allergic_rhinitis": {
        "bucket": "literature_candidates",
        "term": '("allergic rhinitis" OR "hay fever" OR "seasonal allergic rhinitis" OR "perennial allergic rhinitis")',
    },
}

PUBMED_QUERIES = [
    (name, str(spec["bucket"]), str(spec["term"]))
    for name, spec in PUBMED_QUERY_SPECS.items()
]

PUBMED_IMPORT_QUERIES = {
    name: str(spec["term"])
    for name, spec in PUBMED_QUERY_SPECS.items()
    if name.startswith("pubmed_")
}

PUBMED_SCREENING_PROFILES = {
    "pubmed_allergic_rhinitis_all": {
        "allowed_levels": {"guideline", "consensus", "systematic_review", "meta_analysis", "rct", "review"},
        "required_tags": set(),
        "require_abstract": True,
        "default_limit": 300,
    },
    "pubmed_guideline_consensus": {
        "allowed_levels": {"guideline", "consensus"},
        "required_tags": set(),
        "require_abstract": False,
        "default_limit": 300,
    },
    "pubmed_systematic_meta": {
        "allowed_levels": {"systematic_review", "meta_analysis", "review"},
        "required_tags": {"系统综述", "Meta"},
        "require_abstract": True,
        "default_limit": 500,
    },
    "pubmed_rct": {
        "allowed_levels": {"rct"},
        "required_tags": set(),
        "require_abstract": True,
        "default_limit": 500,
    },
    "pubmed_immunotherapy_ar": {
        "allowed_levels": {"guideline", "consensus", "systematic_review", "meta_analysis", "rct", "review", "observational", "paper"},
        "required_tags": {"免疫治疗"},
        "require_abstract": True,
        "default_limit": 300,
    },
    "pubmed_nasal_endoscopy_ar": {
        "allowed_levels": {"guideline", "consensus", "systematic_review", "meta_analysis", "rct", "review", "observational", "paper"},
        "required_tags": {"鼻内镜"},
        "require_abstract": False,
        "default_limit": 250,
    },
    "pubmed_pediatric_ar": {
        "allowed_levels": {"guideline", "consensus", "systematic_review", "meta_analysis", "rct", "review", "observational"},
        "required_tags": {"儿童"},
        "require_abstract": True,
        "default_limit": 300,
    },
    "pubmed_intranasal_steroid_ar": {
        "allowed_levels": {"guideline", "consensus", "systematic_review", "meta_analysis", "rct", "review", "observational", "paper"},
        "required_tags": {"鼻喷激素"},
        "require_abstract": True,
        "default_limit": 300,
    },
    "pubmed_antihistamine_ar": {
        "allowed_levels": {"guideline", "consensus", "systematic_review", "meta_analysis", "rct", "review", "observational", "paper"},
        "required_tags": {"抗组胺"},
        "require_abstract": True,
        "default_limit": 250,
    },
    "pubmed_asthma_comorbidity_ar": {
        "allowed_levels": {"guideline", "consensus", "systematic_review", "meta_analysis", "rct", "review", "observational"},
        "required_tags": {"合并哮喘"},
        "require_abstract": True,
        "default_limit": 250,
    },
    "pubmed_pollen_environment_ar": {
        "allowed_levels": {"guideline", "consensus", "systematic_review", "meta_analysis", "rct", "review", "observational", "paper"},
        "required_tags": {"花粉"},
        "require_abstract": True,
        "default_limit": 250,
    },
}

PUBMED_IMPORT_PLANS = {
    "priority": [
        "pubmed_guideline_consensus",
        "pubmed_systematic_meta",
        "pubmed_rct",
        "pubmed_immunotherapy_ar",
        "pubmed_intranasal_steroid_ar",
        "pubmed_antihistamine_ar",
        "pubmed_nasal_endoscopy_ar",
        "pubmed_pediatric_ar",
        "pubmed_asthma_comorbidity_ar",
        "pubmed_pollen_environment_ar",
    ],
}

EUROPE_PMC_QUERIES = [
    (
        "europepmc_allergic_rhinitis",
        "literature_candidates",
        'TITLE_ABS:"allergic rhinitis" OR TITLE_ABS:"hay fever" OR TITLE_ABS:"seasonal allergic rhinitis"',
    ),
    (
        "europepmc_open_access_fulltext",
        "literature_candidates",
        '(TITLE_ABS:"allergic rhinitis" OR TITLE_ABS:"hay fever") AND OPEN_ACCESS:y',
    ),
    (
        "europepmc_guideline_consensus",
        "guideline_candidates",
        '(TITLE_ABS:"allergic rhinitis") AND (TITLE_ABS:guideline OR TITLE_ABS:consensus)',
    ),
]

CLINICAL_TRIALS_QUERIES = [
    ("clinicaltrials_allergic_rhinitis", "trial_candidates", {"query.cond": "allergic rhinitis"}),
    ("clinicaltrials_seasonal_allergic_rhinitis", "trial_candidates", {"query.cond": "seasonal allergic rhinitis"}),
    ("clinicaltrials_immunotherapy_ar", "trial_candidates", {"query.cond": "allergic rhinitis", "query.intr": "immunotherapy"}),
]

OPENALEX_QUERIES = [
    ("openalex_allergic_rhinitis_works", "literature_candidates", "allergic rhinitis"),
    ("openalex_seasonal_ar_works", "literature_candidates", "seasonal allergic rhinitis"),
    ("openalex_immunotherapy_ar_works", "literature_candidates", "allergic rhinitis immunotherapy"),
]

DRUG_TERMS = [
    "fluticasone",
    "mometasone",
    "budesonide",
    "azelastine",
    "cetirizine",
    "loratadine",
    "montelukast",
    "levocetirizine",
    "desloratadine",
    "fexofenadine",
]


def _get_json(url: str) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=25) as response:
        return json.load(response)


def _get_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


class _HTMLSummaryParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title_parts: list[str] = []
        self.description = ""
        self.text_parts: list[str] = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        if normalized == "title":
            self._in_title = True
        if normalized == "meta":
            values = {str(key).lower(): str(value or "") for key, value in attrs}
            name = values.get("name", "").lower()
            prop = values.get("property", "").lower()
            if not self.description and (name == "description" or prop == "og:description"):
                self.description = _clean_text(values.get("content", ""))

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in {"script", "style", "noscript", "svg"} and self._skip_depth:
            self._skip_depth -= 1
        if normalized == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        cleaned = _clean_text(data)
        if not cleaned:
            return
        if self._in_title:
            self.title_parts.append(cleaned)
            return
        if self._skip_depth:
            return
        if len(cleaned) >= 2:
            self.text_parts.append(cleaned)


def _fetch_public_page_metadata(url: str) -> dict:
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        raw = response.read(1_500_000)
        status = getattr(response, "status", 200)
        final_url = response.geturl()
        headers = response.headers
        content_type = headers.get("Content-Type", "")
        charset = headers.get_content_charset() or "utf-8"
    text = raw.decode(charset, errors="replace")
    parser = _HTMLSummaryParser()
    parser.feed(text)
    title = _clean_text(" ".join(parser.title_parts))
    body_text = _clean_text(" ".join(parser.text_parts))
    return {
        "http_status": status,
        "final_url": final_url,
        "content_type": content_type,
        "charset": charset,
        "fetched_title": title,
        "description": parser.description,
        "extracted_text_sample": _trim(body_text, 3600),
        "retrieved_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }


def _record_success(source_name: str, source_bucket: str, query: str, count: int, metadata: dict | None = None) -> None:
    from app.rhinitis_evidence import record_import_run

    record_import_run(
        source_name=source_name,
        source_bucket=source_bucket,
        query=query,
        status="counted",
        fetched_count=count,
        imported_count=0,
        metadata=metadata or {},
    )
    print(f"{source_name}: {count}")


def _record_failure(source_name: str, source_bucket: str, query: str, error: Exception) -> None:
    from app.rhinitis_evidence import record_import_run

    record_import_run(
        source_name=source_name,
        source_bucket=source_bucket,
        query=query,
        status="failed",
        error=str(error),
    )
    print(f"{source_name}: failed: {error}", file=sys.stderr)


def import_seed_source_pages(*, limit: int = 0) -> dict:
    from app.rhinitis_evidence import record_import_run, upsert_raw_document

    payload = yaml.safe_load(SEED_SOURCE_PATH.read_text(encoding="utf-8")) or {}
    documents = list(payload.get("documents") or [])
    if limit > 0:
        documents = documents[:limit]

    imported = 0
    updated = 0
    skipped = 0
    failed = 0
    failures: list[dict[str, str]] = []
    started_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    for document in documents:
        source_key = str(document.get("source_key") or "").strip()
        url = str(document.get("url") or "").strip()
        if not source_key or not url:
            skipped += 1
            continue
        try:
            metadata = _fetch_public_page_metadata(url)
            candidate = _seed_fetch_document(document, metadata)
            _, created = upsert_raw_document(candidate)
            imported += 1 if created else 0
            updated += 0 if created else 1
            print(
                f"seed_source_fetch: {'new' if created else 'updated'} {candidate['source_key']} "
                f"status={metadata.get('http_status')} title={candidate['title'][:70]}"
            )
        except Exception as exc:
            failed += 1
            failures.append({"source_key": source_key, "url": url, "error": str(exc)[:500]})
            print(f"seed_source_fetch: failed {source_key}: {exc}", file=sys.stderr)
        time.sleep(0.35)

    run = record_import_run(
        source_name="seed_source_fetch",
        source_bucket="mixed_candidates",
        query=str(SEED_SOURCE_PATH.relative_to(ROOT)),
        status="imported_with_errors" if failed else "imported",
        fetched_count=len(documents),
        imported_count=imported,
        metadata={
            "updated_count": updated,
            "skipped_count": skipped,
            "failed_count": failed,
            "failures": failures[:20],
        },
        started_at=started_at,
    )
    print(
        f"seed_source_fetch: fetched={len(documents)} new={imported} "
        f"updated={updated} skipped={skipped} failed={failed}"
    )
    return run


def _seed_fetch_document(document: dict, metadata: dict) -> dict:
    blocked = _looks_like_challenge_page(metadata)
    if blocked:
        metadata = dict(metadata)
        metadata["warning"] = "challenge_or_non_content_page"
    fetched_text = "" if blocked else metadata.get("extracted_text_sample") or ""
    fetched_text = fetched_text or document.get("content_summary") or ""
    title = "" if blocked else metadata.get("fetched_title") or ""
    title = title or document.get("title") or "Seed source webpage"
    source_key = str(document.get("source_key") or "").strip()
    topic_tags = list(document.get("topic_tags") or [])
    chunks = []
    if fetched_text:
        chunks.append(
            {
                "heading": "公开网页抓取摘要",
                "scenario": "research",
                "content": _trim(fetched_text, 2600),
                "topic_tags": topic_tags,
                "patient_visible": False,
                "doctor_visible": bool(document.get("doctor_visible", True)),
                "research_visible": True,
            }
        )
    for chunk in document.get("chunks") or []:
        content = str(chunk.get("content") or "").strip()
        if not content:
            continue
        copied = dict(chunk)
        copied["scenario"] = copied.get("scenario") or "research"
        copied["patient_visible"] = False
        copied["research_visible"] = True
        chunks.append(copied)
    return {
        "source_key": f"seedfetch:{source_key}",
        "source_bucket": document.get("source_bucket") or "hospital_education_candidates",
        "source_type": document.get("source_type") or "webpage",
        "title": title,
        "url": metadata.get("final_url") or document.get("url") or "",
        "pmid": document.get("pmid") or "",
        "pmcid": document.get("pmcid") or "",
        "doi": document.get("doi") or "",
        "year": document.get("year"),
        "journal_or_org": document.get("journal_or_org") or "",
        "language": document.get("language") or "zh",
        "evidence_level": document.get("evidence_level") or "webpage",
        "review_status": "needs_review",
        "license_status": document.get("license_status") or "public_webpage",
        "open_access": bool(document.get("open_access", True)),
        "patient_visible": False,
        "doctor_visible": bool(document.get("doctor_visible", True)),
        "research_visible": True,
        "topic_tags": _dedupe([*topic_tags, "seed_source_fetch"]),
        "content_summary": _trim(metadata.get("description") or fetched_text or document.get("content_summary") or title, 900),
        "raw_payload": {
            "seed_source_key": source_key,
            "seed_title": document.get("title") or "",
            "seed_review_status": document.get("review_status") or "",
            "fetch": metadata,
            "extractor": "seed_source_fetch_v1",
        },
        "chunks": chunks,
    }


def _looks_like_challenge_page(metadata: dict) -> bool:
    title = str(metadata.get("fetched_title") or "").lower()
    sample = str(metadata.get("extracted_text_sample") or "").lower()
    return any(
        signal in title or signal in sample[:500]
        for signal in [
            "checking your browser",
            "recaptcha",
            "captcha",
            "access denied",
            "verify you are human",
            "请完成安全验证",
        ]
    )


def fetch_pubmed_counts() -> None:
    for name, bucket, term in PUBMED_QUERIES:
        db = "pmc" if name.startswith("pmc_") else "pubmed"
        url = PUBMED_ESEARCH_URL + "?" + urlencode({"db": db, "term": term, "retmode": "json"})
        try:
            data = _get_json(url)
            count = int(data["esearchresult"].get("count") or 0)
            _record_success(name, bucket, term, count, {"db": db})
        except Exception as exc:
            _record_failure(name, bucket, term, exc)
        time.sleep(0.35)


def import_pubmed_candidates(
    query_name: str,
    *,
    max_results: int,
    batch_size: int,
    retstart: int,
    screened: bool = True,
) -> dict:
    from app.rhinitis_evidence import record_import_run, upsert_raw_document

    query = PUBMED_IMPORT_QUERIES[query_name]
    source_bucket = str(PUBMED_QUERY_SPECS.get(query_name, {}).get("bucket") or "literature_candidates")
    effective_limit = _pubmed_profile_limit(query_name, max_results)
    started_at = None
    imported = 0
    updated = 0
    fetched = 0
    eligible = 0
    skipped_reasons: Counter[str] = Counter()
    try:
        params = {
            "db": "pubmed",
            "term": query,
            "retmode": "json",
            "retmax": effective_limit,
            "retstart": max(0, retstart),
            "sort": "relevance",
        }
        search_payload = _get_json(PUBMED_ESEARCH_URL + "?" + urlencode(params))
        ids = search_payload.get("esearchresult", {}).get("idlist") or []
        fetched = len(ids)
        for id_batch in _chunks(ids, max(1, min(batch_size, 200))):
            xml_text = _get_text(
                PUBMED_EFETCH_URL
                + "?"
                + urlencode({"db": "pubmed", "id": ",".join(id_batch), "retmode": "xml"})
            )
            for document in _parse_pubmed_xml(xml_text):
                accepted, reason = _screen_pubmed_document(document, query_name) if screened else (True, "screening_disabled")
                if not accepted:
                    skipped_reasons[reason] += 1
                    continue
                eligible += 1
                if source_bucket != "literature_candidates":
                    document["source_bucket"] = source_bucket
                document.setdefault("raw_payload", {})["screening"] = {
                    "profile": query_name,
                    "screened": screened,
                    "decision": "imported",
                }
                _, created = upsert_raw_document(document)
                if created:
                    imported += 1
                else:
                    updated += 1
            time.sleep(0.35)
        metadata = {
            "retstart": retstart,
            "max_results": effective_limit,
            "requested_max_results": max_results,
            "batch_size": batch_size,
            "screened": screened,
            "eligible_count": eligible,
            "updated_count": updated,
            "skipped_count": sum(skipped_reasons.values()),
            "skip_reasons": dict(skipped_reasons),
            "query_hit_count": int(search_payload.get("esearchresult", {}).get("count") or 0),
        }
        run = record_import_run(
            source_name=f"pubmed_import_{query_name}",
            source_bucket=source_bucket,
            query=query,
            status="imported_screened" if screened else "imported",
            fetched_count=fetched,
            imported_count=imported,
            metadata=metadata,
            started_at=started_at,
        )
        print(
            f"pubmed_import_{query_name}: fetched={fetched} eligible={eligible} "
            f"new={imported} updated={updated} skipped={sum(skipped_reasons.values())}"
        )
        return run
    except Exception as exc:
        record_import_run(
            source_name=f"pubmed_import_{query_name}",
            source_bucket=source_bucket,
            query=query,
            status="failed",
            fetched_count=fetched,
            imported_count=imported,
            error=str(exc),
            metadata={
                "retstart": retstart,
                "max_results": effective_limit,
                "requested_max_results": max_results,
                "batch_size": batch_size,
                "screened": screened,
                "eligible_count": eligible,
                "updated_count": updated,
                "skipped_count": sum(skipped_reasons.values()),
                "skip_reasons": dict(skipped_reasons),
            },
            started_at=started_at,
        )
        raise


def import_pubmed_plan(plan_name: str, *, max_results: int, batch_size: int, retstart: int, screened: bool = True) -> None:
    if plan_name not in PUBMED_IMPORT_PLANS:
        raise ValueError(f"unknown PubMed plan: {plan_name}")
    for query_name in PUBMED_IMPORT_PLANS[plan_name]:
        import_pubmed_candidates(
            query_name,
            max_results=max_results,
            batch_size=batch_size,
            retstart=retstart,
            screened=screened,
        )
        time.sleep(0.35)


def _parse_pubmed_xml(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    documents = []
    for article in root.findall(".//PubmedArticle"):
        pmid = _node_text(article.find(".//MedlineCitation/PMID"))
        if not pmid:
            continue
        title = _clean_text(_iter_text(article.find(".//Article/ArticleTitle")))
        abstract = _abstract_text(article)
        journal = _journal_title(article)
        year = _publication_year(article)
        publication_types = _publication_types(article)
        mesh_terms = _mesh_terms(article)
        article_ids = _article_ids(article)
        doi = article_ids.get("doi", "")
        pmcid = article_ids.get("pmc", "")
        language = _node_text(article.find(".//Article/Language"))
        evidence_level = _pubmed_evidence_level(publication_types, title, abstract)
        review_status = _pubmed_review_status(evidence_level, title, abstract)
        topic_tags = _pubmed_topic_tags(title, abstract, mesh_terms, publication_types, evidence_level)
        source_bucket = "guideline_candidates" if evidence_level in {"guideline", "consensus"} else "literature_candidates"
        source_type = _source_type_for_evidence(evidence_level)
        summary = abstract or title
        documents.append(
            {
                "source_key": f"pubmed:{pmid}",
                "source_bucket": source_bucket,
                "source_type": source_type,
                "title": title or f"PubMed PMID {pmid}",
                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                "pmid": pmid,
                "pmcid": pmcid,
                "doi": doi,
                "year": year,
                "journal_or_org": journal,
                "language": language,
                "evidence_level": evidence_level,
                "review_status": review_status,
                "license_status": "public_metadata",
                "open_access": bool(pmcid),
                "patient_visible": False,
                "doctor_visible": True,
                "research_visible": True,
                "topic_tags": topic_tags,
                "content_summary": _trim(summary, 900),
                "raw_payload": {
                    "publication_types": publication_types,
                    "mesh_terms": mesh_terms,
                    "authors": _authors(article),
                    "article_ids": article_ids,
                    "has_abstract": bool(abstract),
                    "abstract_length": len(abstract),
                },
                "chunks": [
                    {
                        "heading": "PubMed 摘要",
                        "scenario": "research",
                        "content": _trim(summary, 2400),
                        "topic_tags": topic_tags,
                        "patient_visible": False,
                        "doctor_visible": True,
                        "research_visible": True,
                    }
                ],
            }
        )
    return documents


def _pubmed_evidence_level(publication_types: list[str], title: str, abstract: str) -> str:
    publication_text = " ".join(publication_types).lower()
    title_text = (title or "").lower()
    abstract_text = (abstract or "").lower()
    broad_text = " ".join([publication_text, title_text, abstract_text])
    title_or_type = " ".join([publication_text, title_text])

    if "practice guideline" in publication_text or re.search(r"\bguidelines?\b", publication_text):
        return "guideline"
    if _title_has_guideline_signal(title_text):
        return "guideline"
    if "consensus" in publication_text or _title_has_consensus_signal(title_text):
        return "consensus"
    if "meta-analysis" in broad_text or "meta analysis" in broad_text:
        return "meta_analysis"
    if "systematic review" in broad_text:
        return "systematic_review"
    if "randomized controlled trial" in broad_text or "randomised controlled trial" in broad_text:
        return "rct"
    if ("randomized" in broad_text or "randomised" in broad_text) and ("trial" in broad_text or "controlled" in broad_text):
        return "rct"
    if "review" in title_or_type:
        return "review"
    if any(term in broad_text for term in ["cohort", "case-control", "observational", "cross-sectional"]):
        return "observational"
    return "paper"


def _title_has_guideline_signal(title_text: str) -> bool:
    if not title_text:
        return False
    negative_phrases = [
        "based on guideline",
        "based on guidelines",
        "adherence to guideline",
        "adherence to guidelines",
        "according to guideline",
        "according to guidelines",
    ]
    if any(phrase in title_text for phrase in negative_phrases):
        return False
    guideline_patterns = [
        r"\bguidelines?\b",
        r"\bpractice parameter\b",
        r"\bposition paper\b",
        r"\bposition statement\b",
        r"\bclinical practice guideline\b",
        r"\brecommendations?\b",
    ]
    return any(re.search(pattern, title_text) for pattern in guideline_patterns)


def _title_has_consensus_signal(title_text: str) -> bool:
    if not title_text:
        return False
    return bool(re.search(r"\bconsensus\b|\bdelphi\b|\bexpert statement\b", title_text))


def _pubmed_review_status(evidence_level: str, title: str, abstract: str) -> str:
    if evidence_level in {"guideline", "consensus", "meta_analysis", "systematic_review", "rct"}:
        return "needs_review"
    if _has_topic(title, abstract, ["nasal endoscopy", "immunotherapy", "allergen-specific", "ige", "pollen"]):
        return "needs_review"
    return "candidate"


def _source_type_for_evidence(evidence_level: str) -> str:
    return evidence_level if evidence_level in {"guideline", "consensus", "systematic_review", "meta_analysis", "rct"} else "paper"


def _pubmed_topic_tags(title: str, abstract: str, mesh_terms: list[str], publication_types: list[str], evidence_level: str) -> list[str]:
    text = " ".join([title, abstract, " ".join(mesh_terms), " ".join(publication_types)]).lower()
    tags = ["PubMed", evidence_level]
    evidence_tags = {
        "guideline": "指南",
        "consensus": "共识",
        "systematic_review": "系统综述",
        "meta_analysis": "Meta",
        "rct": "RCT",
    }
    if evidence_level in evidence_tags:
        tags.append(evidence_tags[evidence_level])
    rules = [
        ("鼻内镜", ["nasal endoscopy", "endoscopic"]),
        ("免疫治疗", ["immunotherapy", "allergen immunotherapy", "sublingual", "subcutaneous"]),
        ("IgE", ["ige", "immunoglobulin e"]),
        ("过敏原", ["allergen", "allergen-specific"]),
        ("花粉", ["pollen", "aeroallergen"]),
        ("儿童", ["children", "child", "pediatric", "paediatric", "adolescent"]),
        ("孕妇", ["pregnancy", "pregnant"]),
        ("合并哮喘", ["asthma"]),
        ("鼻喷激素", ["intranasal corticosteroid", "fluticasone", "mometasone", "budesonide"]),
        ("抗组胺", ["antihistamine", "cetirizine", "loratadine", "fexofenadine", "azelastine"]),
        ("白三烯", ["montelukast", "leukotriene"]),
    ]
    for tag, needles in rules:
        if any(needle in text for needle in needles):
            tags.append(tag)
    if "rhinitis, allergic" in text or "allergic rhinitis" in text:
        tags.append("过敏性鼻炎")
    return _dedupe(tags)


def _has_topic(title: str, abstract: str, needles: list[str]) -> bool:
    text = f"{title} {abstract}".lower()
    return any(needle in text for needle in needles)


def _abstract_text(article: ET.Element) -> str:
    parts = []
    for node in article.findall(".//Article/Abstract/AbstractText"):
        text = _clean_text(_iter_text(node))
        if not text:
            continue
        label = node.attrib.get("Label") or node.attrib.get("NlmCategory") or ""
        parts.append(f"{label}: {text}" if label else text)
    return " ".join(parts)


def _journal_title(article: ET.Element) -> str:
    return (
        _node_text(article.find(".//Article/Journal/Title"))
        or _node_text(article.find(".//Article/Journal/ISOAbbreviation"))
    )


def _publication_year(article: ET.Element) -> int | None:
    for path in [
        ".//Article/Journal/JournalIssue/PubDate/Year",
        ".//MedlineCitation/DateCompleted/Year",
        ".//MedlineCitation/DateRevised/Year",
    ]:
        value = _node_text(article.find(path))
        if value and value.isdigit():
            return int(value)
    medline = _node_text(article.find(".//Article/Journal/JournalIssue/PubDate/MedlineDate"))
    match = re.search(r"\b(19|20)\d{2}\b", medline or "")
    return int(match.group(0)) if match else None


def _publication_types(article: ET.Element) -> list[str]:
    return _dedupe(_clean_text(_iter_text(node)) for node in article.findall(".//Article/PublicationTypeList/PublicationType"))


def _mesh_terms(article: ET.Element) -> list[str]:
    terms = []
    for node in article.findall(".//MedlineCitation/MeshHeadingList/MeshHeading"):
        descriptor = _node_text(node.find("DescriptorName"))
        if descriptor:
            terms.append(descriptor)
        for qualifier in node.findall("QualifierName"):
            value = _node_text(qualifier)
            if descriptor and value:
                terms.append(f"{descriptor}/{value}")
    return _dedupe(terms)


def _article_ids(article: ET.Element) -> dict[str, str]:
    ids: dict[str, str] = {}
    for node in article.findall(".//PubmedData/ArticleIdList/ArticleId"):
        id_type = node.attrib.get("IdType") or ""
        value = _node_text(node)
        if id_type and value:
            ids[id_type] = value
    return ids


def _authors(article: ET.Element) -> list[str]:
    authors = []
    for node in article.findall(".//Article/AuthorList/Author")[:10]:
        last_name = _node_text(node.find("LastName"))
        fore_name = _node_text(node.find("ForeName"))
        collective = _node_text(node.find("CollectiveName"))
        name = collective or " ".join(part for part in [fore_name, last_name] if part)
        if name:
            authors.append(name)
    return authors


def _node_text(node: ET.Element | None) -> str:
    return _clean_text(_iter_text(node))


def _iter_text(node: ET.Element | None) -> str:
    if node is None:
        return ""
    return "".join(node.itertext())


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _trim(value: str, limit: int) -> str:
    cleaned = _clean_text(value)
    return cleaned[:limit]


def _dedupe(values) -> list[str]:
    result = []
    seen = set()
    for value in values:
        cleaned = str(value or "").strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            result.append(cleaned)
    return result


def _safe_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        match = re.search(r"\b(19|20)\d{2}\b", str(value))
        return int(match.group(0)) if match else None


def _normalize_doi(value: str) -> str:
    doi = str(value or "").strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.IGNORECASE)
    return doi.strip()


def _existing_raw_identity(document: dict) -> bool:
    from app.rhinitis_evidence import rhinitis_evidence_db_path

    clauses = ["source_key = ?"]
    params: list[str] = [str(document.get("source_key") or "")]
    pmid = str(document.get("pmid") or "").strip()
    doi = _normalize_doi(str(document.get("doi") or ""))
    if pmid:
        clauses.append("pmid = ?")
        params.append(pmid)
    if doi:
        clauses.append("lower(doi) = lower(?)")
        params.append(doi)
    conn = sqlite3.connect(rhinitis_evidence_db_path())
    try:
        row = conn.execute(
            f"SELECT id FROM raw_documents WHERE {' OR '.join(clauses)} LIMIT 1",
            params,
        ).fetchone()
    finally:
        conn.close()
    return row is not None


def _chunks(values: list[str], size: int):
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _pubmed_profile_limit(query_name: str, requested_max_results: int) -> int:
    if requested_max_results > 0:
        return max(1, min(requested_max_results, 1000))
    profile = PUBMED_SCREENING_PROFILES.get(query_name) or {}
    return max(1, min(int(profile.get("default_limit") or 200), 1000))


def _screen_pubmed_document(document: dict, query_name: str) -> tuple[bool, str]:
    if not document.get("title"):
        return False, "missing_title"
    if not _pubmed_is_allergic_rhinitis_relevant(document):
        return False, "not_allergic_rhinitis"
    if query_name == "pubmed_guideline_consensus" and not _pubmed_has_title_or_mesh_ar(document):
        return False, "weak_guideline_relevance"
    exclusion = _pubmed_exclusion_reason(document)
    if exclusion:
        return False, exclusion

    profile = PUBMED_SCREENING_PROFILES.get(query_name) or {}
    if profile.get("require_abstract") and not _pubmed_has_abstract(document):
        return False, "missing_abstract"

    evidence_level = str(document.get("evidence_level") or "")
    tags = set(document.get("topic_tags") or [])
    allowed_levels = set(profile.get("allowed_levels") or [])
    required_tags = set(profile.get("required_tags") or [])
    level_match = not allowed_levels or evidence_level in allowed_levels
    tag_match = not required_tags or bool(tags & required_tags)
    if not level_match:
        return False, "evidence_level_not_priority"
    if not tag_match:
        return False, "topic_not_matched"
    if query_name == "pubmed_allergic_rhinitis_all":
        high_value_tags = {"指南", "共识", "系统综述", "Meta", "RCT", "鼻内镜", "免疫治疗", "儿童", "合并哮喘", "鼻喷激素", "抗组胺", "花粉"}
        if evidence_level == "review" and not (tags & high_value_tags):
            return False, "broad_review_without_priority_topic"
    return True, "accepted"


def _pubmed_is_allergic_rhinitis_relevant(document: dict) -> bool:
    text = _pubmed_screen_text(document)
    if "non-allergic rhinitis" in text or "nonallergic rhinitis" in text:
        mesh_terms = {term.lower() for term in document.get("raw_payload", {}).get("mesh_terms") or []}
        if "rhinitis, allergic" not in mesh_terms and "local allergic rhinitis" not in text:
            return False
    relevance_terms = [
        "allergic rhinitis",
        "rhinitis, allergic",
        "hay fever",
        "seasonal allergic rhinitis",
        "perennial allergic rhinitis",
        "local allergic rhinitis",
    ]
    return any(term in text for term in relevance_terms)


def _pubmed_has_title_or_mesh_ar(document: dict) -> bool:
    raw_payload = document.get("raw_payload") or {}
    title = str(document.get("title") or "").lower()
    mesh_text = " ".join(raw_payload.get("mesh_terms") or []).lower()
    strong_terms = [
        "allergic rhinitis",
        "rhinitis, allergic",
        "hay fever",
        "seasonal allergic rhinitis",
        "perennial allergic rhinitis",
        "local allergic rhinitis",
    ]
    return any(term in title or term in mesh_text for term in strong_terms)


def _pubmed_exclusion_reason(document: dict) -> str:
    raw_payload = document.get("raw_payload") or {}
    mesh_terms = {term.lower() for term in raw_payload.get("mesh_terms") or []}
    publication_types = {term.lower() for term in raw_payload.get("publication_types") or []}
    evidence_level = str(document.get("evidence_level") or "")
    if "animals" in mesh_terms and "humans" not in mesh_terms:
        return "animal_only"
    low_value_types = {"letter", "editorial", "comment", "news", "published erratum", "case reports"}
    if publication_types & low_value_types and evidence_level not in {"guideline", "consensus"}:
        return "low_value_publication_type"
    text = _pubmed_screen_text(document)
    basic_science_terms = ["murine", "mouse model", "mice", "rat model", "guinea pig", "cell line"]
    if any(term in text for term in basic_science_terms) and not any(term in text for term in ["patient", "patients", "clinical", "trial"]):
        return "basic_science_only"
    return ""


def _pubmed_has_abstract(document: dict) -> bool:
    raw_payload = document.get("raw_payload") or {}
    return bool(raw_payload.get("has_abstract")) or int(raw_payload.get("abstract_length") or 0) > 0


def _pubmed_screen_text(document: dict) -> str:
    raw_payload = document.get("raw_payload") or {}
    values = [
        document.get("title") or "",
        document.get("content_summary") or "",
        " ".join(document.get("topic_tags") or []),
        " ".join(raw_payload.get("mesh_terms") or []),
        " ".join(raw_payload.get("publication_types") or []),
    ]
    return " ".join(values).lower()


def fetch_europe_pmc_counts() -> None:
    base = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    for name, bucket, query in EUROPE_PMC_QUERIES:
        url = base + "?" + urlencode({"query": query, "format": "json", "pageSize": "1"})
        try:
            data = _get_json(url)
            _record_success(name, bucket, query, int(data.get("hitCount") or 0))
        except Exception as exc:
            _record_failure(name, bucket, query, exc)
        time.sleep(0.35)


def import_europe_pmc_candidates(*, max_results: int, page_size: int) -> None:
    for name, bucket, query in EUROPE_PMC_QUERIES:
        import_europe_pmc_query(name, bucket, query, max_results=max_results, page_size=page_size)
        time.sleep(0.35)


def import_europe_pmc_query(name: str, source_bucket: str, query: str, *, max_results: int, page_size: int) -> dict:
    from app.rhinitis_evidence import record_import_run, upsert_raw_document

    base = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    effective_limit = max(1, min(max_results or 80, 1000))
    effective_page_size = max(1, min(page_size or 50, 100))
    cursor_mark = "*"
    fetched = 0
    imported = 0
    updated = 0
    skipped_reasons: Counter[str] = Counter()
    started_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    try:
        while fetched < effective_limit:
            params = {
                "query": query,
                "format": "json",
                "resultType": "core",
                "pageSize": str(min(effective_page_size, effective_limit - fetched)),
                "cursorMark": cursor_mark,
            }
            payload = _get_json(base + "?" + urlencode(params))
            results = (payload.get("resultList") or {}).get("result") or []
            if not results:
                break
            for item in results:
                fetched += 1
                document = _europe_pmc_document(item, source_bucket=source_bucket, query_name=name)
                if not document.get("title"):
                    skipped_reasons["missing_title"] += 1
                    continue
                if _existing_raw_identity(document):
                    skipped_reasons["duplicate_identity"] += 1
                    continue
                _, created = upsert_raw_document(document)
                if created:
                    imported += 1
                else:
                    updated += 1
                if fetched >= effective_limit:
                    break
            next_cursor = payload.get("nextCursorMark")
            if not next_cursor or next_cursor == cursor_mark:
                break
            cursor_mark = next_cursor
            time.sleep(0.35)
        run = record_import_run(
            source_name=f"europepmc_import_{name}",
            source_bucket=source_bucket,
            query=query,
            status="imported",
            fetched_count=fetched,
            imported_count=imported,
            metadata={
                "updated_count": updated,
                "skipped_count": sum(skipped_reasons.values()),
                "skip_reasons": dict(skipped_reasons),
                "max_results": effective_limit,
                "page_size": effective_page_size,
            },
            started_at=started_at,
        )
        print(
            f"europepmc_import_{name}: fetched={fetched} new={imported} "
            f"updated={updated} skipped={sum(skipped_reasons.values())}"
        )
        return run
    except Exception as exc:
        record_import_run(
            source_name=f"europepmc_import_{name}",
            source_bucket=source_bucket,
            query=query,
            status="failed",
            fetched_count=fetched,
            imported_count=imported,
            error=str(exc),
            metadata={
                "updated_count": updated,
                "skipped_count": sum(skipped_reasons.values()),
                "skip_reasons": dict(skipped_reasons),
                "max_results": effective_limit,
                "page_size": effective_page_size,
            },
            started_at=started_at,
        )
        raise


def _europe_pmc_document(item: dict, *, source_bucket: str, query_name: str) -> dict:
    title = _clean_text(item.get("title") or "")
    abstract = _clean_text(item.get("abstractText") or "")
    pub_types = _europe_pmc_pub_types(item)
    evidence_level = _pubmed_evidence_level(pub_types, title, abstract)
    topic_tags = _pubmed_topic_tags(title, abstract, [], pub_types, evidence_level)
    review_status = _pubmed_review_status(evidence_level, title, abstract)
    if source_bucket == "guideline_candidates" and evidence_level not in {"guideline", "consensus"}:
        review_status = "candidate"
    journal_info = item.get("journalInfo") or {}
    journal = item.get("journalTitle") or (journal_info.get("journal") or {}).get("title") or ""
    pmid = str(item.get("pmid") or "")
    pmcid = str(item.get("pmcid") or "")
    doi = _normalize_doi(item.get("doi") or "")
    source_id = pmid or pmcid or doi or str(item.get("id") or "")
    open_access = str(item.get("isOpenAccess") or "").upper() == "Y" or bool(item.get("fullTextUrlList"))
    url = ""
    if pmcid:
        url = f"https://pmc.ncbi.nlm.nih.gov/articles/{pmcid}/"
    elif pmid:
        url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
    elif doi:
        url = f"https://doi.org/{doi}"
    summary = abstract or title
    return {
        "source_key": f"europepmc:{source_id}",
        "source_bucket": source_bucket,
        "source_type": _source_type_for_evidence(evidence_level),
        "title": title or f"Europe PMC {source_id}",
        "url": url,
        "pmid": pmid,
        "pmcid": pmcid,
        "doi": doi,
        "year": _safe_int(item.get("pubYear")),
        "journal_or_org": journal,
        "language": str(item.get("language") or "en"),
        "evidence_level": evidence_level,
        "review_status": review_status,
        "license_status": "open_access" if open_access else "public_metadata",
        "open_access": open_access,
        "patient_visible": False,
        "doctor_visible": True,
        "research_visible": True,
        "topic_tags": _dedupe([*topic_tags, "Europe PMC", query_name]),
        "content_summary": _trim(summary, 900),
        "raw_payload": {
            "source": "Europe PMC",
            "query_name": query_name,
            "pub_types": pub_types,
            "cited_by_count": _safe_int(item.get("citedByCount")),
            "has_pdf": str(item.get("hasPDF") or "").upper() == "Y",
            "has_full_text": bool(item.get("fullTextUrlList")),
            "raw": item,
        },
        "chunks": [
            {
                "heading": "Europe PMC 摘要",
                "scenario": "research",
                "content": _trim(summary, 2400),
                "topic_tags": _dedupe([*topic_tags, "Europe PMC"]),
                "patient_visible": False,
                "doctor_visible": True,
                "research_visible": True,
            }
        ],
    }


def _europe_pmc_pub_types(item: dict) -> list[str]:
    pub_type_list = item.get("pubTypeList") or {}
    values = pub_type_list.get("pubType") if isinstance(pub_type_list, dict) else pub_type_list
    if isinstance(values, str):
        return [values]
    if isinstance(values, list):
        return _dedupe(values)
    return []


def fetch_clinical_trials_counts() -> None:
    base = "https://clinicaltrials.gov/api/v2/studies"
    for name, bucket, params in CLINICAL_TRIALS_QUERIES:
        url = base + "?" + urlencode({**params, "pageSize": "1", "format": "json", "countTotal": "true"})
        try:
            data = _get_json(url)
            _record_success(name, bucket, json.dumps(params, ensure_ascii=False), int(data.get("totalCount") or 0))
        except Exception as exc:
            _record_failure(name, bucket, json.dumps(params, ensure_ascii=False), exc)
        time.sleep(0.35)


def import_clinical_trials_candidates(*, max_results: int, page_size: int) -> None:
    for name, bucket, params in CLINICAL_TRIALS_QUERIES:
        import_clinical_trials_query(name, bucket, params, max_results=max_results, page_size=page_size)
        time.sleep(0.35)


def import_clinical_trials_query(name: str, source_bucket: str, params: dict, *, max_results: int, page_size: int) -> dict:
    from app.rhinitis_evidence import record_import_run, upsert_raw_document

    base = "https://clinicaltrials.gov/api/v2/studies"
    effective_limit = max(1, min(max_results or 80, 1000))
    effective_page_size = max(1, min(page_size or 50, 100))
    page_token = ""
    fetched = 0
    imported = 0
    updated = 0
    skipped_reasons: Counter[str] = Counter()
    started_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    try:
        while fetched < effective_limit:
            request_params = {
                **params,
                "pageSize": str(min(effective_page_size, effective_limit - fetched)),
                "format": "json",
                "countTotal": "true",
            }
            if page_token:
                request_params["pageToken"] = page_token
            payload = _get_json(base + "?" + urlencode(request_params))
            studies = payload.get("studies") or []
            if not studies:
                break
            for study in studies:
                fetched += 1
                document = _clinical_trial_document(study, query_name=name)
                if not document.get("source_key"):
                    skipped_reasons["missing_nct_id"] += 1
                    continue
                _, created = upsert_raw_document(document)
                if created:
                    imported += 1
                else:
                    updated += 1
                if fetched >= effective_limit:
                    break
            page_token = payload.get("nextPageToken") or ""
            if not page_token:
                break
            time.sleep(0.35)
        run = record_import_run(
            source_name=f"clinicaltrials_import_{name}",
            source_bucket=source_bucket,
            query=json.dumps(params, ensure_ascii=False),
            status="imported",
            fetched_count=fetched,
            imported_count=imported,
            metadata={
                "updated_count": updated,
                "skipped_count": sum(skipped_reasons.values()),
                "skip_reasons": dict(skipped_reasons),
                "max_results": effective_limit,
                "page_size": effective_page_size,
            },
            started_at=started_at,
        )
        print(
            f"clinicaltrials_import_{name}: fetched={fetched} new={imported} "
            f"updated={updated} skipped={sum(skipped_reasons.values())}"
        )
        return run
    except Exception as exc:
        record_import_run(
            source_name=f"clinicaltrials_import_{name}",
            source_bucket=source_bucket,
            query=json.dumps(params, ensure_ascii=False),
            status="failed",
            fetched_count=fetched,
            imported_count=imported,
            error=str(exc),
            metadata={
                "updated_count": updated,
                "skipped_count": sum(skipped_reasons.values()),
                "skip_reasons": dict(skipped_reasons),
                "max_results": effective_limit,
                "page_size": effective_page_size,
            },
            started_at=started_at,
        )
        raise


def _clinical_trial_document(study: dict, *, query_name: str) -> dict:
    protocol = study.get("protocolSection") or {}
    identification = protocol.get("identificationModule") or {}
    status = protocol.get("statusModule") or {}
    conditions = protocol.get("conditionsModule") or {}
    design = protocol.get("designModule") or {}
    arms = protocol.get("armsInterventionsModule") or {}
    description = protocol.get("descriptionModule") or {}
    sponsor = protocol.get("sponsorCollaboratorsModule") or {}
    nct_id = str(identification.get("nctId") or "").strip()
    title = _clean_text(
        identification.get("briefTitle")
        or identification.get("officialTitle")
        or f"ClinicalTrials.gov {nct_id}"
    )
    condition_values = _dedupe(conditions.get("conditions") or [])
    intervention_values = _trial_interventions(arms)
    phase_values = _dedupe(design.get("phases") or [])
    overall_status = str(status.get("overallStatus") or "")
    summary = _clean_text(
        " ".join(
            part
            for part in [
                f"Status: {overall_status}." if overall_status else "",
                f"Conditions: {', '.join(condition_values)}." if condition_values else "",
                f"Interventions: {', '.join(intervention_values)}." if intervention_values else "",
                f"Phases: {', '.join(phase_values)}." if phase_values else "",
                description.get("briefSummary") or "",
            ]
            if part
        )
    )
    text = f"{title} {summary}".lower()
    tags = ["ClinicalTrials.gov", "临床试验", "过敏性鼻炎"]
    if "immunotherapy" in text or "sublingual" in text or "subcutaneous" in text:
        tags.append("免疫治疗")
    if "pediatric" in text or "children" in text or "child" in text:
        tags.append("儿童")
    if "asthma" in text:
        tags.append("合并哮喘")
    review_status = "needs_review" if "免疫治疗" in tags or overall_status in {"RECRUITING", "ACTIVE_NOT_RECRUITING", "COMPLETED"} else "candidate"
    return {
        "source_key": f"clinicaltrials:{nct_id}",
        "source_bucket": "trial_candidates",
        "source_type": "trial_registry",
        "title": title,
        "url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
        "year": _trial_year(status),
        "journal_or_org": _lead_sponsor_name(sponsor) or "ClinicalTrials.gov",
        "language": "en",
        "evidence_level": "trial_registry",
        "review_status": review_status,
        "license_status": "public_registry",
        "open_access": True,
        "patient_visible": False,
        "doctor_visible": True,
        "research_visible": True,
        "topic_tags": _dedupe([*tags, query_name]),
        "content_summary": _trim(summary or title, 900),
        "raw_payload": {
            "source": "ClinicalTrials.gov",
            "query_name": query_name,
            "nct_id": nct_id,
            "overall_status": overall_status,
            "conditions": condition_values,
            "interventions": intervention_values,
            "phases": phase_values,
            "has_results": bool(study.get("hasResults")),
            "raw": study,
        },
        "chunks": [
            {
                "heading": "临床试验登记摘要",
                "scenario": "research",
                "content": _trim(summary or title, 2400),
                "topic_tags": _dedupe(tags),
                "patient_visible": False,
                "doctor_visible": True,
                "research_visible": True,
            }
        ],
    }


def _trial_interventions(arms: dict) -> list[str]:
    values = []
    for item in arms.get("interventions") or []:
        if item.get("name"):
            values.append(item["name"])
        if item.get("type"):
            values.append(item["type"])
    return _dedupe(values)


def _trial_year(status: dict) -> int | None:
    for key in ["startDateStruct", "studyFirstSubmitDate", "lastUpdateSubmitDate"]:
        value = status.get(key)
        if isinstance(value, dict):
            year = _safe_int(value.get("date", "")[:4])
        else:
            year = _safe_int(str(value or "")[:4])
        if year:
            return year
    return None


def _lead_sponsor_name(sponsor: dict) -> str:
    lead = sponsor.get("leadSponsor") or {}
    return str(lead.get("name") or "")


def fetch_openalex_counts() -> None:
    base = "https://api.openalex.org/works"
    for name, bucket, query in OPENALEX_QUERIES:
        url = base + "?" + urlencode({"search": query, "per-page": "1"})
        try:
            data = _get_json(url)
            _record_success(name, bucket, query, int(data.get("meta", {}).get("count") or 0))
        except Exception as exc:
            _record_failure(name, bucket, query, exc)
        time.sleep(0.35)


def enrich_openalex_metadata(*, limit: int, force: bool = False) -> dict:
    from app.rhinitis_evidence import record_import_run, rhinitis_evidence_db_path

    effective_limit = max(1, min(limit or 200, 2000))
    conn = sqlite3.connect(rhinitis_evidence_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, source_key, doi, raw_payload_json
        FROM raw_documents
        WHERE doi != ''
        ORDER BY id ASC
        LIMIT ?
        """,
        (effective_limit,),
    ).fetchall()
    scanned = 0
    enriched = 0
    skipped = 0
    failed = 0
    failures: list[dict[str, str]] = []
    started_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    try:
        for row in rows:
            scanned += 1
            raw_payload = json.loads(row["raw_payload_json"] or "{}")
            if raw_payload.get("openalex") and not force:
                skipped += 1
                continue
            doi = _normalize_doi(row["doi"])
            try:
                work = _get_json(f"https://api.openalex.org/works/{quote('https://doi.org/' + doi, safe='')}")
                raw_payload["openalex"] = _openalex_summary(work)
                conn.execute(
                    """
                    UPDATE raw_documents
                    SET raw_payload_json = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        json.dumps(raw_payload, ensure_ascii=False),
                        datetime.now(UTC).replace(microsecond=0).isoformat(),
                        row["id"],
                    ),
                )
                enriched += 1
            except Exception as exc:
                failed += 1
                failures.append({"source_key": row["source_key"], "doi": doi, "error": str(exc)[:500]})
            time.sleep(0.15)
        conn.commit()
    finally:
        conn.close()
    run = record_import_run(
        source_name="openalex_enrich_doi",
        source_bucket="literature_candidates",
        query="raw_documents.doi",
        status="enriched_with_errors" if failed else "enriched",
        fetched_count=scanned,
        imported_count=enriched,
        metadata={
            "skipped_count": skipped,
            "failed_count": failed,
            "failures": failures[:20],
            "force": force,
            "limit": effective_limit,
        },
        started_at=started_at,
    )
    print(f"openalex_enrich_doi: scanned={scanned} enriched={enriched} skipped={skipped} failed={failed}")
    return run


def _openalex_summary(work: dict) -> dict:
    primary_location = work.get("primary_location") or {}
    source = primary_location.get("source") or {}
    return {
        "id": work.get("id") or "",
        "doi": _normalize_doi(work.get("doi") or ""),
        "display_name": work.get("display_name") or work.get("title") or "",
        "publication_year": work.get("publication_year"),
        "cited_by_count": work.get("cited_by_count"),
        "open_access": work.get("open_access") or {},
        "primary_source": {
            "id": source.get("id") or "",
            "display_name": source.get("display_name") or "",
            "type": source.get("type") or "",
        },
        "updated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }


def fetch_drug_label_counts() -> None:
    for term in DRUG_TERMS:
        openfda_name = f"openfda_label_{term.replace(' ', '_')}"
        openfda_url = f"https://api.fda.gov/drug/label.json?search={quote(term)}&limit=1"
        try:
            data = _get_json(openfda_url)
            count = int(data.get("meta", {}).get("results", {}).get("total") or 0)
            _record_success(openfda_name, "drug_candidates", term, count)
        except Exception as exc:
            _record_failure(openfda_name, "drug_candidates", term, exc)
        time.sleep(0.35)

        dailymed_name = f"dailymed_{term.replace(' ', '_')}"
        dailymed_url = f"https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json?drug_name={quote(term)}&pagesize=1&page=1"
        try:
            data = _get_json(dailymed_url)
            count = int(data.get("metadata", {}).get("total_elements") or 0)
            _record_success(dailymed_name, "drug_candidates", term, count)
        except Exception as exc:
            _record_failure(dailymed_name, "drug_candidates", term, exc)
        time.sleep(0.35)


def import_dailymed_candidates(*, max_results_per_term: int, page_size: int) -> None:
    for term in DRUG_TERMS:
        import_dailymed_term(term, max_results=max_results_per_term, page_size=page_size)
        time.sleep(0.35)


def import_dailymed_term(term: str, *, max_results: int, page_size: int) -> dict:
    from app.rhinitis_evidence import record_import_run, upsert_raw_document

    effective_limit = max(1, min(max_results or 12, 100))
    effective_page_size = max(1, min(page_size or 20, 100))
    max_scan = max(effective_limit * 4, effective_limit)
    fetched = 0
    imported = 0
    updated = 0
    skipped_reasons: Counter[str] = Counter()
    page = 1
    started_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    try:
        while fetched < max_scan and imported + updated < effective_limit:
            url = "https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json?" + urlencode(
                {"drug_name": term, "pagesize": str(effective_page_size), "page": str(page)}
            )
            payload = _get_json(url)
            rows = payload.get("data") or []
            if not rows:
                break
            for item in rows:
                fetched += 1
                if not _dailymed_title_relevant(term, item.get("title") or ""):
                    skipped_reasons["title_not_rhinitis_relevant"] += 1
                    continue
                document = _dailymed_document(term, item)
                _, created = upsert_raw_document(document)
                if created:
                    imported += 1
                else:
                    updated += 1
                if imported + updated >= effective_limit or fetched >= max_scan:
                    break
            metadata = payload.get("metadata") or {}
            next_page = metadata.get("next_page")
            if not next_page or str(next_page).lower() == "null":
                break
            page = int(next_page)
            time.sleep(0.35)
        run = record_import_run(
            source_name=f"dailymed_import_{term.replace(' ', '_')}",
            source_bucket="drug_candidates",
            query=term,
            status="imported",
            fetched_count=fetched,
            imported_count=imported,
            metadata={
                "updated_count": updated,
                "skipped_count": sum(skipped_reasons.values()),
                "skip_reasons": dict(skipped_reasons),
                "max_results_per_term": effective_limit,
                "page_size": effective_page_size,
                "max_scan": max_scan,
            },
            started_at=started_at,
        )
        print(
            f"dailymed_import_{term}: fetched={fetched} new={imported} "
            f"updated={updated} skipped={sum(skipped_reasons.values())}"
        )
        return run
    except Exception as exc:
        record_import_run(
            source_name=f"dailymed_import_{term.replace(' ', '_')}",
            source_bucket="drug_candidates",
            query=term,
            status="failed",
            fetched_count=fetched,
            imported_count=imported,
            error=str(exc),
            metadata={
                "updated_count": updated,
                "skipped_count": sum(skipped_reasons.values()),
                "skip_reasons": dict(skipped_reasons),
                "max_results_per_term": effective_limit,
                "page_size": effective_page_size,
                "max_scan": max_scan,
            },
            started_at=started_at,
        )
        raise


def _dailymed_document(term: str, item: dict) -> dict:
    setid = str(item.get("setid") or "").strip()
    title = _clean_text(item.get("title") or f"DailyMed {term} label")
    year = _safe_int(str(item.get("published_date") or ""))
    tags = _dailymed_tags(term, title)
    summary = (
        f"DailyMed SPL label candidate for {term}. Title: {title}. "
        f"Published date: {item.get('published_date') or 'unknown'}. "
        "This drug-label candidate must be reviewed before any patient-facing use."
    )
    return {
        "source_key": f"dailymed:{setid}",
        "source_bucket": "drug_candidates",
        "source_type": "drug_label",
        "title": title,
        "url": f"https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid={setid}" if setid else "",
        "year": year,
        "journal_or_org": "DailyMed / National Library of Medicine",
        "language": "en",
        "evidence_level": "drug_label",
        "review_status": "needs_review",
        "license_status": "public_label",
        "open_access": True,
        "patient_visible": False,
        "doctor_visible": True,
        "research_visible": True,
        "topic_tags": tags,
        "content_summary": _trim(summary, 900),
        "raw_payload": {
            "source": "DailyMed",
            "drug_term": term,
            "setid": setid,
            "spl_version": item.get("spl_version"),
            "published_date": item.get("published_date"),
            "raw": item,
        },
        "chunks": [
            {
                "heading": "DailyMed 药品标签候选",
                "scenario": "research",
                "content": _trim(summary, 1600),
                "topic_tags": tags,
                "patient_visible": False,
                "doctor_visible": True,
                "research_visible": True,
            }
        ],
    }


def _dailymed_title_relevant(term: str, title: str) -> bool:
    text = f"{term} {title}".lower()
    nasal_terms = {"fluticasone", "mometasone", "budesonide", "azelastine"}
    if term in nasal_terms:
        return any(token in text for token in ["nasal", "spray", "allergy"])
    if term == "montelukast":
        return "montelukast" in text
    return any(token in text for token in [term, "allergy", "tablet", "capsule", "solution", "syrup", "antihistamine"])


def _dailymed_tags(term: str, title: str) -> list[str]:
    text = f"{term} {title}".lower()
    tags = ["DailyMed", "药品说明书", term]
    if any(token in text for token in ["fluticasone", "mometasone", "budesonide", "nasal", "spray"]):
        tags.append("鼻喷激素")
    if any(token in text for token in ["azelastine", "cetirizine", "loratadine", "fexofenadine", "levocetirizine", "desloratadine"]):
        tags.append("抗组胺")
    if "montelukast" in text:
        tags.append("白三烯")
    return _dedupe(tags)


def print_import_report(*, limit: int = 12) -> None:
    from app.rhinitis_evidence import rhinitis_evidence_db_path

    conn = sqlite3.connect(rhinitis_evidence_db_path())
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT source_name, source_bucket, status, fetched_count, imported_count, metadata_json, finished_at
            FROM import_runs
            WHERE source_name LIKE 'pubmed_import_%'
            ORDER BY id DESC
            LIMIT ?
            """,
            (max(1, min(int(limit), 100)),),
        ).fetchall()
    finally:
        conn.close()

    if not rows:
        print("PubMed import report: no import runs")
        return

    print("\nPubMed import report")
    print(
        "source".ljust(42),
        "bucket".ljust(24),
        "fetched".rjust(7),
        "eligible".rjust(8),
        "new".rjust(5),
        "updated".rjust(7),
        "skipped".rjust(7),
        "hit_count".rjust(9),
        "top_skip_reasons",
        sep="  ",
    )
    for row in rows:
        metadata = json.loads(row["metadata_json"] or "{}")
        skip_reasons = metadata.get("skip_reasons") or {}
        top_reasons = ", ".join(
            f"{reason}:{count}"
            for reason, count in sorted(skip_reasons.items(), key=lambda item: item[1], reverse=True)[:3]
        )
        print(
            row["source_name"].replace("pubmed_import_", "").ljust(42),
            row["source_bucket"].ljust(24),
            str(row["fetched_count"]).rjust(7),
            str(metadata.get("eligible_count", "")).rjust(8),
            str(row["imported_count"]).rjust(5),
            str(metadata.get("updated_count", "")).rjust(7),
            str(metadata.get("skipped_count", "")).rjust(7),
            str(metadata.get("query_hit_count", "")).rjust(9),
            top_reasons or "-",
            sep="  ",
        )
    print("")


def rescreen_pubmed_documents(*, apply_changes: bool = False, limit: int = 0) -> None:
    from app.rhinitis_evidence import init_rhinitis_evidence_db, rhinitis_evidence_db_path

    init_rhinitis_evidence_db()
    conn = sqlite3.connect(rhinitis_evidence_db_path())
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT id, source_key, source_bucket, source_type, title, content_summary, evidence_level,
               review_status, topic_tags_json, raw_payload_json
        FROM raw_documents
        WHERE source_key LIKE 'pubmed:%'
          AND review_status != 'approved'
        ORDER BY id ASC
        """
    ).fetchall()
    if limit > 0:
        rows = rows[:limit]

    counters: Counter[str] = Counter()
    changes: list[tuple[sqlite3.Row, dict, str, str]] = []
    for row in rows:
        raw_payload = json.loads(row["raw_payload_json"] or "{}")
        publication_types = raw_payload.get("publication_types") or []
        mesh_terms = raw_payload.get("mesh_terms") or []
        screening_profile = (raw_payload.get("screening") or {}).get("profile") or ""
        title = row["title"] or ""
        summary = row["content_summary"] or ""
        evidence_level = _pubmed_evidence_level(publication_types, title, summary)
        topic_tags = _pubmed_topic_tags(title, summary, mesh_terms, publication_types, evidence_level)
        candidate_doc = {
            "title": title,
            "content_summary": summary,
            "evidence_level": evidence_level,
            "topic_tags": topic_tags,
            "raw_payload": {
                "publication_types": publication_types,
                "mesh_terms": mesh_terms,
                "has_abstract": bool(summary),
                "abstract_length": len(summary),
            },
        }
        accepted, reason = _screen_pubmed_document(candidate_doc, screening_profile) if screening_profile else (True, "accepted")
        if not accepted and reason in {"not_allergic_rhinitis", "animal_only", "low_value_publication_type", "basic_science_only"}:
            review_status = "rejected"
            source_bucket = row["source_bucket"]
        else:
            review_status = _pubmed_review_status(evidence_level, title, summary) if accepted else "candidate"
            source_bucket = _rescreen_source_bucket(screening_profile, evidence_level, accepted)
        source_type = _source_type_for_evidence(evidence_level)
        desired = {
            "source_bucket": source_bucket,
            "source_type": source_type,
            "evidence_level": evidence_level,
            "review_status": review_status,
            "topic_tags_json": json.dumps(topic_tags, ensure_ascii=False),
        }
        current = {
            "source_bucket": row["source_bucket"],
            "source_type": row["source_type"],
            "evidence_level": row["evidence_level"],
            "review_status": row["review_status"],
            "topic_tags_json": row["topic_tags_json"],
        }
        counters[f"decision:{'accepted' if accepted else reason}"] += 1
        counters[f"status:{review_status}"] += 1
        counters[f"bucket:{source_bucket}"] += 1
        if desired != current:
            raw_payload["rescreening"] = {
                "decision": "accepted" if accepted else reason,
                "profile": screening_profile,
                "applied": apply_changes,
                "at": datetime.now(UTC).replace(microsecond=0).isoformat(),
            }
            changes.append((row, {**desired, "raw_payload_json": json.dumps(raw_payload, ensure_ascii=False)}, "accepted" if accepted else reason, screening_profile))

    print(
        f"pubmed_rescreen: scanned={len(rows)} changes={len(changes)} "
        f"mode={'apply' if apply_changes else 'dry_run'}"
    )
    for name, count in sorted(counters.items()):
        print(f"{name}: {count}")
    if changes:
        print("sample_changes:")
        for row, desired, reason, profile in changes[:12]:
            print(
                f"- {row['source_key']} | {profile or '-'} | {reason} | "
                f"{row['source_bucket']}->{desired['source_bucket']} | "
                f"{row['evidence_level']}->{desired['evidence_level']} | "
                f"{row['review_status']}->{desired['review_status']} | {row['title'][:90]}"
            )

    if not apply_changes or not changes:
        conn.close()
        return

    now = datetime.now(UTC).replace(microsecond=0).isoformat()
    for row, desired, _reason, _profile in changes:
        conn.execute(
            """
            UPDATE raw_documents
            SET source_bucket = ?, source_type = ?, evidence_level = ?, review_status = ?,
                topic_tags_json = ?, raw_payload_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                desired["source_bucket"],
                desired["source_type"],
                desired["evidence_level"],
                desired["review_status"],
                desired["topic_tags_json"],
                desired["raw_payload_json"],
                now,
                row["id"],
            ),
        )
        conn.execute(
            """
            UPDATE raw_chunks
            SET topic_tags_json = ?, updated_at = ?
            WHERE document_id = ?
            """,
            (desired["topic_tags_json"], now, row["id"]),
        )
    conn.commit()
    conn.close()
    init_rhinitis_evidence_db()


def _rescreen_source_bucket(screening_profile: str, evidence_level: str, accepted: bool) -> str:
    profile_bucket = str(PUBMED_QUERY_SPECS.get(screening_profile, {}).get("bucket") or "literature_candidates")
    if accepted and profile_bucket == "environment_candidates":
        return "environment_candidates"
    if accepted and profile_bucket == "guideline_candidates" and evidence_level in {"guideline", "consensus"}:
        return "guideline_candidates"
    return "literature_candidates"


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialize and inspect the Rhinitis Evidence Library.")
    parser.add_argument(
        "--fetch-counts",
        action="store_true",
        help="Call public APIs and record candidate count import runs. Without this flag only initializes local seed data.",
    )
    parser.add_argument(
        "--import-pubmed",
        action="store_true",
        help="Import one screened PubMed query into raw candidate documents.",
    )
    parser.add_argument(
        "--import-seed-sources",
        action="store_true",
        help="Fetch public URLs listed in knowledge/rhinitis_seed_sources.yaml into separate raw candidate documents.",
    )
    parser.add_argument(
        "--import-europe-pmc",
        action="store_true",
        help="Import screened Europe PMC metadata and abstracts into raw candidate documents.",
    )
    parser.add_argument(
        "--import-clinical-trials",
        action="store_true",
        help="Import ClinicalTrials.gov allergic rhinitis study registrations into raw candidate documents.",
    )
    parser.add_argument(
        "--import-dailymed",
        action="store_true",
        help="Import DailyMed SPL drug label candidates for configured rhinitis medication terms.",
    )
    parser.add_argument(
        "--enrich-openalex",
        action="store_true",
        help="Enrich existing DOI-bearing raw documents with OpenAlex citation and open-access metadata.",
    )
    parser.add_argument(
        "--import-pubmed-plan",
        choices=sorted(PUBMED_IMPORT_PLANS),
        help="Import a screened PubMed priority plan across multiple source buckets.",
    )
    parser.add_argument(
        "--pubmed-query",
        choices=sorted(PUBMED_IMPORT_QUERIES),
        default="pubmed_guideline_consensus",
        help="Named PubMed query to import.",
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=0,
        help="Maximum PubMed records fetched per query. Use 0 for profile defaults. Capped at 1000.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="PubMed efetch batch size. Capped at 200.",
    )
    parser.add_argument(
        "--retstart",
        type=int,
        default=0,
        help="PubMed esearch retstart offset for paged imports.",
    )
    parser.add_argument(
        "--seed-limit",
        type=int,
        default=0,
        help="Optional number of seed source documents to process. Use 0 for all seed documents.",
    )
    parser.add_argument(
        "--europe-pmc-max-results",
        type=int,
        default=80,
        help="Maximum Europe PMC records fetched per query.",
    )
    parser.add_argument(
        "--europe-pmc-page-size",
        type=int,
        default=50,
        help="Europe PMC page size per request, capped at 100.",
    )
    parser.add_argument(
        "--clinical-trials-max-results",
        type=int,
        default=80,
        help="Maximum ClinicalTrials.gov records fetched per query.",
    )
    parser.add_argument(
        "--clinical-trials-page-size",
        type=int,
        default=50,
        help="ClinicalTrials.gov page size per request, capped at 100.",
    )
    parser.add_argument(
        "--dailymed-max-results",
        type=int,
        default=12,
        help="Maximum DailyMed SPL candidates imported per drug term.",
    )
    parser.add_argument(
        "--dailymed-page-size",
        type=int,
        default=20,
        help="DailyMed page size per request, capped at 100.",
    )
    parser.add_argument(
        "--openalex-limit",
        type=int,
        default=200,
        help="Maximum DOI-bearing raw documents to enrich from OpenAlex.",
    )
    parser.add_argument(
        "--openalex-force",
        action="store_true",
        help="Refresh OpenAlex metadata even when a document already has openalex payload.",
    )
    parser.add_argument(
        "--no-screen",
        action="store_true",
        help="Disable import-time PubMed screening. Intended only for debugging counts and parser behavior.",
    )
    parser.add_argument(
        "--report-imports",
        action="store_true",
        help="Print a compact PubMed import report from recent import_runs.",
    )
    parser.add_argument(
        "--rescreen-pubmed",
        action="store_true",
        help="Re-evaluate existing PubMed raw candidates with the current screening rules.",
    )
    parser.add_argument(
        "--apply-rescreen",
        action="store_true",
        help="Apply --rescreen-pubmed changes. Without this flag rescreening is a dry run.",
    )
    parser.add_argument(
        "--rescreen-limit",
        type=int,
        default=0,
        help="Optional limit for --rescreen-pubmed. Use 0 for all PubMed candidates.",
    )
    parser.add_argument(
        "--report-limit",
        type=int,
        default=12,
        help="Maximum PubMed import runs shown by --report-imports.",
    )
    args = parser.parse_args()

    from app.rhinitis_evidence import evidence_stats, init_rhinitis_evidence_db

    init_rhinitis_evidence_db()
    if args.fetch_counts:
        fetch_pubmed_counts()
        fetch_europe_pmc_counts()
        fetch_clinical_trials_counts()
        fetch_drug_label_counts()
        fetch_openalex_counts()
    if args.import_seed_sources:
        import_seed_source_pages(limit=args.seed_limit)
    if args.import_europe_pmc:
        import_europe_pmc_candidates(
            max_results=args.europe_pmc_max_results,
            page_size=args.europe_pmc_page_size,
        )
    if args.import_clinical_trials:
        import_clinical_trials_candidates(
            max_results=args.clinical_trials_max_results,
            page_size=args.clinical_trials_page_size,
        )
    if args.import_dailymed:
        import_dailymed_candidates(
            max_results_per_term=args.dailymed_max_results,
            page_size=args.dailymed_page_size,
        )
    if args.enrich_openalex:
        enrich_openalex_metadata(limit=args.openalex_limit, force=args.openalex_force)
    if args.import_pubmed_plan:
        import_pubmed_plan(
            args.import_pubmed_plan,
            max_results=args.max_results,
            batch_size=args.batch_size,
            retstart=args.retstart,
            screened=not args.no_screen,
        )
    if args.import_pubmed:
        import_pubmed_candidates(
            args.pubmed_query,
            max_results=args.max_results,
            batch_size=args.batch_size,
            retstart=args.retstart,
            screened=not args.no_screen,
        )
    if args.report_imports:
        print_import_report(limit=args.report_limit)
    if args.rescreen_pubmed:
        rescreen_pubmed_documents(apply_changes=args.apply_rescreen, limit=args.rescreen_limit)

    print(json.dumps(evidence_stats(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
