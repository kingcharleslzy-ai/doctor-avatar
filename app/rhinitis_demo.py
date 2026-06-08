from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from .models import RhinitisDemoCase
from .rhinitis_evidence import list_answer_citations, record_answer_citations, search_evidence


DOCTOR_OUTPUT = "doctor_summary"
PATIENT_OUTPUT = "patient_education"
DIGITAL_HUMAN_OUTPUT = "digital_human_script"


def default_rhinitis_demo_case() -> RhinitisDemoCase:
    return RhinitisDemoCase()


def build_rhinitis_demo_summary(case: RhinitisDemoCase) -> dict[str, Any]:
    output_id = f"rhinitis-demo-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    case_payload = case.model_dump()
    queries = _build_queries(case_payload)

    doctor_evidence = _collect_evidence(queries["doctor"], scenario="doctor", max_items=8)
    patient_evidence = _collect_evidence(queries["patient"], scenario="patient", max_items=4)
    script_evidence = _dedupe_evidence([*doctor_evidence[:5], *patient_evidence[:3]], max_items=7)
    evidence_groups = _assign_global_refs(
        {
            DOCTOR_OUTPUT: doctor_evidence,
            PATIENT_OUTPUT: patient_evidence,
            DIGITAL_HUMAN_OUTPUT: script_evidence,
        }
    )
    doctor_evidence = evidence_groups[DOCTOR_OUTPUT]
    patient_evidence = evidence_groups[PATIENT_OUTPUT]
    script_evidence = evidence_groups[DIGITAL_HUMAN_OUTPUT]

    doctor_summary = _build_doctor_summary(case_payload, doctor_evidence)
    patient_education = _build_patient_education(case_payload, patient_evidence)
    digital_human_script = _build_digital_human_script(case_payload, script_evidence)

    citation_records = []
    for output_type, evidence_items in [
        (DOCTOR_OUTPUT, doctor_evidence),
        (PATIENT_OUTPUT, patient_evidence),
        (DIGITAL_HUMAN_OUTPUT, script_evidence),
    ]:
        citation_records.extend(
            record_answer_citations(
                output_type=output_type,
                output_id=output_id,
                citations=evidence_items,
                chunk_scope="curated",
            )
        )

    return {
        "output_id": output_id,
        "case": case_payload,
        "retrieval": {
            "scope": "curated",
            "doctor_queries": queries["doctor"],
            "patient_queries": queries["patient"],
            "doctor_evidence_count": len(doctor_evidence),
            "patient_evidence_count": len(patient_evidence),
            "script_evidence_count": len(script_evidence),
            "unique_evidence_count": _unique_evidence_count(evidence_groups),
        },
        "doctor_summary": doctor_summary,
        "patient_education": patient_education,
        "digital_human_script": digital_human_script,
        "evidence": evidence_groups,
        "answer_citations": list_answer_citations(output_id),
        "citation_record_count": len(citation_records),
    }


def _build_queries(case_payload: dict[str, Any]) -> dict[str, list[str]]:
    symptoms_text = _join(case_payload.get("main_symptoms"))
    trigger_text = _join(case_payload.get("triggers"))
    medication_text = str(case_payload.get("medication_history") or "")
    allergen_text = str(case_payload.get("allergen_tests") or "")
    endoscopy_text = str(case_payload.get("nasal_endoscopy") or "")
    comorbidity_text = _join(case_payload.get("comorbidities"))

    doctor_queries = [
        "过敏性鼻炎 诊断 治疗 指南",
        "鼻喷激素 抗组胺 过敏性鼻炎",
        "过敏原 IgE 免疫治疗 过敏性鼻炎",
    ]
    patient_queries = [
        "过敏性鼻炎 日常预防",
        "鼻腔冲洗 过敏性鼻炎",
        "花粉 过敏性鼻炎",
    ]

    if "花粉" in trigger_text or "季" in str(case_payload.get("seasonality") or ""):
        doctor_queries.append("花粉 环境暴露 过敏性鼻炎")
    if "鼻内镜" in endoscopy_text or "下鼻甲" in endoscopy_text or "黏膜" in endoscopy_text:
        doctor_queries.append("鼻内镜 下鼻甲 过敏性鼻炎")
    if "免疫" in medication_text or "脱敏" in medication_text or "IgE" in allergen_text or "ige" in allergen_text.lower():
        doctor_queries.append("变应原免疫治疗 IgE 过敏性鼻炎")
    if "儿童" in case_payload.get("age_group", "") or "儿童" in comorbidity_text:
        doctor_queries.append("儿童 过敏性鼻炎 指南")
    if "哮喘" in comorbidity_text or "咳嗽" in comorbidity_text:
        doctor_queries.append("过敏性鼻炎 合并哮喘")
    if "氟替卡松" in medication_text or "鼻喷" in medication_text or "喷嚏" in symptoms_text:
        doctor_queries.append("intranasal corticosteroids allergic rhinitis")

    return {
        "doctor": _dedupe_strings(doctor_queries)[:8],
        "patient": _dedupe_strings(patient_queries)[:5],
    }


