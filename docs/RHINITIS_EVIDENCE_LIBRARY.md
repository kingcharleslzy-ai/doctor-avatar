# 鼻敏智诊证据库设计

本文记录鼻敏智诊第一版数据库底座。目标不是训练模型，而是把过敏性鼻炎相关资料变成可检索、可审核、可引用的专病证据资产。

## 1. 两层库

系统分为两层：

- `raw_candidates`：全量候选库。尽量多抓公开资料，允许噪音，供筛选、研究、医生审核使用。
- `curated_evidence`：精选证据库。只放 `approved` 内容，供患者宣教、医生摘要和数字人脚本使用。

默认规则：

- `approved` 可以进入患者端和医生端生成。
- `candidate`、`needs_review` 只进入研究端检索。
- `rejected`、`deprecated` 不进入任何生成链路。

## 2. 来源桶

候选库分 7 个来源桶：

- `guideline_candidates`：中外指南、共识、临床路径。
- `literature_candidates`：PubMed、PMC、Europe PMC、OpenAlex、中文文献题录。
- `drug_candidates`：DailyMed、openFDA、NMPA/CDE/第三方药品说明书。
- `hospital_education_candidates`：三甲医院宣教、科普、手册。
- `environment_candidates`：花粉浓度、季节、空气质量、地区暴露。
- `trial_candidates`：ClinicalTrials.gov、ChiCTR、药物临床试验登记。
- `doctor_material_candidates`：医生问诊路径、摘要模板、宣教模板、审核意见。

## 3. Schema

数据库文件默认在 `data/rhinitis_evidence.db`，由 `app/rhinitis_evidence.py` 初始化。核心表：

- `raw_documents` / `raw_chunks`：候选资料和分段。
- `curated_documents` / `curated_chunks`：精选资料和分段。
- `aliases`：中英文症状、药品、检查、疾病同义词。
- `review_notes`：医生审核、修订、禁用原因。
- `import_runs`：每次抓取来源、查询词、数量、时间。
- `answer_citations`：生成结果引用的证据片段。

FTS5 表：

- `raw_chunks_fts`
- `curated_chunks_fts`

FTS 只用于检索排序，不替代审核状态判断。

## 4. 证据等级

排序权重优先级：

```text
指南/共识 > 临床路径 > 系统综述/Meta > RCT > 药品标签 > 医院宣教 > 普通综述/网页 > 试验登记/环境数据
```

第一版使用手工权重，不接向量数据库。检索排序由以下因素组成：

- FTS/LIKE 命中。
- 证据等级权重。
- 审核状态权重。
- 场景匹配，例如 `patient_education` 或 `doctor_summary`。
- alias 扩展，例如“辅舒良”会扩展到 `fluticasone`、`氟替卡松`、`鼻喷激素`。

## 5. 抓取策略

第一版脚本 `scripts/rhinitis_evidence_import.py` 支持：

- 初始化数据库和种子源。
- 通过公开 API 抓取候选量级统计并写入 `import_runs`。
- 批量导入 PubMed 题录、摘要、PMID、DOI、PMCID、期刊、年份、Publication Type、MeSH 和作者信息。
- 抓取 `knowledge/rhinitis_seed_sources.yaml` 中公开 URL 的标题、描述和正文样本，写入独立 `seedfetch:*` 候选。
- 批量导入 Europe PMC 题录、摘要、开放获取标记和 PMID/PMCID/DOI。
- 批量导入 ClinicalTrials.gov 研究登记，作为 `trial_registry` 候选。
- 批量导入 DailyMed SPL 药品标签候选，按鼻喷、抗组胺、白三烯相关标题筛选。
- 使用 OpenAlex 按 DOI 补全引用量和开放获取状态，只写入 `raw_payload.openalex`，不直接生成 RAG 证据。

当前自动统计 / 导入：

- PubMed / PMC：题录、摘要、PMID、MeSH、年份、期刊。
- Europe PMC：题录、摘要、开放获取和全文候选标记。
- ClinicalTrials.gov：研究登记、状态、干预、适应症。
- DailyMed：目标药物标签候选。
- openFDA：当前只做数量统计，不直接导入，原因是噪音和重复较高。
- OpenAlex：DOI、引用量、开放获取状态补全，不直接进 RAG。

国内资料第一版半自动：

- `knowledge/rhinitis_seed_sources.yaml` 维护指南、三甲医院宣教、卫健委、花粉和药品说明书入口。
- 中文文献库先记录题录、摘要、URL、期刊、年份，不强制抓全文。

