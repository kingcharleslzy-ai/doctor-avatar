# 鼻敏智诊 AI 证据预审 Agent

本文定义鼻敏智诊第一版 AI 证据预审流程。目标是降低医生逐条审核工作量，把候选资料先整理成大模型易读的 Markdown 证据包，再由 GPT-5.5 按固定 rubric 给出预审意见。

## 定位

AI 预审 agent 不是医生终审。

- 可以用于研究演示、医生端摘要原型、证据库初筛。
- 不把 AI 预审写成“医生已审核”。
- 患者端默认不可见，除非后续人工确认。
- 所有 AI 结论必须留痕：模型、prompt 版本、decision、confidence、理由、风险标记和原始候选资料。

## 工作流

```bash
.venv/bin/python scripts/rhinitis_ai_review.py export --limit 20
.venv/bin/python scripts/rhinitis_ai_review.py review --batch latest --model gpt-5.5
.venv/bin/python scripts/rhinitis_ai_review.py apply --batch latest
.venv/bin/python scripts/rhinitis_ai_review.py apply --batch latest --promote-doctor-only --write
```

步骤说明：

1. `export`：从 `raw_documents` 取 `needs_review` 候选资料，写成 Markdown。
2. `review`：把 Markdown 交给模型，生成 `review.json` 和 `review.md`。
3. `apply`：默认只 dry-run 汇总，不回写数据库。
4. `--promote-doctor-only --write`：只把 AI 推荐且置信度达标的资料晋级到 curated，且 `patient_visible=false`、`doctor_visible=true`。

## 证据包格式

每个批次放在：

```text
data/rhinitis_ai_review/batches/{batch_id}/
```

核心文件：

- `manifest.json`：批次、筛选条件、候选资料列表。
- `reviewer_prompt.md`：本批次使用的 reviewer rubric。
- `candidates/doc_000037.md`：单条候选资料 Markdown。
- `reviews/doc_000037.review.json`：模型结构化审核结果。
- `reviews/doc_000037.review.md`：便于人工抽查的审核说明。

Markdown 候选资料只做整理，不做复杂医学判断。医学判断交给模型。

## Reviewer Rubric

AI reviewer 应判断：

- 是否确实与过敏性鼻炎、鼻炎诊疗、鼻内镜观察、过敏原检查、免疫治疗、常用药物、儿童/合并哮喘、环境诱因相关。
- 是否适合进入精选证据库。
- 当前证据等级是否合理。
- 更适合医生摘要、患者宣教、数字人脚本还是研究检索。
- 是否存在药物剂量、儿童、孕妇、禁忌、自动诊断、图像诊断、证据冲突等风险。
- 是否需要人工抽查。

## Decision

- `ai_recommend_curate`：资料相关、可信、可用于医生端演示或后续精选。
- `needs_human_spot_check`：资料可能有价值，但有风险、边界或不确定性，需要抽查。
- `reject`：明显不相关、低价值、基础实验/动物实验为主、无可用临床信息，或摘要不足以支撑专病库使用。

## 回写边界

第一版数据库不新增复杂状态。AI 结论写入 `review_notes`，必要时复用已有晋级逻辑：

- AI 推荐晋级并执行 `--promote-doctor-only`：`review_status=approved`，进入 `curated_documents`，但 `patient_visible=false`。
- AI 建议抽查：保留原状态，只写审核 note。
- AI 建议拒绝：默认不自动驳回；只有显式使用拒绝写入选项时才改成 `rejected`。

这保证原型可以快速形成医生端可用的 curated 小库，同时不把 AI 预审结果直接推给患者端。