def _collect_evidence(queries: list[str], *, scenario: str, max_items: int) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for query in queries:
        payload = search_evidence(query, scope="curated", scenario=scenario, limit=4)
        for item in payload.get("results") or []:
            if item.get("review_status") != "approved":
                continue
            collected.append(_citation_item(item, query=query))
    return _dedupe_evidence(collected, max_items=max_items)


def _citation_item(item: dict[str, Any], *, query: str) -> dict[str, Any]:
    label = _citation_label(item)
    return {
        "label": label,
        "citation_label": label,
        "query": query,
        "document_id": item.get("document_id"),
        "chunk_id": item.get("chunk_id"),
        "title": item.get("title") or "",
        "heading": item.get("heading") or "",
        "snippet": item.get("snippet") or "",
        "url": item.get("url") or "",
        "pmid": item.get("pmid") or "",
        "doi": item.get("doi") or "",
        "year": item.get("year"),
        "journal_or_org": item.get("journal_or_org") or "",
        "evidence_level": item.get("evidence_level") or "",
        "patient_visible": bool(item.get("patient_visible")),
        "doctor_visible": bool(item.get("doctor_visible")),
        "topic_tags": item.get("topic_tags") or [],
        "score": item.get("score"),
    }


def _citation_label(item: dict[str, Any]) -> str:
    parts = []
    if item.get("pmid"):
        parts.append(f"PMID {item['pmid']}")
    if item.get("doi"):
        parts.append(f"DOI {item['doi']}")
    if item.get("year"):
        parts.append(str(item["year"]))
    suffix = " · ".join(parts) or str(item.get("journal_or_org") or item.get("evidence_level") or "evidence")
    return f"{item.get('title') or 'Evidence'} | {suffix}"[:200]


def _dedupe_evidence(items: list[dict[str, Any]], *, max_items: int) -> list[dict[str, Any]]:
    results = []
    seen: set[tuple[int, int]] = set()
    for item in items:
        key = (int(item.get("document_id") or 0), int(item.get("chunk_id") or 0))
        if key in seen or not key[0] or not key[1]:
            continue
        seen.add(key)
        results.append(dict(item))
        if len(results) >= max_items:
            break
    return results