常用命令：

```bash
.venv/bin/python scripts/rhinitis_evidence_import.py
.venv/bin/python scripts/rhinitis_evidence_import.py --fetch-counts
.venv/bin/python scripts/rhinitis_evidence_import.py --import-pubmed-plan priority
.venv/bin/python scripts/rhinitis_evidence_import.py --import-pubmed --pubmed-query pubmed_guideline_consensus
.venv/bin/python scripts/rhinitis_evidence_import.py --import-seed-sources
.venv/bin/python scripts/rhinitis_evidence_import.py --import-europe-pmc
.venv/bin/python scripts/rhinitis_evidence_import.py --import-clinical-trials
.venv/bin/python scripts/rhinitis_evidence_import.py --import-dailymed
.venv/bin/python scripts/rhinitis_evidence_import.py --enrich-openalex
.venv/bin/python scripts/rhinitis_evidence_import.py --report-imports
.venv/bin/python scripts/rhinitis_evidence_import.py --rescreen-pubmed
.venv/bin/python scripts/rhinitis_evidence_import.py --rescreen-pubmed --apply-rescreen
```

PubMed 不做“全量先落本地”。导入默认使用筛选流程：

1. 源头 query 先按指南/共识、系统综述/Meta、RCT、免疫治疗、鼻内镜、儿童、鼻喷激素、抗组胺、合并哮喘、花粉环境等桶缩小范围。
2. 导入时再跳过明显无关、动物/基础实验为主、低价值 publication type、缺摘要的主题桶结果。
3. 每条记录用 `pubmed:{PMID}` 去重；通过准入的候选资料才写入 `raw_documents`。
4. `import_runs.metadata_json` 记录 `eligible_count`、`updated_count`、`skipped_count`、`skip_reasons` 和 PubMed 原始命中数。
5. 筛选规则变更后，`--rescreen-pubmed` 会按当前规则重扫已入库 PubMed 候选；默认 dry-run，带 `--apply-rescreen` 才会更新旧候选的来源桶、证据等级、标签和审核状态。

因此 `raw_candidates` 是“已筛候选库”，不是把 PubMed 总量全量复制到本地。高证据等级或关键主题自动进入 `needs_review`，普通低优先级文献默认不入库。

本轮多源导入后的本地运行态统计：

- `raw_documents=1266`
- `curated_documents=86`
- 来源前缀：`pubmed=761`、`europepmc=184`、`clinicaltrials=184`、`dailymed=114`、`seed=13`、`seedfetch=10`
- 来源桶：`literature_candidates=752`、`trial_candidates=184`、`drug_candidates=116`、`guideline_candidates=115`、`environment_candidates=91`、`hospital_education_candidates=6`、`doctor_material_candidates=2`

已知限制：

- `seed_sources.yaml` 中国家卫健委主页当前对脚本请求返回 `HTTP 412`，不硬绕；保留人工种子，后续应补具体临床路径 URL。
- DailyMed 当前导入 SPL 列表元数据和候选摘要，未抓完整标签正文；进入患者端前仍需审核具体商品、剂型和标签版本。
- Europe PMC 当前导入题录和摘要，不抓全文。
- ClinicalTrials.gov 只作为研究登记候选，不作为患者宣教或治疗推荐依据。

## 6. 晋级流程

抓取资料默认进入 `candidate` 或 `needs_review`。

晋级步骤：

1. 自动打标签：指南、药品、检查、鼻内镜、免疫治疗、花粉、儿童、孕妇、合并哮喘。
2. 自动打初始证据等级。
3. 去重：PMID、DOI、URL、source key。
4. AI 证据预审 agent 先审，输出结构化 JSON 和可抽查 Markdown。
5. AI 推荐晋级的资料可通过 `scripts/rhinitis_ai_review.py apply --promote-doctor-only --write` 标记为 `approved`。
6. 系统把 raw document 晋级到 curated evidence，但第一版默认 `patient_visible=false`，只服务医生端演示。
7. 高风险或不确定资料保留 `needs_review`，后续再做人工抽查。

## 7. 精选库部署快照

`data/rhinitis_evidence.db` 是本地/线上运行态 SQLite 文件，不提交到 Git。为了让线上部署拿到本地已审核的精选证据，系统使用可提交的 JSON 快照：

