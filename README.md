# MedFlow 医疗数字人项目

MedFlow 是杭州 MedFlow 智能科技工作室的医疗 AI 信息化展示项目。当前仓库包含工作室官网、耳鼻喉专病 AI 子页面和医疗数字人问诊页面。

## 当前主链路

数字人页面已经重构为豆包端到端实时语音单链路：

```text
浏览器麦克风 PCM 16k
  -> FastAPI /ws/doubao/realtime
  -> 豆包端到端实时语音 ASR
  -> 后端问诊状态机 + 本地医疗资料库检索
  -> 豆包 ChatRAGText / ChatTextQuery 生成回复
  -> 豆包 TTS PCM 24k
  -> 浏览器 Web Audio 播放
```

前端只暴露当前豆包实时语音方案，生产环境不提供公网后台。

## 页面

- `/`：MedFlow 工作室官网
- `/hospital-ai`：医疗数字人实时语音问诊页
- `/rhinitis-ai`：耳鼻喉专病 AI 分支页面
- `/rhinitis-demo`：鼻敏智诊病例摘要 Demo
- `/rhinitis-evidence`：鼻敏智诊证据检索页
- `/rhinitis-review`：鼻敏智诊候选证据审核页

## 核心目录

- `app/main.py`：FastAPI 路由、豆包 WebSocket 代理、公开运行状态接口
- `app/doubao_realtime.py`：豆包 RealtimeAPI v3 帧协议、鉴权头、StartSession 配置
- `app/consultation_flow.py`：耳鼻喉问诊状态机、每轮人设更新、外部 RAG 组织
- `app/rhinitis_evidence.py`：鼻敏智诊候选库 / 精选证据库、FTS5 检索、审核晋级
- `app/rhinitis_demo.py`：鼻敏智诊固定病例输入、精选证据检索、医生摘要/宣教/数字人口播 Demo
- `app/knowledge.py`：本地 Markdown + SQLite 医生资料检索
- `app/static/user.js`：数字人页面豆包实时语音前端
- `knowledge/`：医生资料、FAQ、问诊流程和表达风格资料
- `knowledge/rhinitis_seed_sources.yaml`：鼻敏智诊第一批种子证据和术语别名
- `docs/DOUBAO_REALTIME_V2.md`：豆包实时语音接入说明
- `docs/RHINITIS_EVIDENCE_LIBRARY.md`：鼻敏智诊证据库设计
- `docs/RHINITIS_DATABASE_PROGRESS.md`：鼻敏智诊多源候选库当前进度

## 环境变量

复制 `.env.example` 为 `.env` 后配置：

```bash
DOUBAO_REALTIME_API_KEY=你的豆包语音APIKey
```

主要可调项：

- `DOUBAO_REALTIME_BOT_NAME`：基础人设名称，O/O2.0 模型支持。
- `DOUBAO_REALTIME_SYSTEM_ROLE`：背景人设。
- `DOUBAO_REALTIME_SPEAKING_STYLE`：对话风格。
- `DOUBAO_REALTIME_OPENING_REMARK`：会话建立后通过 `SayHello` 发送的开场白。
- `DOUBAO_REALTIME_SPEAKER`：豆包音色，默认 `zh_male_yunzhou_jupiter_bigtts`。
- `DOUBAO_REALTIME_ENABLE_WEBSEARCH`：内置联网搜索开关，医疗场景默认关闭。
- `DOUBAO_REALTIME_HOTWORDS`：耳鼻喉相关 ASR 热词。
- `RHINITIS_EVIDENCE_DB_PATH`：鼻敏智诊证据库路径，默认 `data/rhinitis_evidence.db`。
- `RHINITIS_EVIDENCE_REVIEW_ENABLED`：是否开放证据审核写接口，生产默认关闭。
- `RHINITIS_EVIDENCE_SEED_SNAPSHOT_ENABLED`：启动时是否导入 `knowledge/rhinitis_curated_evidence.json` 精选证据快照，默认开启。

## 本地运行

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

打开：

```text
http://127.0.0.1:8001/
http://127.0.0.1:8001/hospital-ai
http://127.0.0.1:8001/rhinitis-ai
http://127.0.0.1:8001/rhinitis-demo
http://127.0.0.1:8001/rhinitis-evidence
http://127.0.0.1:8001/rhinitis-review
```

## 验证

```bash
npm ci
python -m compileall app scripts/validate_doubao_realtime.py scripts/validate_doubao_cloud.py
node --check app/static/user.js
npm run validate:consultation-flow
npm run validate:rhinitis-evidence
npm run validate:doubao-realtime
npm run validate:doubao-cloud
npm run validate:user
```

鼻敏智诊证据库初始化和公开 API 候选量级统计：

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

