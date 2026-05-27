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

## 核心目录

- `app/main.py`：FastAPI 路由、豆包 WebSocket 代理、公开运行状态接口
- `app/doubao_realtime.py`：豆包 RealtimeAPI v3 帧协议、鉴权头、StartSession 配置
- `app/consultation_flow.py`：耳鼻喉问诊状态机、每轮人设更新、外部 RAG 组织
- `app/knowledge.py`：本地 Markdown + SQLite 医生资料检索
- `app/static/user.js`：数字人页面豆包实时语音前端
- `knowledge/`：医生资料、FAQ、问诊流程和表达风格资料
- `docs/DOUBAO_REALTIME_V2.md`：豆包实时语音接入说明

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
```

## 验证

```bash
npm ci
python -m compileall app scripts/validate_doubao_realtime.py scripts/validate_doubao_cloud.py
node --check app/static/user.js
npm run validate:consultation-flow
npm run validate:doubao-realtime
npm run validate:doubao-cloud
npm run validate:user
```

## 豆包官方配置口径

当前接入对齐火山引擎「端到端实时语音大模型API接入文档」：

- `StartSession` 传 `tts.speaker`、`tts.audio_config`、`asr.extra`、`dialog.bot_name/system_role/speaking_style/extra`。
- O2.0 使用模型版本 `1.2.1.1`，支持 `bot_name`、`system_role`、`speaking_style` 和精品音色。
- 外部资料通过 `ChatRAGText` 发送，`external_rag` 控制在 4K 字符以内。
- 文本输入通过 `ChatTextQuery`；麦克风输入采用 `TaskRequest` 发送 16k 单声道 PCM。
- 会话期间用 `UpdateConfig` 动态更新问诊阶段的人设和回答约束。
- 内置联网搜索对应 `enable_volc_websearch` 等字段，但当前医疗项目默认关闭，优先使用本地医生资料库。

官方文档：<https://www.volcengine.com/docs/6561/1594356?lang=zh>