- 快照文件：`knowledge/rhinitis_curated_evidence.json`
- 导出命令：`.venv/bin/python scripts/rhinitis_evidence_snapshot.py export`
- 导入命令：`.venv/bin/python scripts/rhinitis_evidence_snapshot.py import`
- 查看快照：`.venv/bin/python scripts/rhinitis_evidence_snapshot.py stats`

快照只保存 `approved` 精选证据及其分段，导入时会用 `source_key` 幂等 upsert 到 `raw_documents`，再通过同一套晋级逻辑生成 `curated_documents`。导入不会删除线上已有候选资料，也不会绕过审核状态规则。

应用启动时会自动导入 `knowledge/rhinitis_curated_evidence.json`，GitHub Actions 部署流程也会显式执行一次导入作为双保险。可以用 `RHINITIS_EVIDENCE_SEED_SNAPSHOT_ENABLED=false` 关闭启动时自动 seed。

## 8. 病例 Demo 生成链路

第一版产品原型使用固定病例输入结构，不接新模型：

- 页面：`/rhinitis-demo`
- 示例病例：`GET /api/rhinitis/demo/sample-case`
- 生成摘要：`POST /api/rhinitis/demo/summary`

输入字段包括人群、主要症状、病程、季节性、诱因、用药史、过敏原/IgE、鼻内镜、合并情况和患者目标。后端根据病例生成检索词，只检索 `curated` 范围的 `approved` 证据。

输出分三类：

- `doctor_summary`：给医生看的病史整理、检查线索和待补充问题。
- `patient_education`：低风险通俗宣教，优先使用 `patient_visible=true` 的精选证据。
- `digital_human_script`：适合李勇医生数字人口播的短脚本。

每次生成会使用同一个 `output_id`，并把三类输出引用过的 curated chunk 写入 `answer_citations`。这一步用于证明精选证据库不仅能搜索，还能支撑医生摘要、患者宣教和数字人脚本的可追溯生成。

患者端和医生端只读 curated evidence。

`/rhinitis-review` 审核页需要填写审核人和审核备注，并选择 `doctor_visible`、`patient_visible` 可用范围。单条审核和批量审核都会写入 `review_notes`，详情抽屉可追溯查看。

当前优先路线不是让医生逐条审核，而是先走 AI 证据预审：

```bash
.venv/bin/python scripts/rhinitis_ai_review.py export --limit 20
.venv/bin/python scripts/rhinitis_ai_review.py review --batch latest --model gpt-5.5
.venv/bin/python scripts/rhinitis_ai_review.py apply --batch latest
.venv/bin/python scripts/rhinitis_ai_review.py apply --batch latest --promote-doctor-only --write
```

AI 预审不是医生终审；所有 AI 结论写入 `review_notes`，reviewer 使用 `ai:{model}:rhinitis_evidence_reviewer_v1`。

## 7. API

第一版 API：

- `GET /api/rhinitis/evidence/stats`
- `GET /api/rhinitis/evidence/search?q=...&scope=raw|curated&source_bucket=environment_candidates`
- `GET /api/rhinitis/evidence/review-queue?status=needs_review&source_bucket=guideline_candidates`
- `GET /api/rhinitis/evidence/review-pack`
- `GET /api/rhinitis/evidence/documents/{id}?scope=raw|curated`
- `POST /api/rhinitis/evidence/review`
- `POST /api/rhinitis/evidence/review-batch`

`scope=curated` 是默认安全检索范围。`scope=raw` 用于研究和审核，不应直接用于患者宣教。

审核队列和精选包候选接口只读；审核写接口和批量审核写接口由 `RHINITIS_EVIDENCE_REVIEW_ENABLED` 控制，默认关闭，避免生产公网被写入。

页面入口：

- `/rhinitis-ai`：鼻敏智诊产品介绍页，只保留证据库摘要和检索 / 审核入口。
- `/rhinitis-evidence`：证据检索页，只放统计、检索结果和证据详情。
- `/rhinitis-review`：候选证据审核页，只放审核设置、审核队列、精选证据包候选和证据详情。

## 8. 输出边界

患者端：

- 通俗解释、就医准备、诱因记录、检查说明。
- 不输出确定诊断、处方剂量或个体化治疗承诺。

医生端：

- 主诉、现病史、诱因、既往检查、用药线索、待确认问题。
- 可以显示证据引用和审核状态。

研究端：

- PMID、PMCID、DOI、URL、来源桶、证据等级、导入批次。
- 可以查看 `candidate` 和 `needs_review`。

鼻内镜图像：

- 第一版只做观察字段和术语库。
- 不做自动诊断，不输出“图像诊断结论”。