PubMed 导入默认是“筛选后入库”：先用分桶 query 在源头缩小范围，再在导入时跳过明显无关、动物/基础实验为主、低价值 publication type、缺摘要的主题桶结果。`--max-results` 是每个 query 的拉取上限，`0` 表示使用该桶默认上限；`--no-screen` 只用于调试，不建议生产导入使用。筛选规则变化后，先用 `--rescreen-pubmed` 预览，再用 `--apply-rescreen` 更新旧候选的桶、证据等级和审核状态。

多源导入当前策略：

- `--import-seed-sources`：抓取 `knowledge/rhinitis_seed_sources.yaml` 中公开 URL 的标题、meta description 和正文样本，写入独立 `seedfetch:*` 候选，避免覆盖人工种子。
- `--import-europe-pmc`：导入 Europe PMC 题录、摘要、PMID/PMCID/DOI、开放获取标记；按 PMID/DOI 去重，不抓全文。
- `--import-clinical-trials`：导入 ClinicalTrials.gov 研究登记，统一作为 `trial_registry` 候选证据。
- `--import-dailymed`：导入 DailyMed SPL 药品标签候选；按鼻喷/抗组胺/白三烯相关标题筛选，默认不进入患者端。
- `--enrich-openalex`：只补全已有 DOI 文档的 OpenAlex 引用量和开放获取状态，不直接把 OpenAlex 搜索结果导入 RAG。

本地当前候选库进度：`raw_documents=1266`，`curated_documents=86`；来源前缀约为 `pubmed=761`、`europepmc=184`、`clinicaltrials=184`、`dailymed=114`、`seed=13`、`seedfetch=10`。`data/rhinitis_evidence.db` 是运行态文件，不提交到 Git。

鼻敏智诊 AI 证据预审：

```bash
.venv/bin/python scripts/rhinitis_ai_review.py export --status needs_review --limit 900 --max-chars-per-doc 12000
.venv/bin/python scripts/rhinitis_ai_review.py export --status candidate --limit 400 --max-chars-per-doc 10000
.venv/bin/python scripts/rhinitis_ai_review.py review --batch latest --model gpt-5.5
.venv/bin/python scripts/rhinitis_ai_review.py apply --batch latest
.venv/bin/python scripts/rhinitis_ai_review.py apply --batch latest --promote-doctor-only --write
```

`export` 会把 SQLite 中的候选资料整理成 Markdown 证据包，放在 `data/rhinitis_ai_review/batches/`。`apply` 默认只是 dry-run；只有带 `--write` 才会回写数据库。AI 推荐晋级时第一版只开放医生端演示，默认 `patient_visible=false`。

鼻敏智诊精选证据快照：

```bash
.venv/bin/python scripts/rhinitis_evidence_snapshot.py export
.venv/bin/python scripts/rhinitis_evidence_snapshot.py stats
.venv/bin/python scripts/rhinitis_evidence_snapshot.py import
```

`data/rhinitis_evidence.db` 不提交到 Git；`knowledge/rhinitis_curated_evidence.json` 用来把本地已审核的精选证据带到线上。部署流程会显式导入一次，应用启动时也会自动补种一次，导入按 `source_key` 幂等更新。

鼻敏智诊病例 Demo：

```bash
curl -s http://127.0.0.1:8001/api/rhinitis/demo/sample-case
curl -s http://127.0.0.1:8001/api/rhinitis/demo/summary \
  -H 'Content-Type: application/json' \
  -d '{"case":{"age_group":"成人","main_symptoms":["鼻塞","喷嚏","流涕","鼻痒"],"duration":"反复3年，本次2周","seasonality":"春秋季加重","triggers":["花粉","冷空气"],"medication_history":"间断口服抗组胺药","allergen_tests":"尘螨和蒿草花粉 IgE 阳性","nasal_endoscopy":"鼻黏膜苍白水肿，下鼻甲肿胀","comorbidities":["偶有咳嗽"],"patient_goal":"希望明确评估和治疗方向"}}'
```

Demo 只检索 `approved` 精选证据；医生摘要、患者宣教和数字人口播都会写入 `answer_citations`，用于追溯引用过的证据片段。

## 豆包官方配置口径

当前接入对齐火山引擎「端到端实时语音大模型API接入文档」：

- `StartSession` 传 `tts.speaker`、`tts.audio_config`、`asr.extra`、`dialog.bot_name/system_role/speaking_style/extra`。
- O2.0 使用模型版本 `1.2.1.1`，支持 `bot_name`、`system_role`、`speaking_style` 和精品音色。
- 外部资料通过 `ChatRAGText` 发送，`external_rag` 控制在 4K 字符以内。
- 文本输入通过 `ChatTextQuery`；麦克风输入采用 `TaskRequest` 发送 16k 单声道 PCM。
- 会话期间用 `UpdateConfig` 动态更新问诊阶段的人设和回答约束。
- 内置联网搜索对应 `enable_volc_websearch` 等字段，但当前医疗项目默认关闭，优先使用本地医生资料库。

官方文档：<https://www.volcengine.com/docs/6561/1594356?lang=zh>
