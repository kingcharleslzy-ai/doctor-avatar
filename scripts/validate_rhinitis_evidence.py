from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


SAMPLE_PUBMED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>12345678</PMID>
      <Article>
        <Journal>
          <JournalIssue>
            <PubDate><Year>2025</Year></PubDate>
          </JournalIssue>
          <Title>Journal of Rhinitis Evidence</Title>
          <ISOAbbreviation>J Rhin Evid</ISOAbbreviation>
        </Journal>
        <ArticleTitle>Allergic rhinitis guideline with nasal endoscopy observations</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Allergic rhinitis assessment may include allergen-specific IgE and nasal endoscopy observations. validationrhinitisendoscopytoken</AbstractText>
          <AbstractText Label="METHODS">This practice guideline discusses intranasal corticosteroid classes and immunotherapy review.</AbstractText>
        </Abstract>
        <AuthorList>
          <Author><LastName>Li</LastName><ForeName>Yong</ForeName></Author>
        </AuthorList>
        <Language>eng</Language>
        <PublicationTypeList>
          <PublicationType>Practice Guideline</PublicationType>
        </PublicationTypeList>
      </Article>
      <MeshHeadingList>
        <MeshHeading><DescriptorName>Rhinitis, Allergic</DescriptorName></MeshHeading>
        <MeshHeading><DescriptorName>Nasal Endoscopy</DescriptorName></MeshHeading>
      </MeshHeadingList>
    </MedlineCitation>
    <PubmedData>
      <ArticleIdList>
        <ArticleId IdType="pubmed">12345678</ArticleId>
        <ArticleId IdType="doi">10.0000/example</ArticleId>
        <ArticleId IdType="pmc">PMC1234567</ArticleId>
      </ArticleIdList>
    </PubmedData>
  </PubmedArticle>