def _assign_global_refs(groups: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    ref_by_key: dict[tuple[int, int], str] = {}
    ref_index = 1
    output: dict[str, list[dict[str, Any]]] = {}
    for group_name in [DOCTOR_OUTPUT, PATIENT_OUTPUT, DIGITAL_HUMAN_OUTPUT]:
        output[group_name] = []
        for item in groups.get(group_name) or []:
            key = (int(item.get("document_id") or 0), int(item.get("chunk_id") or 0))
            if key not in ref_by_key:
                ref_by_key[key] = f"R{ref_index:02d}"
                ref_index += 1
            copied = dict(item)
            copied["ref"] = ref_by_key[key]
            output[group_name].append(copied)
    return output


def _unique_evidence_count(groups: dict[str, list[dict[str, Any]]]) -> int:
    return len(
        {
            (int(item.get("document_id") or 0), int(item.get("chunk_id") or 0))
            for items in groups.values()
            for item in items
            if item.get("document_id") and item.get("chunk_id")
        }
    )


def _build_doctor_summary(case_payload: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    symptoms = _join(case_payload.get("main_symptoms"))
    triggers = _join(case_payload.get("triggers"))
    comorbidities = _join(case_payload.get("comorbidities"))
    refs = _refs(evidence[:5])
    return {
        "title": "医生摘要",
        "sections": [
            {
                "heading": "病史要点",
                "items": [
                    f"{case_payload.get('age_group')}，主要症状为{symptoms}。",
                    f"病程：{case_payload.get('duration')}。",
                    f"季节和诱因：{case_payload.get('seasonality')}；相关诱因为{triggers}。",
                ],
            },
            {
                "heading": "已知检查和治疗线索",
                "items": [
                    f"用药史：{case_payload.get('medication_history')}。",
                    f"过敏原/IgE：{case_payload.get('allergen_tests')}。",
                    f"鼻内镜描述：{case_payload.get('nasal_endoscopy')}。",
                    f"合并情况：{comorbidities}。",
                ],
            },
            {
                "heading": "接诊提示",
                "items": [
                    "当前信息支持按过敏性鼻炎方向做结构化评估，但不能替代线下面诊诊断。",
                    "建议补充症状严重度、睡眠/学习工作影响、单侧症状、脓涕/发热/面痛等鼻窦炎警示信息。",
                    "如考虑免疫治疗，应结合明确过敏原、症状控制情况、依从性和安全性评估。",
                ],
            },
        ],
        "evidence_refs": refs,
    }


def _build_patient_education(case_payload: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    refs = _refs(evidence)
    trigger_text = _join(case_payload.get("triggers"))
    return {
        "title": "患者宣教",
        "paragraphs": [
            f"你描述的鼻塞、喷嚏、流清涕和鼻痒在{case_payload.get('seasonality')}时加重，确实需要按过敏性鼻炎方向进一步评估。",
            f"日常先关注诱因管理，尤其是{trigger_text}相关暴露；花粉季外出、打扫卫生和睡前鼻部护理可以作为重点记录。",
            "鼻腔冲洗、环境控制和规范复诊可以帮助医生判断症状变化。药物种类、使用频率和是否需要免疫治疗，需要线下医生结合检查结果决定。",
            "如果出现持续高热、剧烈头痛、明显面部疼痛、视力异常、反复大量鼻出血或呼吸困难，应及时线下就医。",
        ],
        "evidence_refs": refs,
    }


def _build_digital_human_script(case_payload: dict[str, Any], evidence: list[dict[str, Any]]) -> dict[str, Any]:
    refs = _refs(evidence[:5])
    symptoms = _join(case_payload.get("main_symptoms"))
    return {
        "title": "数字人宣教脚本",
        "script": (
            f"你好，我是李医生。你提供的信息里，{symptoms}反复出现，并且和季节、环境诱因有关，"
            "这类情况需要按过敏性鼻炎方向做规范评估。下一步重点不是自己加药，而是把病程、诱因、"
            "既往用药、过敏原检查和鼻内镜表现整理清楚。鼻喷药、抗组胺药和免疫治疗都要结合医生判断，"
            "尤其不能在线上直接决定剂量或疗程。你可以先记录最近两周症状变化和接触诱因，复诊时带上既往检查结果。"
        ),
        "evidence_refs": refs,
    }


def _refs(evidence: list[dict[str, Any]]) -> list[str]:
    return [str(item.get("ref")) for item in evidence if item.get("ref")]


def _join(values: Any) -> str:
    if isinstance(values, list):
        return "、".join(str(item).strip() for item in values if str(item).strip()) or "未填写"
    value = str(values or "").strip()
    return value or "未填写"


def _dedupe_strings(values: list[str]) -> list[str]:
    results: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = " ".join(str(value or "").split()).strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            results.append(cleaned)
    return results
