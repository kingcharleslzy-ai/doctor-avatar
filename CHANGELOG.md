# Changelog

## [Unreleased]

### 2026-03-16 — 诊断质量优化 + 等待提示（windows-claude）

**改动文件：**
- `app/prompts.py`：诊断阶段从 5-8 句扩展到 8-15 句（300-500 字），要求包含原因分析、调理方法、用药方向、就医条件和挂什么科；强化禁止 AI 免责声明（扩大禁词范围，禁止在结尾加声明）
- `app/services.py`：删除 memory code 回复中的"仅供健康科普"声明
- `app/static/user.js`：等待首个 token 超过 3 秒时显示"医生正在给出诊断意见，请稍等……"

**为什么：**
- 用户测试发现：AI 会在对话中途插入"我是AI助手，只是提供建议"，最终诊断只有两三句话太敷衍
- 测试版不需要免责声明，诊断结果应该像真医生一样详细有价值
- 诊断内容变长后响应时间增加，需要给用户等待反馈

---

### 2026-03-16 — 全双工语音探索与回退（windows-claude，commits 1f5cf46..ab12649）

**改动文件：**
- `app/static/user.js`：尝试了 AI 说话时持续录音+打断功能，最终回退

**为什么：**
- 尝试全双工：AI 说话时同时录音，检测到用户说话就打断 AI → VAD 在静音时误触发导致死循环
- 尝试只录不打断：AI 说话时开始录音但不打断 → VAD idle timeout 在用户还没说话时触发空提交 → 无限循环
- 最终回退到顺序流程（AI 说完 → 开始录音），保留持久化麦克风流避免重新初始化延迟

---

### 2026-03-16 — 代码审计 + 语音优化（windows-claude，commits bce4434..1ff7caf，tag: stable-v2026-03-16）

**审计修复 7 项：**
- `app/main.py`：修 httpx import 缺失、stt.py NameError、lifespan handler 迁移
- `deploy/nginx/default.conf`：SSE 关闭 buffering、安全头（HSTS/nosniff/DENY）、gzip 压缩（~44% 节省）
- `app/static/user.js`：修 connDot 逻辑 bug、AudioContext 页面卸载时清理
- `app/config.py`：移除 db_path 默认值暴露

**语音优化：**
- TTS 改用 YunjianNeural 沉稳男声 +15% 语速
- prompt 调整为电话口语风格
- 麦克风流持久化，消除 500ms 重新初始化延迟

---

### 2026-03-15 — iOS 移动端语音兼容性修复（windows-claude，commits 89b343e..d5d0b9d）

**改动文件：**
- `app/static/user.js`：Safari TTS 从 HTMLAudioElement 改为 Web Audio API（decodeAudioData + AudioBufferSourceNode）
- `app/main.py`：后端 ffmpeg 统一转 16kHz mono WAV 再送 Whisper，不依赖浏览器文件扩展名
- `app/static/user.js`：前端 VAD 无人声时不提交 + 后端过滤 prompt echo + idle timeout 6.5s→15s

**为什么：**
- Safari AudioElement 播放 TTS 无声，Web Audio API 在用户手势解锁后正常
- 夸克/WKWebView STT 发送格式不对，ffmpeg 统一转码解决
- 静音时 Whisper 产生幻觉文本，前后端双重过滤

---

### 2026-03-15 — MiniMax 蓝紫风格重设计（windows-claude，commits ae085e4..da3b300）

**改动文件：**
- `app/templates/user_mobile.html`：完整重写为蓝紫玻璃拟态，视频+聊天合并单张卡片
- `app/templates/user_desktop.html`：同步重设计
- `app/static/user.js`：新增"结束问诊"按钮、inline script 统一移入 user.js、cache-bust 自动刷新

---

### 2026-03-15 — Codex Review 响应（windows-claude，commits ae36200..dd7b36b）

- 采纳 P1-1：新增 `voiceSessionActive` 状态位，文本提问不会意外开麦
- 采纳 P2-3：`stopSpeech()` 改为调 `_stopAllTts()`
- 补全 voiceSessionActive 生命周期：stopSpeech/askBtn/Enter/pill click 四个路径全部设回 false
- 不采纳 P1-2（同步 OpenAI client）：单 worker 场景阻塞可忽略
- `/api/voice-chat` 新增 memory-code 特判

---

### 2026-03-15 — 移动端 SSE 降级修复（windows-claude，commit 62cf290）

- SSE ReadableStream 在部分移动端浏览器不兼容 → 自动降级到 `/api/chat` + `speakAnswer`
- `audio.play()` 拒绝时跳过继续处理，不卡住

---

### 2026-03-15 — 实时语音通话 SSE 流水线（windows-claude，commits 9bc63e7..ee3c9c8）

**改动文件：**
- `app/main.py`：新增 `/api/voice-chat` SSE 端点 + `/api/tts/stream` 流式端点
- `app/static/user.js`：`askQuestion()` 改用 SSE，文字逐 token 显示，音频按句队列播放

**为什么：**
- 原链路：Chat 全部完成(6-9s) → TTS 全部合成(7-17s) → 播放，总延迟 11-20s
- 新方案：DeepSeek 流式 → 按句切分 → 每句即时 Edge TTS → SSE 推送 text+audio
- 结果：首个文字 1.6-3.2s，首段音频 3.1-5.5s，总完成 5.7-7.6s

---

### 2026-03-15 — 阿里云 TTS Ethan 接通（windows-claude，commit 016e885）

- 发现 Codex 之前设的 `Neil` 不是合法 voice，改为 `Ethan`（晨煦，标准普通话）
- 服务器 `DASHSCOPE_API_KEY` 已配置，`docker compose down + up` 重建容器

---

### 2026-03-14 — TTS Provider 统一（codex，commit 0202d78）

- 新增 `app/speech.py`：aliyun/openai/edge 三条 TTS 收为一套服务
- `/api/tts`、Ditto 离线视频、Ditto 流式音频源统一复用
- 未配 DASHSCOPE_API_KEY 时自动回退到 OpenAI

---

### 2026-03-14 — 语音识别重构 + 回复精简（windows-claude，commit 86c8edd）

**改动文件：**
- `app/config.py`：新增 `STT_API_KEY` 配置项，语音识别用独立 OpenAI key
- `app/main.py`：新增 `/api/stt` 端点，接收音频文件发给 OpenAI Whisper 转写
- `app/static/user.js`：废弃 Web Speech API，改用 MediaRecorder 录音 + 服务端 Whisper 转写
- `app/prompts.py`：去掉每次回复的自我介绍和末尾免责声明

**部署：** 服务器 .env 新增 `STT_API_KEY=<OpenAI key>`

---

### 2026-03-14 — Ditto 视频+TTS 语音系统接入（windows-claude）

- `requirements.txt`：新增 `edge-tts>=7.0,<8`
- `app/main.py`：新增 `/api/tts` + `/api/ditto/generate` 端点
- `app/static/user.js`：`speakAnswer()` 升级为服务端 TTS，新增 Ditto 视频生成

---

## 2026-03-14 — 替换 SVG 占位为真实医生照片（windows-claude，commit c96ed5f）

- `app/static/user.js`：改为真实 PNG 医生照片

---

## 2026-03-14 — DeepSeek API 接入（windows-claude，commit e9e4b1e）

- `app/services.py`：`responses.create` → `chat.completions.create`，兼容 OpenAI 兼容接口

---

## 2026-03-14 — ops 统计修复 + 单 worker（codex，commit 021c1bf）

- `app/ops.py`：兼容 DeepSeek token 计数口径
- `deploy/docker-compose.yml`：uvicorn 改为 `--workers 1`
