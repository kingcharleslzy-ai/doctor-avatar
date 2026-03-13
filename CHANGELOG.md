# Changelog

## [Unreleased]

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
