# 鼻敏智诊数据库进度

更新时间：2026-06-08

## 当前结论

数据库路线已经从单一 PubMed 候选库扩展为多源候选库。当前仍坚持“两层库”原则：

- `raw_documents`：大范围候选库，允许噪音，供 AI 预审和研究端检索。
- `curated_documents`：精选证据库，只放 approved 内容，供病例 Demo、患者宣教和数字人脚本使用。

## 本地运行态统计

- raw candidates：1266
- curated evidence：86
- approved：86
- needs_review：827
- candidate：349
- rejected/deprecated：4

按来源前缀：

- PubMed：761
- Europe PMC：184
- ClinicalTrials.gov：184
- DailyMed：114
- YAML seed：13
- seed URL fetch：10

按来源桶：

- literature_candidates：752
- trial_candidates：184
- drug_candidates：116
- guideline_candidates：115
- environment_candidates：91
- hospital_education_candidates：6
- doctor_material_candidates：2

## 已实现导入链路

1. PubMed：筛选后导入，保留 PMID、DOI、摘要、Publication Type、MeSH、作者、证据等级和主题标签。
2. seed sources：从 `knowledge/rhinitis_seed_sources.yaml` 抓公开 URL 标题、描述和正文样本，写入独立 `seedfetch:*` 候选。
3. Europe PMC：导入题录、摘要、PMID、PMCID、DOI、开放获取标记；按 PMID/DOI 去重。
4. ClinicalTrials.gov：导入研究登记、状态、条件、干预、阶段和 sponsor，统一作为 `trial_registry` 候选。
5. DailyMed：导入目标药物 SPL 标签候选，按鼻喷、抗组胺、白三烯相关标题筛选。
6. OpenAlex：按 DOI 补引用量、OA 状态和 OpenAlex ID，只做元数据 enrichment。

## 已知限制

- 国家卫健委主页对脚本请求返回 HTTP 412，本轮不硬绕；后续应补具体临床路径页面或 PDF 入口。
- Europe PMC 当前不抓全文，只抓题录和摘要。
- DailyMed 当前不抓完整标签正文，只保留 SPL 标签候选、setid、标题、发布日期和 URL。
- ClinicalTrials.gov 只作为研究端候选，不进入患者宣教和治疗建议。
- openFDA 仍只做数量统计，不直接导入，原因是噪音和重复较高。

## 下一步

1. 用 AI 证据预审处理新增的 `needs_review` 队列，先从指南、药品标签、医院宣教和免疫治疗研究开始。
2. 为国内资料补更具体的三甲医院、卫健委、花粉监测页面 URL。
3. 对 DailyMed 增加完整 SPL 文本提取，但仍只进入候选库。
4. 做一次 curated evidence 晋级，把新增多源候选中最稳的 30-60 条补进精选库。
