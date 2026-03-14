# Changelog

## [Unreleased]

### 2026-03-14 — 语音识别重构 + 回复精简（windows-claude，commit 86c8edd）

**改动文件：**
- `app/config.py`：新增 `STT_API_KEY` 配置项，语音识别用独立 OpenAI key
- `app/main.py`：新增 `/api/stt` 端点，接收音频文件发给 OpenAI Whisper 转写
- `app/static/user.js`：废弃 Web Speech API，改用 MediaRecorder 录音 + 服务端 Whisper 转写（兼容 iOS Safari / Android / 桌面全平台）
- `app/prompts.py`：去掉每次回复的自我介绍和末尾免责声明，改为简洁直接回答

**为什么：**
- Web Speech API 在 iOS Safari 完全不支持，Android 不稳定，桌面端只能识别一句就停
- 改用 MediaRecorder + Whisper 方案全平台兼容，识别质量更好
- AI 回复去掉废话（自我介绍 + 免责声明），用户体验更好，也减少 Ditto 视频生成的文本量

**部署：** 服务器 .env 新增 `STT_API_KEY=<OpenAI key>`（聊天继续走 DeepSeek）

---

### 2026-03-14 — Ditto 视频+TTS 语音系统接入（windows-claude）

**改动文件：**
- `requirements.txt`：新增 `edge-tts>=7.0,<8`
- `app/config.py`：新增三个环境变量字段 `DITTO_SERVICE_URL`、`ENABLE_DITTO_VIDEO`、`TTS_VOICE`
- `app/models.py`：新增 `TTSRequest`、`DittoGenerateRequest` 请求模型
- `app/main.py`：新增 `/api/tts`（edge-tts 合成音频）和 `/api/ditto/generate`（转发音频到 Ditto 服务生成 MP4）两个端点；`/api/app-config` 新增 `ditto_enabled` 字段
- `app/static/user.js`：
  - `speakAnswer()` 从浏览器 `SpeechSynthesis` 升级为调用 `/api/tts`，Audio 对象播放
  - 新增 `generateDittoVideo(text)` 函数：调用 `/api/ditto/generate`，在 `#videoStage` 播放 MP4，播完自动恢复医生照片
  - `askQuestion()` 在拿到回答后，若 `config.ditto_enabled` 为 true，自动触发 `generateDittoVideo`

**为什么：**
目标是实现「患者提问 → DeepSeek 回答 → edge-tts 语音播报 + Ditto 视频生成」全链路。Ditto 服务运行在 4090D GPU 服务器 `127.0.0.1:8001`，通过反向 SSH 隧道透传到 ECS。

**部署激活方式：**
在服务器 `.env` 添加：
```
ENABLE_DITTO_VIDEO=true
DITTO_SERVICE_URL=http://127.0.0.1:8001
TTS_VOICE=zh-CN-XiaoxiaoNeural
```

---

## 2026-03-14 — 替换 SVG 占位为真实医生照片（windows-claude，commit c96ed5f）

- `app/static/user.js`：`desktopPlaceholderMarkup` / `mobilePlaceholderMarkup` 改为真实 PNG
- `app/static/doctor-photo-desktop.png`：GPT 生成专业医生照片（桌面横版）
- `app/static/doctor-photo-mobile.png`：GPT 生成专业医生照片（移动竖版）

---

## 2026-03-14 — DeepSeek API 接入（windows-claude，commit e9e4b1e）

- `app/services.py`：`responses.create` → `chat.completions.create`，兼容所有 OpenAI 兼容接口
- 服务器 `.env`：已更新 `OPENAI_API_KEY`、`OPENAI_BASE_URL=https://api.deepseek.com`、`OPENAI_MODEL=deepseek-chat`

---

## 2026-03-14 — ops 统计修复 + 单 worker（codex，commit 021c1bf）

- `app/ops.py`：兼容 `prompt_tokens`/`completion_tokens`（DeepSeek 口径）
- `deploy/docker-compose.yml`：uvicorn 改为 `--workers 1` 防止进程内统计漂移
- `README.md`：移除真实 DeepSeek API key（改回占位符）
