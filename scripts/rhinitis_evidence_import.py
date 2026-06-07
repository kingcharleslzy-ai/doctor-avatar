from __future__ import annotations

import argparse
from collections import Counter
from datetime import UTC, datetime
import json
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


USER_AGENT = "MedFlowRhinitisEvidence/0.1"
PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


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