</PubmedArticleSet>
"""


def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        os.environ["RHINITIS_EVIDENCE_DB_PATH"] = str(Path(tmpdir) / "rhinitis_evidence.db")
        os.environ["RHINITIS_AI_REVIEW_DIR"] = str(Path(tmpdir) / "rhinitis_ai_review")

        from app.rhinitis_evidence import (
            evidence_stats,
            get_evidence_document,
            init_rhinitis_evidence_db,
            list_answer_citations,
            review_evidence_batch,
            review_pack,
            review_queue,
            review_evidence_document,
            search_evidence,
            upsert_raw_document,
        )
        from app.config import settings
        from scripts.rhinitis_ai_review import apply_batch, export_batch, review_batch
        from scripts.rhinitis_evidence_import import _parse_pubmed_xml, _pubmed_evidence_level, _screen_pubmed_document
        from scripts.rhinitis_evidence_snapshot import (
            export_curated_snapshot,
            import_curated_snapshot,
            snapshot_stats,
        )

        init_rhinitis_evidence_db()
        stats = evidence_stats()
        assert stats["raw_documents"] >= 8, stats
        assert stats["curated_documents"] >= 5, stats
        assert stats["aliases"] >= 10, stats

        curated_fluticasone = search_evidence("辅舒良", scope="curated", limit=5)
        assert curated_fluticasone["results"], curated_fluticasone
        assert any("鼻喷激素" in item["snippet"] or "糖皮质激素" in item["snippet"] for item in curated_fluticasone["results"])

        raw_fluticasone = search_evidence("fluticasone", scope="raw", limit=10)
        assert any(item["review_status"] == "needs_review" for item in raw_fluticasone["results"]), raw_fluticasone
        candidate = next(item for item in raw_fluticasone["results"] if item["review_status"] == "needs_review")

        queue = review_queue(status="needs_review", source_bucket="drug_candidates", limit=10)
        assert queue["total"] >= 1, queue
        assert queue["results"], queue
        assert all(item["review_status"] == "needs_review" for item in queue["results"]), queue
        assert all(item["source_bucket"] == "drug_candidates" for item in queue["results"]), queue
        assert {"document_id", "title", "content_summary", "priority_score"}.issubset(queue["results"][0]), queue["results"][0]

        pack = review_pack()
        assert pack["groups"], pack
        assert pack["target"] >= 30, pack
        pack_ids = [
            item["document_id"]
            for group in pack["groups"]
            for item in group["items"]
        ]
        assert pack_ids, pack
        assert len(pack_ids) == len(set(pack_ids)), pack_ids

        reviewed = review_evidence_document(
            document_scope="raw",
            document_id=candidate["document_id"],
            status="approved",
            note="validation promotion",
            reviewer="validator",
            patient_visible=False,
            doctor_visible=True,
        )
        assert reviewed["review_status"] == "approved", reviewed

        curated_after = search_evidence("fluticasone", scope="curated", limit=10)
        assert any(item["title"] == candidate["title"] for item in curated_after["results"]), curated_after

        batch_queue = review_queue(status="needs_review", limit=10)
        batch_candidate = next((item for item in batch_queue["results"] if item["document_id"] != candidate["document_id"]), None)
        assert batch_candidate, batch_queue
        batch = review_evidence_batch(
            document_ids=[batch_candidate["document_id"]],
            status="approved",
            note="validation batch promotion",
            reviewer="validator",
            patient_visible=True,
            doctor_visible=True,
        )
        assert batch["updated_count"] == 1, batch
        curated_patient = search_evidence(batch_candidate["title"], scope="curated", scenario="patient", limit=10)
        assert any(item["title"] == batch_candidate["title"] for item in curated_patient["results"]), curated_patient
        assert all(item["patient_visible"] for item in curated_patient["results"]), curated_patient

        pollen_environment = search_evidence("花粉", scope="raw", source_bucket="environment_candidates", limit=5)
        assert pollen_environment["results"], pollen_environment
        assert all(item["source_bucket"] == "environment_candidates" for item in pollen_environment["results"]), pollen_environment

        doc = get_evidence_document(candidate["document_id"], scope="raw")
        assert doc and doc["chunks"], doc
        assert doc["review_notes"], doc
        assert doc["review_notes"][0]["note"] == "validation promotion", doc["review_notes"]
        assert doc["review_notes"][0]["reviewer"] == "validator", doc["review_notes"]

        parsed = _parse_pubmed_xml(SAMPLE_PUBMED_XML)
        assert len(parsed) == 1, parsed
        pubmed_doc = parsed[0]
        assert pubmed_doc["source_key"] == "pubmed:12345678", pubmed_doc
        assert pubmed_doc["evidence_level"] == "guideline", pubmed_doc
        assert pubmed_doc["review_status"] == "needs_review", pubmed_doc
        assert "鼻内镜" in pubmed_doc["topic_tags"], pubmed_doc["topic_tags"]
        accepted, reason = _screen_pubmed_document(pubmed_doc, "pubmed_guideline_consensus")
        assert accepted and reason == "accepted", (accepted, reason, pubmed_doc)
        weak_guideline_doc = dict(pubmed_doc)
        weak_guideline_doc["title"] = "ARIA consensus on chronic cough"
        weak_guideline_doc["content_summary"] = "The Allergic Rhinitis and its Impact on Asthma group discusses chronic cough."
        weak_guideline_doc["raw_payload"] = {
            "publication_types": ["Guideline"],
            "mesh_terms": ["Cough"],
            "has_abstract": True,
            "abstract_length": 86,
        }
        accepted, reason = _screen_pubmed_document(weak_guideline_doc, "pubmed_guideline_consensus")
        assert not accepted and reason == "weak_guideline_relevance", (accepted, reason)
        rct_level = _pubmed_evidence_level(["Clinical Trial"], "Randomized trial of allergic rhinitis therapy", "")
        assert rct_level == "rct", rct_level
        consensus_level = _pubmed_evidence_level([], "Chinese expert consensus on intranasal therapy for allergic rhinitis", "")
        assert consensus_level == "consensus", consensus_level
        ordinary_review_level = _pubmed_evidence_level(
            ["Journal Article"],
            "Update on pediatric allergic rhinitis: narrative review based on guideline updates.",
            "This article summarizes several clinical guidelines.",
        )
        assert ordinary_review_level == "review", ordinary_review_level
        row_id, created = upsert_raw_document(pubmed_doc)
        assert created, (row_id, created)
        imported_search = search_evidence("validationrhinitisendoscopytoken", scope="raw", limit=10)
        assert any(item["document_id"] == row_id for item in imported_search["results"]), imported_search

        unrelated_doc = dict(pubmed_doc)
        unrelated_doc["title"] = "Mouse model study in chronic sinusitis"
        unrelated_doc["content_summary"] = "This murine cell line study does not mention allergic rhinitis."
        unrelated_doc["topic_tags"] = ["PubMed", "paper"]
        unrelated_doc["evidence_level"] = "paper"
        unrelated_doc["raw_payload"] = {
            "publication_types": ["Journal Article"],
            "mesh_terms": ["Animals"],
            "has_abstract": True,
            "abstract_length": 67,
        }
        accepted, reason = _screen_pubmed_document(unrelated_doc, "pubmed_intranasal_steroid_ar")
        assert not accepted and reason in {"not_allergic_rhinitis", "animal_only", "basic_science_only"}, (accepted, reason)

        from fastapi.testclient import TestClient

        from app.main import app

        with TestClient(app) as client:
            evidence_page = client.get("/rhinitis-evidence")
            assert evidence_page.status_code == 200, evidence_page.text
            assert "鼻敏智诊证据检索" in evidence_page.text, evidence_page.text
            assert 'id="evidenceSearchForm"' in evidence_page.text, evidence_page.text
            assert 'id="reviewQueueResults"' not in evidence_page.text, evidence_page.text
            assert "来源桶" not in evidence_page.text, evidence_page.text
            assert "导入批次" not in evidence_page.text, evidence_page.text

            review_page = client.get("/rhinitis-review")
            assert review_page.status_code == 200, review_page.text
            assert "鼻敏智诊证据审核" in review_page.text, review_page.text
            assert 'id="reviewQueueResults"' in review_page.text, review_page.text
            assert 'id="evidenceSearchForm"' not in review_page.text, review_page.text
            assert "来源桶" not in review_page.text, review_page.text
            assert "导入批次" not in review_page.text, review_page.text

            demo_page = client.get("/rhinitis-demo")
            assert demo_page.status_code == 200, demo_page.text
            assert "鼻敏智诊病例摘要 Demo" in demo_page.text, demo_page.text
            assert 'id="demoForm"' in demo_page.text, demo_page.text
            assert 'role="tablist"' in demo_page.text, demo_page.text
            assert "function evidenceHtml" not in demo_page.text, demo_page.text

            sample_case = client.get("/api/rhinitis/demo/sample-case")
            assert sample_case.status_code == 200, sample_case.text
            assert sample_case.json()["case"]["main_symptoms"], sample_case.json()

            demo_summary = client.post("/api/rhinitis/demo/summary", json={"case": sample_case.json()["case"]})
            assert demo_summary.status_code == 200, demo_summary.text
            demo_payload = demo_summary.json()
            assert demo_payload["doctor_summary"]["sections"], demo_payload
            assert demo_payload["patient_education"]["paragraphs"], demo_payload
            assert demo_payload["digital_human_script"]["script"], demo_payload
            assert demo_payload["retrieval"]["scope"] == "curated", demo_payload
            assert demo_payload["citation_record_count"] >= 1, demo_payload
            ref_to_key = {}
            key_to_ref = {}
            for evidence_items in demo_payload["evidence"].values():
                for item in evidence_items:
                    ref = item["ref"]
                    key = (item["document_id"], item["chunk_id"])
                    assert ref.startswith("R"), item
                    if ref in ref_to_key:
                        assert ref_to_key[ref] == key, (ref, ref_to_key[ref], key)
                    if key in key_to_ref:
                        assert key_to_ref[key] == ref, (key, key_to_ref[key], ref)
                    ref_to_key[ref] = key
                    key_to_ref[key] = ref
            assert demo_payload["retrieval"]["unique_evidence_count"] == len(key_to_ref), demo_payload["retrieval"]
            stored_citations = list_answer_citations(demo_payload["output_id"])
            assert len(stored_citations) == demo_payload["citation_record_count"], stored_citations
            assert {"doctor_summary", "patient_education", "digital_human_script"} <= {
                item["output_type"] for item in stored_citations
            }, stored_citations

        ai_batch = export_batch(limit=2, status="needs_review", output_dir=Path(tmpdir) / "rhinitis_ai_review")
        batch_dir = Path(ai_batch["batch_dir"])
        assert (batch_dir / "manifest.json").exists(), ai_batch
        assert ai_batch["manifest"]["document_count"] == 2, ai_batch["manifest"]
        assert len(list((batch_dir / "candidates").glob("*.md"))) == 2, batch_dir
        ai_review = review_batch(batch=batch_dir, model="mock-gpt-5.5", mock=True)
        assert ai_review["reviewed_count"] == 2, ai_review
        assert len(list((batch_dir / "reviews").glob("*.review.json"))) == 2, batch_dir
        ai_apply = apply_batch(batch=batch_dir, promote_doctor_only=True, dry_run=True)
        assert ai_apply["dry_run"], ai_apply
        assert ai_apply["total_reviews"] == 2, ai_apply
        assert ai_apply["actions"], ai_apply

        snapshot_path = Path(tmpdir) / "rhinitis_curated_evidence.json"
        snapshot_export = export_curated_snapshot(snapshot_path)
        assert snapshot_path.exists(), snapshot_export
        assert snapshot_export["document_count"] >= stats["curated_documents"], snapshot_export
        snapshot_meta = snapshot_stats(snapshot_path)
        assert snapshot_meta["document_count"] == snapshot_export["document_count"], snapshot_meta

        original_db_path = settings.rhinitis_evidence_db_path
        try:
            settings.rhinitis_evidence_db_path = str(Path(tmpdir) / "snapshot_import.db")
            imported = import_curated_snapshot(snapshot_path)
            assert imported["document_count"] == snapshot_export["document_count"], imported
            assert imported["created_count"] + imported["updated_count"] == imported["document_count"], imported
            imported_stats = evidence_stats()
            assert imported_stats["curated_documents"] >= snapshot_export["document_count"], imported_stats
        finally:
            settings.rhinitis_evidence_db_path = original_db_path

    print("rhinitis_evidence ok")


if __name__ == "__main__":
    main()
