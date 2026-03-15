# 医生虚拟人 MVP

这是一个新的独立项目，用来搭建你爸的医生虚拟人第一版。

当前版本包含 3 层：

1. `OpenAI` 问答层
2. `本地知识库` 检索层
3. `HeyGen / LiveAvatar + LiveKit` 会话接口层

目标不是一步做到真人级视频通话，而是先把“像你爸说话、守住医疗边界、能逐步接入视频分身”的骨架跑起来。

## 目录

- `app/` FastAPI 应用
- `knowledge/` 医生资料、风格样本、常见问答
- `.env.example` 环境变量模板

## 本地启动

```powershell
cd D:\charles\Documents\doctor-avatar
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)

- 用户端：`/`
- 用户端桌面版：`/desktop`
- 用户端手机版：`/mobile`
- 控制台：`/console`

## 4090D 远程接入（frp）

当前已为“阿里云主站 + 家里 4090D 渲染机”准备了 `frp` 服务通道方案：

- 阿里云服务器运行 `frps`
- 家里 4090D 机器运行 `frpc`
- 默认端口：
  - `7000/tcp`：`frps` 控制通道
  - `6022/tcp`：当前保留给远程接入的映射端口

仓库内文件：

- `deploy/frp/frps.toml`
- `deploy/frp/frps.service`
- `.github/workflows/setup-frps.yml`

注意：

- 真正的 `FRP_AUTH_TOKEN` 不会写进仓库，而是放在 GitHub Secret：
  - `FRP_AUTH_TOKEN`
- 阿里云安全组还需要放行：
  - `7000/tcp`
  - `6022/tcp`

说明：

- 旧的 `6000/tcp` SSH 映射已废弃，不再作为长期入口
- 目前远程 SSH 的主入口统一为下面的 `6022/tcp` 反向隧道
- `frp` 这层后续主要为 4090D 渲染服务暴露 HTTP / 流式接口预留

## 4090D 外网 SSH（反向隧道）

为了避免家里 4090D 机器对阿里云 `7000` 端口偶发不可达，当前还额外准备了一条更稳的 SSH 方案：

- 4090D 主机主动连阿里云 `22/tcp`
- 阿里云创建专用用户：`gpu-tunnel`
- 通过反向 SSH 把阿里云 `6022/tcp` 映射回家里机器的 `22/tcp`

仓库内文件：

- `deploy/reverse-ssh/gpu-tunnel-authorized-key.pub`
- `deploy/reverse-ssh/gpu-tunnel-sshd.conf`
- `.github/workflows/setup-reverse-ssh-server.yml`

如果服务器端 workflow 已成功运行，家里 4090D 机器再启动反向隧道服务后，就可以通过：

```bash
ssh -p 6022 charles@47.250.168.45
```

从外网进入 4090D 机器。

## 本机前端验收工具

项目现在已经固定安装了本地 Node + Playwright 工具链，不需要每次再临时下载：

- `package.json`
- `package-lock.json`
- `playwright@1.58.2`
- 独立 `Chromium`

控制台验收可直接执行：

```powershell
cd D:\charles\Documents\doctor-avatar
$env:CONSOLE_USERNAME="admin"
$env:CONSOLE_PASSWORD="你的控制台密码"
npm run validate:console
```

会输出：

- `output/console-validation.png`
- `output/console-validation.txt`

这样后面做后台 UI 验证时，不需要再去抢占你正在开的 Chrome 会话。

验收脚本当前会核对这些关键点：

- 监控台是否正常打开
- `CPU / Memory / Disk / Active Users`
- `Memory Code`
- 只读模式提示

## 阿里云 SWAS 官方命令通道

当前已经确认这台轻量应用服务器可以通过官方 SWAS OpenAPI 执行命令，不必再只依赖 GitHub 自动部署猜服务器状态。

已确认信息：

- 地域：`ap-southeast-3`
- 实例 ID：`7c3a74523d1f49e192b158e0f919eed4`
- endpoint：`swas.ap-southeast-3.aliyuncs.com`
- 云助手状态：在线

本地脚本：

- `scripts/swas_run_command.py`

先在本机设置环境变量：

```powershell
$env:ALIBABA_CLOUD_ACCESS_KEY_ID="你的RAM用户AK"
$env:ALIBABA_CLOUD_ACCESS_KEY_SECRET="你的RAM用户SK"
```

然后执行：

```powershell
cd D:\charles\Documents\doctor-avatar
python .\scripts\swas_run_command.py "hostname"
python .\scripts\swas_run_command.py "docker compose -f /root/doctor-avatar/docker-compose.prod.yml ps"
```

脚本会：

- 调用 SWAS `RunCommand`
- 自动轮询执行结果
- 打印命令输出、状态、退出码

## 需要填写的内容

### 1. `.env`

- `OPENAI_API_KEY`
- `STT_API_KEY`
- `STT_LANGUAGE`
- `OPENAI_STT_MODEL`
- `OPENAI_STT_PROMPT`
- `OPENAI_TTS_API_KEY`
- `DASHSCOPE_API_KEY`
- `TTS_PROVIDER`
- `TTS_FALLBACK_PROVIDER`
- `ALIYUN_TTS_MODEL`
- `ALIYUN_TTS_VOICE`
- `OPENAI_TTS_MODEL`
- `OPENAI_TTS_VOICE`
- `EDGE_TTS_VOICE`
- `HEYGEN_API_KEY`
- `HEYGEN_AVATAR_ID`
- `HEYGEN_VOICE_ID`
- `HEYGEN_CONTEXT_ID`

这些 HeyGen 参数现在默认走后端配置，前端和调试页都不再要求手填。

当前推荐语音路线：

- 当前可上线主流程：
  - `OpenAI STT`
  - `DeepSeek Chat`
  - `阿里云 TTS -> OpenAI TTS -> Edge TTS`
  - `浏览器本地 Web 2D`
- 下一阶段主目标：
  - `阿里云实时语音`
  - 原因：更贴近中文低延迟通话感、成熟男声、以及后续父亲本人声音克隆

当前默认模型与音色：

- `OpenAI STT`
  - 默认模型：`gpt-4o-mini-transcribe`
  - 默认语言：`zh`
  - 用途：当前已跑通的主识别路径
- `阿里云 TTS`
  - 默认模型：`qwen-tts-latest`
  - 默认男声：`Ethan`（晨煦，标准普通话，阳光温暖）
  - 定位：成熟、稳重、专业，适合作为医生助手默认音色
- `OpenAI TTS`
  - 默认模型：`gpt-4o-mini-tts`
  - 默认男声：`cedar`
- `Edge TTS`
  - 默认男声：`zh-CN-YunxiNeural`

说明：

- 当前聊天仍可继续走 DeepSeek（`OPENAI_BASE_URL=https://api.deepseek.com`）
- `OpenAI STT` 优先读取：
  - `STT_API_KEY`
  - 若未设置，再回退到 `OPENAI_API_KEY`
- `OpenAI TTS` 不再复用 DeepSeek 的 `OPENAI_API_KEY` 语义，而是优先读取：
  - `OPENAI_TTS_API_KEY`
  - 若未设置，再回退到 `STT_API_KEY`
- 因此现在可以实现：
  - `OpenAI STT` 作为当前稳定识别入口
  - `阿里云男声` 作为默认主线
  - `OpenAI 男声` 作为独立支线
  - 且不影响聊天继续使用 DeepSeek

更完整的主线判断见：

- [docs/VOICE_MAINLINE_PLAN.md](D:\charles\Documents\doctor-avatar\docs\VOICE_MAINLINE_PLAN.md)

- `CONSOLE_USERNAME`
- `CONSOLE_PASSWORD`
- `CONSOLE_MEMORY_WRITE_ENABLED`
- `DOCTOR_MEMORY_DB_PATH`
- `DOCTOR_MEMORY_BOOTSTRAP`

如果你要保护公网控制台，这两个必须填写。

如果你不希望后台误改资料库，保持：

- `CONSOLE_MEMORY_WRITE_ENABLED=false`

### 2. `knowledge/doctor_profile.yaml`

把你爸的：

- 名字
- 科室
- 擅长方向
- 说话风格
- 禁答规则

填进去。

### 3. `knowledge/*.md`

继续补充：

- 高频问答
- 术前术后宣教
- 慢病随访说明
- 常见检查解释

## API

### `POST /api/chat`

输入：

```json
{
  "message": "最近胸闷，需要去医院吗？",
  "conversation": []
}
```

### `POST /api/liveavatar/token`

用于向 HeyGen LiveAvatar 申请 session token。当前实现按官方新版流程组织，请求体支持：

- `mode`
- `avatar_id`
- `voice_id`
- `context_id`
- `language`
- `is_sandbox`

### `POST /api/liveavatar/session`

用于用 `session_token` 启动一条 LiveAvatar session。当前版本主要先打通后端接口，后续再接真正的视频前端。

### `GET /api/liveavatar/sessions`

列出当前账号下的 session。

### `POST /api/liveavatar/keepalive`

用 `session_token` 延长当前 session 生命周期。

### `GET /api/memory/entries`

读取“医生想法资料库”里的条目。当前默认受控制台 Basic Auth 保护，适合内部维护。

支持参数：

- `kind`
- `q`
- `limit`

### `POST /api/memory/entries`

新增一条“医生想法资料”到 SQLite 资料库。适合后面逐步把你爸的口头表达、判断原则、沟通方式、临床偏好补进去。

### `GET /api/memory/summary`

返回当前资料库总条数、各分类分布，以及当前资料库暗号 `memory_code`。这个暗号会跟随快照一起进入 Git 和服务器，可用来快速核对线上是否已经同步到最新资料。

### `GET /api/ops/overview`

返回控制台监控台需要的只读运行状态，包含：

- CPU / 内存 / 磁盘占用
- 网络累计收发流量
- 最近活跃用户数
- 请求总量 / 错误数 / 平均延迟
- OpenAI 调用次数与累计 token
- 当前资料库总数、分类分布、暗号、只读/写入模式

说明：

- 这是站内监控统计，不是阿里云账单口径
- OpenAI 消耗是当前应用进程统计值，不等于官方计费后台最终数字

### `POST /api/ops/presence`

用户端浏览器会定时上报轻量心跳，用来估算最近活跃的真实用户数。

### `POST /api/memory/entries/delete`

按 `entry_ids` 删除误录或明显错误的资料条目。删除后会自动刷新资料库暗号，并让统一检索索引立即失效重建。

## 当前前端能力

用户端现在已经可以：

- 展示李勇医生公开职业资料与专科方向
- 按设备自动切换桌面版和手机版
- 提供一个面向用户的文本提问入口
- 语音开始后本地检测停顿并自动结束录音，减少“还要手动点停止”的工具感
- 保留视频分身入口与接口，但当前默认不启用高成本的实时视频链路

## 医生想法资料数据库

当前已经新增一层轻量数据库：

- 默认使用 `SQLite`
- 本地默认路径：`data/doctor_memory.db`
- 生产环境通过 `DOCTOR_MEMORY_DB_PATH` 指向持久化卷
- 首次启动会自动把：
  - `doctor_profile.yaml`
  - `common_faq.md`
  - `style_examples.md`
  的内容导入为第一批种子数据

这层数据库的作用不是替代原来的知识文件，而是专门存：

- 你爸的想法
- 他的表达习惯
- 临床沟通偏好
- 一些你后面慢慢补充的经验规则

当前问答链路已经会同时参考：

- 静态知识库
- 医生想法资料库

如果要把整理好的草稿批量导入 SQLite，可执行：

```powershell
cd D:\charles\Documents\doctor-avatar
.\.venv\Scripts\python.exe .\scripts\import_memory_draft.py
```

可选参数：

- `--section public`
- `--section ppt`
- `--path research/doctor-li-memory-draft.yaml`

如果要先做资料库清洗审计，再决定是否删除明显重复项和测试脏数据，可执行：

```powershell
cd D:\charles\Documents\doctor-avatar
.\.venv\Scripts\python.exe .\scripts\audit_memory_cleanup.py
.\.venv\Scripts\python.exe .\scripts\audit_memory_cleanup.py --apply-safe
```

会生成报告：

- `tmp/memory_cleanup_report.md`

控制台现在已经可以：

- 创建 LiveAvatar token
- 启动 session
- 用返回的 `livekit_url` 和 `livekit_client_token` 直接连接 LiveKit
- 自动请求麦克风并订阅远端音视频
- 显示 session 信息和事件日志
- 显示后端当前采用的 LiveAvatar 预设配置
- 单独调试 OpenAI 问答层
- 直接查看当前资料库暗号与分类分布
- 按关键词 / 分类筛选资料条目
- 查看服务器负载、网络累计流量、请求量、平均延迟、OpenAI 调用统计

当前控制台策略已经调整为：

- 以“系统监控 + 问答验证 + 只读资料检索”为主
- 默认禁用后台资料写入
- 即使保留写接口，只要 `CONSOLE_MEMORY_WRITE_ENABLED=false`，控制台写入和删除也会返回 `403`

## 资料库暗号校验

现在数据库会自动生成一个“资料库暗号”，格式类似：

- `LYDB-20260313-48885737`

这个暗号有 3 个用途：

- 每次资料库内容变化后，快照会自动刷新暗号
- 自动部署后，服务器数据库会同步到同一个暗号
- 可直接在网站里提问：
  - `请只回答当前资料库暗号和资料条数，不要解释`

如果网页返回的暗号和 Git 里的 `research/doctor-memory-snapshot.json` 一致，就说明线上数据库已经更新到对应版本。

## 云端部署

项目现在已经补齐可上云的生产部署骨架：

- `Dockerfile`
- `docker-compose.prod.yml`
- `deploy/nginx/default.conf`
- `deploy/ALIYUN_ECS.md`

如果你要部署到阿里云 ECS，直接参考：

- [deploy/ALIYUN_ECS.md](D:\charles\Documents\doctor-avatar\deploy\ALIYUN_ECS.md)

## 视频分身策略

当前项目策略是：

- `HeyGen / LiveAvatar` 接口全部保留
- 默认 `ENABLE_VIDEO_AVATAR=false`
- 先完成低成本的主流程上线
- 后续如果要重新接入视频分身，只需补齐 HeyGen 参数并把 `ENABLE_VIDEO_AVATAR=true`

如果要进入“真人视频分身二期”，请先看：

- [docs/VIDEO_AVATAR_PHASE2.md](D:\charles\Documents\doctor-avatar\docs\VIDEO_AVATAR_PHASE2.md)

当前推荐方向不是把 `Live2D` 当主路线，而是：

- 阿里云继续负责网页、问答、资料库、调度
- 家里 `4090D` 作为视频渲染 worker
- 优先评估 `Ditto`
- 备选 `MuseTalk 1.5`
- 产品上先做“音频先响应，视频后补上”

## 控制台保护

当前默认启用控制台 Basic Auth：

- `CONSOLE_AUTH_MODE=basic`
- `CONSOLE_USERNAME`
- `CONSOLE_PASSWORD`

保护范围包括：

- `/console`
- `/api/liveavatar/*`

## 下一步建议

1. 把你爸的内部口吻、常见回答和禁答规则补进知识库
2. ~~先把 `DASHSCOPE_API_KEY` 配上~~ ✅ 已完成，默认男声改为 `Ethan`（晨煦）
3. 连续测试 30 到 50 个高频耳鼻咽喉科问题，重点观察 STT 医学词识别
4. 再把主线推进到 `阿里云实时语音 + Web 2D`
5. 最后再考虑父亲本人声音克隆，不要反过来阻塞主线

## CHANGELOG

### 2026-03-16（一）—— windows-claude 代码审计修复 + 语音通话体验优化

**代码审计（7项修复）：**
- 修复 `__import__("httpx")` → 正常 import（P0）
- 修复 `stt.py` inp_path NameError（P0）
- nginx `proxy_buffering off` 给 SSE 端点（P1，减少延迟）
- nginx 安全头：HSTS + X-Content-Type-Options + X-Frame-Options（P1）
- nginx gzip 压缩：JSON/JS/CSS/SSE 响应压缩 44%（P1）
- 修复 connDot 永远绿色的逻辑 bug（P1）
- 移除 `/api/app-config` 暴露的 db_path（P2）

**语音通话体验优化：**
- 语音通话全屏 overlay（FaceTime/微信风格）：深色背景、大头像、脉冲光环、状态文字、计时器、波形条
- Edge TTS 声音 YunxiNeural→YunjianNeural（沉稳播音腔）+ 语速 +15%
- Prompt 重写为电话口语风格：1-3 句 60 字以内，主动追问，用口语词
- 麦克风持久化：通话期间 stream 保持开启，消除每轮 500ms+ 初始化延迟
- VAD 静音幻觉修复：前端不提交无人声录音 + 后端过滤 prompt echo
- iOS Safari TTS 用 Web Audio API + iOS STT 用 ffmpeg 转 WAV

### 2026-03-15（日）—— windows-claude MiniMax 风格重设计 + 移动端修复 + 开始/结束问诊

**为什么改**：界面之前被 codex 多轮迭代改回了旧风格，用户桌面上有 MiniMax 设计的两个参考页面需要恢复。移动端 TTS 一直朗读失败。开始问诊按钮太小且无法结束问诊。

**改了什么**（`user_desktop.html`、`user_mobile.html`、`user.js`）：
- 桌面端和移动端模板完整重写为 MiniMax 蓝紫玻璃拟态风格
- 动态背景光球、渐变按钮、glassmorphism 卡片、自定义滚动条
- 桌面：双列布局（头像区左、聊天区右），医生头像圆形+发光动画
- 移动：手机容器布局，紧凑头部+全高聊天区
- `startConsultBtn` 改为全宽突出按钮（17px 粗体、渐变背景、麦克风图标）
- 新增 `endConsultBtn`（结束问诊，红色渐变，点击后停止录音/TTS/重置状态）
- 移除 inline script，按钮切换逻辑统一在 user.js 管理
- 移动端确认所有 24 个功能 DOM ID 完整，user.js 正确加载

### 2026-03-15（日）—— windows-claude 修复多轮语音对话 + 打断 + 口语化

**Bug 修复**：
- 回答播完后自动开始录音（600ms 延迟），不再需要手动点击
- 支持打断：用户点语音按钮可立即中断当前播放和 SSE 流
- SSE 流期间 voiceInputBtn 保持可用，AbortController 清理中断

**口语化改进**：
- Prompt 重写：2-4 句话口语回答，不用 markdown/列表/加粗
- 回答长度从 ~240 字降到 45-77 字，更像门诊对话
- 短句合并（<8 字不单独 TTS），减少请求数

**延迟再次优化**：首段音频 2.6-3.2s，总完成 3.3-4.7s

### 2026-03-15（日）—— windows-claude 实时语音通话：SSE 流式 Chat+TTS 流水线

**为什么改**：之前语音链路是"等 Chat 全部生成 → 等 TTS 全部合成 → 播放"，总延迟 11-20 秒，完全不像通话。

**改了什么**（`app/main.py`、`app/static/user.js`）：
- 新增 `/api/voice-chat` SSE 端点：DeepSeek 流式生成 → 按句子切分 → 每句即时 Edge TTS → SSE 事件流返回文字+音频
- 新增 `/api/tts/stream` 端点：Edge TTS chunked streaming，独立使用时 <1.5s
- 前端 `askQuestion()` 聊天模式改用 SSE：文字逐 token 实时显示，音频按句队列播放
- 前端 `speakAnswer()` 改为句级并行 TTS：第一句播放时后续句子同时获取

**效果**：
- 首个文字 token：1.6-3.2s（改前 5-9s）
- 首段语音播放：3.1-5.5s（改前 11s+）
- 总完成时间：5.7-7.6s（改前 17-20s）
- 用户听到第一句话时，后续句子仍在生成和合成

**30 题耳鼻喉科测试**：30/30 全部通过，26/30 包含就医建议边界

### 2026-03-15（日）—— windows-claude 接通阿里云 TTS 并修正默认男声

**为什么改**：Codex 之前把 TTS 默认男声设为 `Neil`，但 `qwen-tts-latest` 实际不支持该声音（API 返回 400）。同时服务器 `.env` 缺少 `DASHSCOPE_API_KEY`，阿里云 TTS 一直回退到 OpenAI。

**改了什么**（`app/config.py`、`.env.example`、`README.md`、服务器 `.env`）：
- 查阿里云百炼文档确认 `qwen-tts-latest` 支持的男声：`Ethan`（晨煦）、`Moon`（月白）、`Kai`（凯）、`Nofish`（不吃鱼）
- 默认男声从 `Neil` 改为 `Ethan`（标准普通话，阳光温暖，最接近医生场景）
- 服务器配置 `DASHSCOPE_API_KEY`（百炼平台 key）并重建容器使其生效
- 公网实测 `https://liyong828.com/api/tts` 返回 200，Provider: aliyun，194KB WAV 音频

**效果**：阿里云 TTS Ethan 男声已上线，不再回退到 OpenAI

### 2026-03-14（六）—— codex 给 Web 2D 语音主线补上本地静音自动收尾

**为什么改**：当前主路线虽然已经是 `Web 2D + 语音问诊`，但交互上仍然有明显“录音工具感”：

- 用户说完以后还得再点一次“停止录音”
- 对老人或首次使用者来说，这一步会打断“像通话”的感觉
- 而官方实时语音路线本身普遍就是依赖 VAD / turn detection 自动判断何时说完

所以这次先不激进重写成整条实时 WebRTC 链路，而是在当前主线上先补一层本地静音检测，让体验先更像通话。

**改了什么**（`app/static/user.js`）：

- 新增浏览器侧录音 VAD 状态：
  - `voiceHasSpeech`
  - `voiceLastSpeechAt`
  - `voiceSpeechDetectedAt`
  - `recordingStopReason`
- 新增本地静音检测逻辑：
  - 检测到有效说话后，若持续静音约 `1.1s`，自动结束本轮录音
  - 若长时间没检测到清晰语音，也会自动收尾并提示重试
  - 单轮录音过长时会自动按阶段提交，避免一直悬挂
- 录音状态提示同步改得更口语化：
  - 不再只提示“点停止录音”
  - 改成“说完后会自动提交，也可以手动结束”

**效果**：

- 当前 `Web 2D` 主线虽然还不是完整实时双工通话，但已经更接近“说完自然接下去”的感觉
- 这一步和后续阿里云实时语音的方向一致，不是一次性 hack
- 页面结构没有加重，也没有引入新的复杂布局

### 2026-03-14（六）—— codex 收紧语音主线路线并升级 STT 缺省模型

**为什么改**：当前主产品线已经明确从 `Ditto` 转向 `Web 2D + 低延迟语音`，但代码和文档里还有两个问题：

- `/api/stt` 仍然写死旧的 `whisper-1`，后续切模型或调中文医学识别提示都得改代码
- 仓库里虽然已经有 `阿里云 TTS` 和 `OpenAI TTS` 分层，但“当前稳定主线”和“下一阶段最优路线”还没有被明确写死，容易继续摇摆

**改了什么**（`app/config.py`、`app/stt.py`、`app/main.py`、`.env.example`、`docs/VOICE_MAINLINE_PLAN.md`）：

- 新增 `app/stt.py`，把语音识别收成独立服务，后续接供应商切换或实时链路时不需要再把逻辑散落在 `main.py`
- `OPENAI_STT_MODEL` 改成配置项，当前默认值设为 `gpt-4o-mini-transcribe`
- 新增：
  - `STT_LANGUAGE`
  - `OPENAI_STT_PROMPT`
  方便针对中文耳鼻咽喉科语音做更稳的识别提示
- `/api/stt` 现在除了返回转写文本，也会返回当前 `provider` 和 `model`
- `/api/app-config` 新增 `stt` 状态，便于控制台或验收脚本判断当前识别配置
- 新增 [docs/VOICE_MAINLINE_PLAN.md](D:\charles\Documents\doctor-avatar\docs\VOICE_MAINLINE_PLAN.md)，明确：
  - 当前可上线主流程：`OpenAI STT -> DeepSeek -> 阿里云/OpenAI/Edge TTS -> Web 2D`
  - 下一阶段主目标：`阿里云实时语音`
  - `Ditto` 继续保留实验支线，不再定义默认用户路线

**效果**：

- 现有语音主线先变得更可控，不必每次为了 STT 微调再改后端代码
- 文档口径已经明确：`OpenAI` 继续做当前稳定识别备线，`阿里云` 是下一阶段中文实时通话主线
- 后面如果要推进“更像电话”的交互，可以在现有服务边界上继续扩，而不是再重拆一次

### 2026-03-14（六）—— codex 清理云服务器残留下载与失活隧道

**为什么改**：用户反馈 Claude 曾通过阿里云服务器中转下载大文件，导致服务器上残留了临时 HTTP 文件服务、大体积下载文件和失活的反向隧道占位端口。继续放着会带来三个问题：

- `/tmp` 被无意义的大文件和一次性脚本堆满
- `6022/8001/8002` 看起来还在监听，但其实已经是假在线
- 误导后续排障，以为 Ditto 或反向 SSH 还活着

**这次在阿里云上实际做了什么**（通过 `SWAS RunCommand`）：

- 关闭了残留的 `python3 -m http.server 9999`
- 清掉了失活的 `gpu-tunnel` 占位 sshd 进程
- 删除了 `/tmp` 下堆积的临时下载脚本、日志和中转文件
- 删除了大文件：
  - `ollama-linux-amd64.tar.zst`（约 `1.9G`）
  - `frp.tar.gz`
- 同时把线上实验开关维持在：
  - `ENABLE_DITTO_VIDEO=false`
  - `ENABLE_DITTO_STREAM=false`
  避免当前坏掉的 Ditto 支线重新暴露给用户

**结果**：

- `/tmp` 从约 `2.0G` 降到 `36M`
- 服务器上不再有 `9999`
- 服务器上不再有假在线的 `6022/8001/8002`
- 当前只保留真正需要的：
  - `frps :7000`

### 2026-03-14（六）—— codex 补齐依赖并固定 4090D 运行环境安装脚本

**为什么改**：当前项目反复在两类地方绕弯子：

- 本地 `doctor-avatar` 需要的 Python/npm/Playwright 工具虽然已经基本装齐，但没有一个明确的“检查完就算齐了”的收口动作
- 家里 `4090D` 的 Ditto 环境更危险：少包时会导致服务起不来，多装又可能把现有 `torch` 栈顶坏

用户明确要求“没装依赖或者软件先装一下，别凑合”，所以这次把运行依赖补齐流程固定成可复用脚本，而不是继续靠记忆。

**改了什么**（`deploy/ditto/install_runtime_deps.sh`）：

- 新增 `deploy/ditto/install_runtime_deps.sh`
- 脚本默认安装 `Ditto` 服务真正需要的运行包：
  - `fastapi`
  - `uvicorn`
  - `websockets`
  - `soundfile`
  - `ffmpeg-python`
- 默认也会装 `gradio` 作为本地演示/调试辅助
- `xformers` 改成显式开关：
  - 默认 `INSTALL_XFORMERS=0`
  - 避免一条命令把现有 `torch / torchvision / torchaudio` 兼容栈直接顶坏
- 脚本末尾会做一次模块导入校验，避免出现“包名装了但运行时还是 import 失败”

**这轮实机结果**：

- 本地 `doctor-avatar` 这一侧已经确认依赖齐全：
  - `.venv` 里的 Python 包正常
  - `npm` 依赖正常
  - `playwright` / 本地 Chromium 正常
- 4090D 这边已经把缺的 `gradio` 和 `ffmpeg-python` 补上了
- 这次也踩出了一个真实坑：`xformers` 会尝试替换当前 `torch` 主栈，所以脚本里已经改成默认不自动装

### 2026-03-14（六）—— codex 接入双语音路线：阿里云主线 + OpenAI 支线

**为什么改**：用户明确要求两件事同时成立：

- 现在先换成更成熟一点的男声，而且要更像医生
- 后面保留 `OpenAI` 路线作为支线，不让实时语音能力被单一路径绑定

同时，当前项目里 `OPENAI_API_KEY` 已经被用来指向 `DeepSeek` 聊天兼容接口，所以如果直接把它拿来做 OpenAI TTS，会导致语音链路与聊天链路混淆。

**改了什么**（`app/config.py`、`app/models.py`、`app/main.py`、`app/speech.py`、`.env.example`）：

- 新增统一语音服务 `app/speech.py`，把三条 TTS 路径收成一套可切换能力：
  - `aliyun`
  - `openai`
  - `edge`
- 默认优先级改成：
  - `阿里云 TTS` 主线
  - `OpenAI TTS` 支线
  - `Edge TTS` 兜底
- 当前默认声音选择为：
  - 阿里云：`Ethan`
  - OpenAI：`cedar`
  - Edge：`zh-CN-YunxiNeural`
- `/api/tts` 现在支持传 `provider` 和 `voice`
- `Ditto` 的离线视频生成和流式音频源也开始复用同一套语音服务，不再只写死 `edge-tts`
- 新增 `OPENAI_TTS_API_KEY`，避免把聊天用的 DeepSeek key 和 OpenAI 官方语音 key 混在一起

**效果**：

- 现在可以明确区分：
  - `聊天主脑` 走 DeepSeek
  - `语音主线` 走阿里云
  - `语音支线` 走 OpenAI
- 即使阿里云语音暂时没配 key，默认链路也会自动回退，不会把现有站点语音功能直接弄坏

### 2026-03-15（日）—— codex 切换到 Web 2D 浏览器本地主路线

**为什么改**：用户明确反馈 `Ditto` 这条路即使已经把流式链路打通，也仍然不像真正的实时语音通话，更接近“生成后再播”的视频实验链路。结合这台阿里云 `2核2G` 服务器、当前没有现成 `.moc3` 资产、以及用户更看重 `低延迟实时感` 的前提，当前最优主路线应改成：

- 浏览器本地 `Web 2D` 语音头像
- 语音识别 `Whisper STT`
- 回答 `DeepSeek`
- 语音播报 `edge-tts`
- `Ditto` 保留为实验支线，不再作为默认体验

如果后续拿到可商用的 `Live2D .moc3` 资产，再升级到官方 `Cubism SDK for Web / MotionSync` 会更合适。

**改了什么**（`app/main.py`、`app/static/user.js`、`app/templates/user_desktop.html`、`app/templates/user_mobile.html`）：
- `/` 根路由恢复按 `User-Agent` 自动选择桌面/手机模板，而不是继续走一个过重的混合页
- 非 `LiveAvatar` 模式下，主按钮统一改成 `开始问诊`，点击后直接进入麦克风录音/停止录音流程，不再误导成“视频通话”
- 语音录完后改成：
  - 自动转写
  - 自动发问
  - 自动播报回答
  形成真正可连续使用的主语音链路
- `Ditto` 只在显式实验开关打开时才会自动触发，不再污染默认用户体验

**服务端顺手修复**：
- 新增 `/robots.txt`，减少探测日志里的无效 `404`
- 新增 `/favicon.ico` 响应，减少浏览器和扫描器反复打 `404`

**影响**：
- 当前默认用户体验正式切到 `Web 2D 实时语音`，比 Ditto 的“先生成后播放”更接近真正可用的通话半成品
- `Ditto` 不删除，继续保留作实验/备用路线
- 桌面和手机首页都会自动走各自更轻的模板，减少之前混合页结构带来的重叠和混乱
### 2026-03-15（日）—— codex 修掉 `/api/stt` 的 500 根因

**为什么改**：用户实测点击语音按钮后直接提示“识别失败 HTTP 500”。我通过阿里云 `SWAS RunCommand` 直接查线上 `app` 容器日志，定位到 `/api/stt` 在 `await request.form()` 时抛出了：

- `AssertionError: The python-multipart library must be installed to use form parsing.`

也就是说，Claude 已经把录音上传改成 `MediaRecorder + Whisper STT`，但运行镜像里缺少了解析 multipart/form-data 的必备依赖。

**改了什么**（`requirements.txt`）：
- 新增 `python-multipart>=0.0.9,<1`

**影响**：
- 这是 `/api/stt` 走文件上传表单解析的必要依赖
- 不补它，语音按钮路径一定是 `500`
- 补上并重新部署后，才能继续验证新的 `MediaRecorder + Whisper STT` 语音识别链路

### 2026-03-15（日）—— codex 收紧 `/api/stt` 认证失败提示

**为什么改**：`python-multipart` 补上后，我继续实测公网 `/api/stt`，发现新的失败已经不是代码异常，而是服务器上的 `STT_API_KEY` 被 OpenAI 直接拒绝，返回 `401 authentication_error`。如果继续原样透传，前端只会看到一个模糊的失败提示，既误导排障，也会把底层错误原文暴露给用户。

**改了什么**（`app/main.py`）：
- 给 `/api/stt` 增加了鉴权失败分支判断
- 当底层返回 `authentication_error / invalid key` 时，统一改成：
  - `503`
  - `语音识别服务认证失败，请检查服务器上的 STT_API_KEY 是否为有效的 OpenAI API key。`

**影响**：
- 语音按钮再出错时，页面会拿到更明确的中文原因
- 当前真正需要修的已经不再是后端代码，而是换一把有效的 OpenAI STT key

### 2026-03-15（日）—— codex 修掉 `/api/stt` 被 DeepSeek base URL 污染

**为什么改**：我后续继续排查时发现，新的 OpenAI STT key 本身其实是有效的；问题是应用进程里同时设置了：

- `OPENAI_BASE_URL=https://api.deepseek.com`
- `STT_API_KEY=<OpenAI key>`

而 `/api/stt` 里创建 `OpenAI()` 客户端时没有显式传 `base_url`，会继承进程环境里的 `OPENAI_BASE_URL`。结果就变成了“拿 OpenAI 的 key 去打 DeepSeek 兼容端点”，用户侧表现仍然像是 key 无效。

**改了什么**（`app/main.py`）：
- 给 `/api/stt` 里的 `OpenAI()` 客户端显式固定：
  - `base_url=\"https://api.openai.com/v1\"`

**影响**：
- 聊天继续走 `DeepSeek`
- STT 单独固定走 OpenAI 官方转写接口
- 避免 `OPENAI_BASE_URL` 对语音识别链路产生污染

### 2026-03-14（六）—— codex 修正视频按钮交互误导

**为什么改**：线上真实可用的是 `提问 -> DeepSeek 回答 -> TTS 朗读 -> Ditto 生成视频`，但首页按钮仍沿用旧的 LiveAvatar 文案和逻辑。用户点击“视频通话/视频分身”时不会申请麦克风，也不会进入当前这条 Ditto 语音视频路径，实际体验会误以为功能失效。

**改了什么**（`app/static/user.js`、`app/templates/user_desktop.html`、`app/templates/user_mobile.html`）：
- 把首页视频按钮默认文案改成更符合当前能力的 `语音视频`
- 当前端检测到 `ditto_enabled=true` 且 `video_avatar_enabled=false` 时，点击按钮不再走旧 LiveAvatar 路径，而是直接进入现有的 Ditto 语音视频模式
- 优先触发浏览器语音输入（会请求麦克风权限）；如果浏览器不支持，则明确提示用户先说或先输入问题，发送后系统会自动朗读并生成视频
- 同步把页面状态文案从“未启用/等待会话启动”改成更贴近现状的 “本地待命 / 提问后自动生成视频”

**影响**：
- 用户点击按钮时终于会进入当前真正可用的交互路径，而不是落到旧能力上
- Ditto 现有能力与前端按钮行为对齐，减少“后端通了但前端像坏了一样”的误判

### 2026-03-14（六）—— codex 收紧 Ditto 语音视频体验

**为什么改**：虽然 `/api/tts` 和 `/api/ditto/generate` 已经打通，但真实浏览器验收时仍有两个体验断点：
- 点击 `语音视频` 后不会先主动请求麦克风权限，用户容易以为按钮没反应
- 问答返回后仍需要手动点 `朗读`，导致用户主观上先看到静态医生照片，以为系统卡住

**改了什么**（`app/static/user.js`）：
- 新增 `prepareMicrophoneAccess()`：点击 `语音视频` 时先主动请求浏览器音频权限，并根据结果给出更明确的状态反馈
- `askQuestion()` 拿到回答后会立即调用 `speakAnswer(data.answer)`，不再要求用户手动点 `朗读`
- 新增 `renderVideoLoading()`：Ditto 视频生成中时，主舞台会显示明确的过渡态，而不是一直停留在静态照片
- 视频结束或出错后，主舞台状态会回到 `提问后自动生成视频`，避免页面状态退回错误文案

**目标体验**：
- 点击 `语音视频` 后，页面应先进入语音模式并尽可能拉起麦克风权限
- 发送问题后应自动触发：
  - `/api/chat`
  - `/api/tts`
  - `/api/ditto/generate`
- 用户应先听到回答，再看到视频切换，而不是只看到一张静态医生照片

### 2026-03-14（六）—— codex 搭好 Ditto 流式服务骨架（4090D）

**为什么改**：当前公网用户页已经能跑 `TTS + Ditto mp4`，但那还是“先生成整段视频，再播放”的短视频模式。为了给 Claude 接网站侧实时流式链路，4090D 端需要先具备一个稳定的在线帧服务。

**改了什么**（`deploy/ditto/ditto_stream_service.py`、`deploy/ditto/ditto-stream.service`）：
- 新增 `deploy/ditto/ditto_stream_service.py`：基于 Ditto 官方 `stream_pipeline_online.py` 和 `v0.4_hubert_cfg_trt_online.pkl` 搭了一个 `ws://127.0.0.1:8002/ws` 的本地流式服务
- 服务协议当前固定为：
  - 客户端持续发送二进制 `pcm_s16le / 16kHz mono` 音频块（约 `0.4s` 一块）；当前也兼容带 `RIFF` 头的 WAV 块，便于本地调试
  - 服务端持续返回 JPEG 帧（二进制）
  - 客户端发字符串 `END` 或二进制 `b"END"` 后，服务端会继续吐完剩余帧，并最终返回 `{"done":true}`
- 新增 `deploy/ditto/ditto-stream.service`：把 4090D 侧流式服务注册成独立 systemd 单元，避免影响现有 `8001` 的离线 `mp4` 服务

**远端落地结果**：
- 4090D 上 `ditto-stream.service` 已启用并运行
- 反向 SSH 隧道已新增：
  - `-R 127.0.0.1:8002:127.0.0.1:8002`
- 阿里云服务器本机已实测：
  - `http://127.0.0.1:8002/health` 返回 `200`

**实测结论**：
- 4090D 本机通过 WebSocket 客户端发送 `6` 段 `0.4s` PCM 音频后，流式服务实际回出了多帧 JPEG，并在结束时返回 `{"type":"complete"}`
- 这说明 4090D 端“在线收音频块 -> Ditto 在线推理 -> 吐帧”这条链路已经成立
- 下一步只剩网站侧把浏览器 / ECS / 4090D 这三段 WebSocket 串起来

### 2026-03-14（六）—— codex 补齐 Ditto 流式前置依赖（ffmpeg）

**为什么改**：Claude 在 ECS 侧已经把 `/ws/ditto/stream` 接好了，但我复核线上环境时发现 app 容器里并没有 `ffmpeg`。当前流式链路是 `edge-tts -> ffmpeg -> PCM -> Ditto WebSocket`，如果缺这个二进制，`ENABLE_DITTO_STREAM=true` 后只会在运行时直接报错。

**改了什么**（`Dockerfile`）：
- 在运行镜像的系统依赖里补装 `ffmpeg`
- 这样容器内的 `/ws/ditto/stream` 才能把 edge-tts 产出的 MP3 实时转成 `16kHz / mono / PCM` 音频块，再分段送给 4090D 的 `8002` 流式服务

**实测发现**：
- 变更前，阿里云 app 容器里执行 `which ffmpeg` 返回 `no-ffmpeg`
- 这也是为什么当前 `app-config` 里 `ditto_stream.enabled` 还没敢打开：缺依赖会让流式视频接口在第一次调用时直接失败

### 2026-03-14（六）—— codex 修掉 Ditto 流式代理的静默关闭 bug

**为什么改**：在把 `ENABLE_DITTO_STREAM=true` 打开后，线上 `wss://liyong828.com/ws/ditto/stream` 仍然是“握手成功后立刻关闭”，没有任何帧。进一步实测发现，问题不是前端、不是 4090D、也不是隧道，而是网站代理层把 `await websockets.connect(...)` 返回的连接对象又错误地套了一层 `async with`。在 `websockets 13` 下这会直接抛 `TypeError`，而旧代码又把异常吞掉了，所以表面上看起来像“点了没反应”。

**改了什么**（`app/main.py`）：
- 去掉了 `await websockets.connect(...)` 之后那层错误的 `async with ditto_conn`
- 改成显式 `try/finally`，在流式收发结束后手动 `await ditto_conn.close()`

**定位证据**：
- 在 app 容器里按网站当前同样的写法复现实验，真实返回：
  - `TypeError: 'WebSocketClientProtocol' object does not support the asynchronous context manager protocol`
- 同时，容器内直接跑“MP3 -> ffmpeg -> PCM -> host.docker.internal:8002/ws”这段逻辑是能收到 JPEG 帧和 `{"done":true}` 的，说明 4090D 流式服务本身没有问题

### 2026-03-14（六）—— codex 服务器轻量优化与温和防护

**为什么改**：服务器本身并没有爆内存，但仍有 4 个值得先收掉的小问题：
- `2核2G` 机器没有 `swap`，短时峰值更容易直接 OOM
- Docker build cache 累积到约 `800MB`
- 旧的 `6000/tcp` 反向 SSH 残留还在监听，和现行 `6022/tcp` 混在一起
- Nginx 面对 `/.env / wp-admin / cgi-bin` 之类公网探测时缺少最基础的温和拦截

**改了什么**（`deploy/nginx/default.conf`、`deploy/frp/frps.toml`、`.github/workflows/setup-frps.yml`）：
- `deploy/nginx/default.conf`：新增温和防扫规则，直接丢弃常见探测路径；补了轻量级 API 频率/连接限制，但不影响正常页面、SWAS RunCommand、GitHub Actions 或站点主链路
- `deploy/frp/frps.toml`：把 `frps` 允许端口从旧的 `6000` 收敛到 `6022`
- `.github/workflows/setup-frps.yml`：同步把防火墙放行端口从 `6000` 改为 `6022`

**服务器实机处理**：
- 已通过阿里云 `SWAS RunCommand` 直接加上 `1GB` swap，并写入 `/etc/fstab`
- 已清空 Docker build cache，释放约 `800MB`
- 已清理旧的 `6000/tcp` 监听，只保留 `6022/tcp`

**影响**：
- 服务器在部署、重启、短时峰值时更稳
- 远程通道统一，后续不再混用 `6000 / 6022`
- 对常见扫站噪音更耐受，但不会影响当前项目、阿里云官方直连命令通道或 GitHub 自动部署

### 2026-03-14（六）—— codex 线上监控与密钥修复

**为什么改**：本轮发现 3 个直接影响线上稳定性和安全性的点：
- `README` 里误写入了真实 DeepSeek API key
- 控制台 token 统计只认 OpenAI 自有字段，切到 DeepSeek 后会失真
- 生产容器开了 `uvicorn --workers 2`，而监控统计存于进程内全局变量，导致 `/api/ops/overview` 会随 worker 漂移

**改了什么**（`README.md`、`app/ops.py`、`Dockerfile`）：
- `README.md`：移除公开仓库里的真实 key，改回占位符
- `app/ops.py`：`_usage_value()` 新增兼容字段映射，支持 `prompt_tokens / completion_tokens / totalTokens`
- `Dockerfile`：生产容器 worker 数从 `2` 收到 `1`，优先保证这台 `2核2G` 机器上的监控口径稳定一致

**影响**：
- 控制台里的 `openai_input_tokens / openai_output_tokens / openai_total_tokens` 现在能正确反映 DeepSeek 这类兼容接口的 usage
- 控制台里的请求量、错误量、活跃用户、OpenAI 调用次数不再因为多 worker 随机漂移

### 2026-03-14（六）—— windows-claude 流式 Canvas 体验细节

**为什么改**：主链路验通后（公网 wss 实测 30 帧），有两个细节影响真实用户感知：
- `startDittoStream()` 立即创建空 Canvas，用户等待首帧的 1-2 秒会看到黑屏而非明确的加载提示
- WebSocket 建立后如果 4090D 长时间不返回首帧（网络抖动/排队），前端会永久卡在空 Canvas，无任何超时保护

**改了什么**（`app/static/user.js`）：
- `startDittoStream()`：先调用 `renderVideoLoading("实时视频准备中，首帧约 1-2 秒…")` 给用户明确等待反馈；Canvas 懒挂载，首帧到达时才替换 loading 占位
- 新增 `firstFrameTimeout`（10 秒）：10 秒内未收到首帧则关闭连接，恢复占位图，聊天模式下追加"视频连接超时"提示气泡（4 秒后自动移除）
- 错误帧（`payload.error`）时聊天模式下也追加错误提示气泡（5 秒后移除），而不是静默回退
- 所有超时/完成/错误路径都调用 `clearTimeout(firstFrameTimeout)` 防止重复触发

**影响**：
- 用户不再看到黑屏等待，而是看到和批量 Ditto 相同的"AI VIDEO PREPARING"过渡页
- 网络异常时有明确超时提示而非永久卡住

### 2026-03-14（六）—— windows-claude 流式 WebSocket 异常透传

**为什么改**：`/ws/ditto/stream` 端点原来在 `except Exception: pass` 处吞掉所有错误，前端只能看到连接静默关闭，无法判断是 TTS 失败、ffmpeg 失败还是 4090D 连接失败。

**改了什么**（`app/main.py`）：
- `except Exception as exc`：捕获后调用 `ws.send_json({"error": str(exc)})` 把错误文本发回浏览器
- `asyncio.gather(_send(), _recv())` 改为 `return_exceptions=True`：两个任务都跑完后再统一检查异常，避免一个任务异常立即取消另一个，导致部分帧丢失

### 2026-03-14（六）—— windows-claude DeepSeek 接入

**为什么改**：用户切换到 DeepSeek API（中文更强、更聪明），原 `responses.create` 是 OpenAI 专有接口，DeepSeek 不支持。

**改了什么**（`app/config.py`、`app/services.py`、`.env.example`）：
- `app/config.py`：新增 `OPENAI_BASE_URL` 配置项（默认空，填 `https://api.deepseek.com` 即切换 DeepSeek）
- `app/services.py`：OpenAI client 初始化加上 `base_url` 参数；API 调用从 `client.responses.create` 改为 `client.chat.completions.create`，响应取 `choices[0].message.content`（兼容所有 OpenAI 兼容接口）
- `.env.example`：新增 `OPENAI_BASE_URL` 注释，说明 DeepSeek 切换方式

**服务器 .env 需要更新**：
```bash
OPENAI_API_KEY=<YOUR_DEEPSEEK_API_KEY>
OPENAI_BASE_URL=https://api.deepseek.com
OPENAI_MODEL=deepseek-chat
```

**补充说明**：
- 生产容器现在固定为单 worker 运行，这样 `/api/ops/overview` 的请求量、错误数、活跃用户数和 token 统计不会因为多进程而漂移。
- `app/ops.py` 已兼容 `prompt_tokens / completion_tokens` 这类 OpenAI-compatible 返回字段，适配 DeepSeek 的 token 口径。

### 2026-03-13（五）—— codex

**控制台二次视觉重构：收成一屏主舞台 + 窄侧监控轨道，去掉大片空白和低级联调感**（by codex）

- `app/templates/console.html`：整体重做为“顶部摘要条 + 左侧主舞台 + 右侧监控轨道”的单屏内部终端，去掉原先松散堆叠的大块空白卡片
- `app/templates/console.html`：实时会话舞台改成更完整的主视觉壳，加入更克制的扫描/环形占位，不再像裸空框
- `app/templates/console.html`：右侧压缩成真正的运营侧栏，把系统概览、问答验证、资料抽查明确分段，减少后台杂乱感
- `app/static/console.js`：补齐新布局所需状态映射（顶部版本、主舞台状态胶囊、侧栏关键指标）
- `scripts/validate_console_ui.mjs`：同步适配新版控制台文案，保证 Playwright 本机验收不再因旧关键词误报失败

**控制台三次收束：强制单主舞台，折叠次要模块，避免元素互相挤压**（by codex）

- `app/templates/console.html`：进一步删掉首屏里会抢空间的次要模块，把版本/预设/接口回执、命中详情、资料抽查全部改成折叠区
- `app/templates/console.html`：主区保留“视频舞台 + 会话控制 + 系统事件”，右侧只保留“系统概览 + 问答验证”，避免一屏出现多个主角
- `app/static/console.js`：继续兼容收缩后的 DOM 结构，保留统计刷新和状态写入

**控制台视觉重构：从联调堆叠页收成内部工作台**（by codex）

- `app/templates/console.html`：整体布局改为“顶部概览 + 左侧实时会话 + 右侧知识与资料”两栏工作台，移除原来过多的并列区块和重复说明
- 把核心动作压缩为三个明确区域：
  - 实时会话工作区
  - 问答验证
  - 资料录入与检索
- 资料录入后台保留原有功能，但用更轻的统计条、筛选区和列表区组织，减少“乱七八糟的功能堆叠感”

**控制台新增资料录入后台 + 资料库暗号校验链路**（by codex）

- `app/templates/console.html`：新增“资料录入与检索”面板，显示当前资料库暗号、总条数、分类分布，并提供手动录入与筛选查看入口
- `app/static/console.js`：支持资料摘要读取、列表筛选、手动新增、复制、删除和当前暗号展示，减少脚本操作
- `app/main.py`：新增 `/api/memory/summary` 和 `/api/memory/entries/delete`，并让 `/api/memory/entries` 默认隐藏技术用的 `system_marker`
- `app/memory_snapshot.py` 与 `scripts/write_memory_snapshot.py`：资料快照写入时自动维护数据库暗号，`/api/app-config` 和网站问答都可用于线上数据库版本核验
- `scripts/export_memory_review.py`：导出给医生审阅的精简 PDF 时自动排除技术暗号条目

### 2026-03-13（五）—— windows-claude 按钮文字重复修复

**为什么改**：`setBtnText` 把第一个空白文字节点改成"视频通话"，但 HTML 原有的文字节点还在，导致显示两遍。

**改了什么**（`app/static/user.js`、`app/templates/index.html`）：
- `setBtnText` 改为只匹配有实际内容的文字节点（`.trim()` 过滤空白）
- HTML 按钮 SVG 与文字紧邻写，消除空白文字节点

### 2026-03-13（五）—— windows-claude 视频按钮图标修复 + 信息面板精简

**为什么改**：user.js 用 `textContent` 覆盖按钮时会把 SVG 图标一起清掉；专注领域标签蓝色加粗不和谐；官方来源用处不大需删除。

**改了什么**：
- `app/static/user.js`：新增 `setBtnText(btn, text)` 工具函数，只更新按钮内文字节点而不清除 SVG 子元素；将3处 `startBtn.textContent =` 改为 `setBtnText`，文字统一为"视频通话"
- `app/templates/index.html`：`.chip/.tag` 改为浅灰底色 + 细边框 + 常规字重，去掉蓝色加粗，视觉更柔和；官方资料来源区段从 DOM 移除（`#officialSources` 保留隐藏节点供 user.js 写入但不显示）

### 2026-03-13（五）—— windows-claude 适老化 + 视频通话入口改版

**为什么改**：网页服务老年患者，字体偏小、按钮偏小、状态文字技术感太强（"未启用"让人困惑）。

**改了什么**（`app/templates/index.html`）：
- 聊天气泡字号 14px→16px，行高 1.65→1.75，输入框字号 14px→16px（同时防止 iOS 自动缩放）
- 发送按钮 46px→52px，辅助按钮（语音/朗读/停止）最小高度 34px→40px，字号 12px→14px
- 视频通话按钮：字号 14px→16px，padding 加大，颜色改为微信绿（#07c160），配视频摄像头图标
- "视频分身" 统一改为 "视频通话"（桌面+移动端）
- 顶栏右侧状态：通过 MutationObserver 拦截 user.js 写入的技术性文字，重映射为患者友好文字："未启用/未连接/等待会话启动" → "在线问诊"，"已连接" → "通话中"

### 2026-03-13（五）—— windows-claude 信息面板视觉重设计

**为什么改**：医生信息区字体不统一、内容平铺无层次，视觉像纯文字堆砌，缺乏设计感。

**改了什么**（`app/templates/index.html`）：
- 信息面板拆为独立 `.info-section` 区段，每段有细分隔线，内边距统一
- 节标题改为全大写小号 label（`UPPERCASE + letter-spacing`），视觉层级清晰
- `#doctorBio`：`white-space: pre-line` 保留换行，`::first-line` 伪类将第一行（姓名/职称）自动加粗加大
- 专注领域标签补充 `.chip` CSS（user.js 实际注入的是 `.chip` 而非 `.tag`，之前标签完全没样式）
- 官方来源每条链接改为带 `↗` 前缀的卡片行，有 hover 高亮，不再是裸链接
- `clinicNote` 改用渐变底色 notice-box，视觉更轻
- 隐藏重复的 `#focusList`（专注领域已有标签胶囊，列表冗余）

### 2026-03-13（五）—— windows-claude MiniMax 设计前端上线

**MiniMax 2.5 设计稿落地：响应式统一模板全面重写**（by windows-claude）

- `app/templates/index.html`：基于 MiniMax 2.5 设计的蓝紫玻璃拟态（glassmorphism）风格全面重写，统一替代原 `user_desktop.html` + `user_mobile.html` 的 `/` 路由
- 视觉设计：CSS 变量（`--accent: #2563eb`、`--ai-color: #7c3aed`）、动态背景光球动画、医生头像悬浮效果、渐变按钮、深色模式自适应（`prefers-color-scheme: dark`）
- 响应式布局：`@media (max-width: 899px)` 移动端（全屏聊天 + 底部操作栏）/ 桌面端双列网格（左侧医生卡 + 右侧视频舱），单文件零重复
- **关键兼容修复**：`startConsultBtn`、`keepAliveBtn`、`disconnectBtn`、`connDot` 等视频控件仅存在于 `avatar-section`（桌面卡），移动端操作按钮通过 `onclick` 委托（`document.getElementById('startConsultBtn').click()`）避免 DOM 重复 ID 问题
- 保留 `user.js` 所需全部 ID：`chatHistory`、`message`、`askBtn`、`connDot`、`connectionState`、`voiceInputBtn`、`speakAnswerBtn`、`stopSpeechBtn`、`voiceStatus`、`heroTitle`、`deptState`、`doctorBio`、`focusTags`、`focusList`、`officialSources`、`clinicNote`、`hospitalValue`、`brandSubtitle`、`answer`（隐藏）
- CSS 类名完全对齐 `user.js`：`.msg-row`、`.ai-label`、`.bubble`、`.typing-dots` 全部就位

### 2026-03-13（五）—— windows-claude 审查与优化

**接入统一响应式模板（index.html）**（by windows-claude）

- `app/main.py`：`/` 路由改为直接返回 `index.html`（CSS 媒体查询自动适配移动/平板/桌面），移除冗余的 User-Agent 检测逻辑和 `MOBILE_MARKERS` 常量
- `app/templates/index.html`：修复 CSS 类名与 `user.js` 不一致（`.message` → `.msg-row`，`.message-label` → `.ai-label`，`.message-bubble` → `.bubble`），补充 `.typing-dots` 兼容，修复静态初始消息的 HTML 类名

**知识库索引性能优化**（by windows-claude）

- `app/knowledge.py`：`_build_index_signature` 改用 SHA256 哈希，避免把全量文本内容存入内存做巨型字符串比较（O(N·字符) → O(64)）
- `app/knowledge.py`：`_get_index` 新增快路径 `_compute_fast_sig()`，用 SQLite COUNT/MAX 指纹 + 文件 mtime 做轻量变更检测，命中时直接返回缓存，无需每次请求都重读文件和数据库
- `app/knowledge.py`：磁盘缓存格式更新（`signature` 字段替代原 `texts` 字段，大幅减小缓存文件体积）
- `app/db.py`：删除多余空行

### 2026-03-13（五）—— codex

**控制台转向只读监控台：默认禁用资料写入，新增服务器与 API 运行监控**（by codex）

- `app/ops.py`：新增轻量运行监控模块，统计 CPU 负载、内存、磁盘、网络累计流量、请求总量、错误数、平均延迟、OpenAI 调用与 token
- `app/main.py`：新增 `GET /api/ops/overview` 与 `POST /api/ops/presence`；同时让资料写入/删除在 `CONSOLE_MEMORY_WRITE_ENABLED=false` 时直接返回 `403`
- `app/static/user.js`：新增轻量浏览器心跳，上报最近活跃用户数
- `app/templates/console.html` + `app/static/console.js`：把控制台右侧从“资料增删改”改成“系统监控 + 问答验证 + 只读资料检索”
- `.env.example`：新增 `CONSOLE_MEMORY_WRITE_ENABLED=false`
- `README.md`：补充监控接口和控制台只读模式说明

**补齐本机前端验收工具链：固定 Playwright 与独立 Chromium，不再每次临时下载或抢系统 Chrome**（by codex）

- `package.json` + `package-lock.json`：新增本地 Node 工具清单与 `npm run validate:console`
- `scripts/validate_console_ui.mjs`：新增独立控制台验收脚本，支持 Basic Auth、自动截图和正文导出
- `README.md`：补充本机 UI 验收命令与输出路径

**视频分身二期技术方案落地：明确不走 Live2D 主线，优先家里 4090D + Ditto / MuseTalk 1.5**（by codex）

- `docs/VIDEO_AVATAR_PHASE2.md`：新增二期视频分身方案，系统整理了当前项目在阿里云 `2核2G` + 家里 `4090D` 条件下的推荐路线、模型优先级、网络架构和分阶段落地方式
- `README.md`：补充二期方案入口，并把当前建议收敛为“阿里云负责网页与调度，家里 GPU 负责真人视频渲染 worker”

**资料库清洗工具：安全删除测试噪音与完全重复项**（by codex）

- `app/db.py`：新增完全重复组检测与批量删除能力
- `scripts/audit_memory_cleanup.py`：新增清洗审计脚本，可输出报告，并在 `--apply-safe` 模式下删除测试脏数据和完全重复项
- `README.md`：补充清洗审计命令与报告路径

**生产容器补齐导入所需目录：支持在 Docker 容器内执行资料导入脚本**（by codex）

- `Dockerfile`：新增复制 `scripts/` 与 `research/`，让容器内可以直接运行 `import_memory_draft.py` 并读取草稿 YAML
- `.dockerignore`：移除对 `scripts` 的排除，避免镜像构建时把导入脚本漏掉

**资料库批量导入能力：支持按草稿 YAML 幂等写入 SQLite**（by codex）

- `app/db.py`：新增 `upsert_memory_entry()`，按 `kind + title + source` 幂等更新或插入资料条目
- `scripts/import_memory_draft.py`：新增批量导入脚本，可把 `research/doctor-li-memory-draft.yaml` 的公开资料和 PPT 草稿导入数据库
- `README.md`：补充导入命令与使用方式

**李勇医生资料整理首版：公开资料深搜 + 本地 PPT 提炼 + 可入库草稿**（by codex）

- `research/doctor-li-public-materials.md`：整理了公开搜索资料、来源链接、稳定职业画像与可转化知识块
- `research/doctor-li-ppt-materials.md`：整理了桌面 `doctor li` 文件夹中 7 份 PPT 的核心主题、稳定观点和推荐入库方向
- `research/doctor-li-memory-draft.yaml`：按 `doctor_memory_entries` 字段结构产出第一版可入库草稿，分为 `public_search_entries` 和 `ppt_entries`
- `tmp/ppt_summary.md` 与 `tmp/ppt_raw_extract.md`：保留本轮 PPT 文字层抽取结果，便于后续继续精炼与校对

### 2026-03-12（四）—— codex 白天改动

**桌面端按移动端风格重写**（by codex, 09:31）

- `app/templates/user_desktop.html`：统一浅色主题和相同 CSS 变量，两列布局（左视频、右聊天），全屏高度
- 移除科幻装饰（扫描线动画、HUD 卡片、深色背景），按钮/气泡/卡片样式与移动端对齐
- 医生信息折叠内嵌聊天卡片底部

**SQLite 医生记忆库上线**（by codex, 09:40）

- `app/db.py`：新增 SQLite 记忆层，初始化 + 种子导入 + CRUD + 全量列表
- `app/main.py`：新增 `/api/memory/entries` 读写接口，启动时自动初始化数据库
- `docker-compose.prod.yml`：新增持久化卷，避免容器重建后丢失数据

**SQLite 容器权限热修**（by codex, 09:44）

- `Dockerfile`：预创建并授权 `/app_data` 与 `/app_cache`，避免挂载卷不可写导致 SQLite 启动失败

**3D 矢量动画头像替换医生照片**（by codex, 09:51）

- `app/templates/user_desktop.html` + `app/templates/user_mobile.html`：内联 SVG 立绘（白大褂、听诊器、医疗十字、脉冲环动画、漂浮粒子），渐变实现 3D 立体感

**修复 3D 头像被 JS 覆盖**（by codex, 09:55）

- `app/static/user.js`：提取 `avatarSvg()` 公共函数，`renderVideoPlaceholder()` 不再用 innerHTML 替换 SVG

**统一 embedding 检索管道**（by codex, 10:13）

- `app/knowledge.py`：合并文件+SQLite 两路来源为一套 embedding 管道；缓存失效同时校验文件内容和 SQLite 指纹（COUNT+MAX updated_at）；新增 `invalidate_index()` 供 DB 写入后调用
- `app/db.py`：移除重复的 `search_memory_entries`，只保留 CRUD 和全量 `list_memory_entries`
- `app/services.py`：简化为单次 `search_knowledge()` 调用；`app/prompts.py` 合并两段 context

**统一索引刷新修复**（by codex, 10:28）

- `app/main.py`：新增资料后主动调用 `invalidate_index()`，避免聊天命中旧 embedding 直到重启
- `app/knowledge.py`：修复 `_index_ready` 过早返回旧索引；数据库资料块改为全量参与，不再只取前 500 条

---

### 2026-03-11 深夜（五 00:02）—— windows-claude 移动端重构

**移动端完整重写**（by windows-claude, commit 9adcbee）

- `app/templates/user_mobile.html`：完整重写，视频区+聊天区合并为单张 `.main-card`（视频上、聊天下）
- 去掉 hero/intro 大区块，顶栏只保留精简 topbar
- 医生简介/来源折叠进 `<details class="card details-section">`，默认收起
- 触屏按钮尺寸规范：send-btn 44×44px，aux-btn min-height 36px，video-btn min-height 38px
- keepAliveBtn / disconnectBtn 默认 `display:none`，视频未启用时隐藏
- 保留所有 JS 兼容 ID 为隐藏 span，不破坏 user.js 逻辑

### 2026-03-11（四）—— windows-claude 夜间修复

**nginx 缓存与部署修复**（by windows-claude, 22:27~22:36）

- `deploy/nginx/default.conf`：JS/CSS 新增 `proxy_hide_header Cache-Control` + `add_header Cache-Control "no-cache, must-revalidate" always`，确保部署后浏览器立即加载新版本
- `.github/workflows/deploy.yml`：nginx 重启从 `nginx -s reload` 改为 `docker compose restart nginx`，原命令在容器内静默失败

**前端错误处理与 LiveKit 修复**（by windows-claude, 22:56~23:11）

- `app/static/user.js`：`postJson`/`getJson` 先检查 `response.ok` 再 `.json()`，避免 500 时 SyntaxError 掩盖真实错误；resize 加 150ms debounce 防抖
- LiveKit CDN 脚本改用 `defer` 加载，防止阻塞页面渲染

**移动端聊天气泡 UI**（by windows-claude, 23:45）

- `app/static/user.js`：新增 `appendChatMessage(role, text)` / `updateChatMessage(row, text)` 工具函数
- `askQuestion()` 按 `isChatMode()` 分支：移动端走聊天气泡，桌面端走 answer div

### 2026-03-11（四）—— codex 桌面端迭代（多轮）

### 2026-03-11（三）

**桌面端三次重构：去掉舞台内第二块大卡片，按真实截图回修断点**（by codex）

- `app/templates/user_desktop.html`：桌面端把主舞台恢复成单一视觉主体，不再在舞台中间并排塞第二块大说明卡
- `app/templates/user_desktop.html`：桌面断点从 `1260px` 下调到 `1180px`，避免常见桌面宽度下过早塌成单列
- `app/templates/user_desktop.html`：右侧提问舱收窄并简化按钮密度，减少“控制台感”
- `app/static/user.js`：同步调整桌面占位结构，并在视频未启用时隐藏无意义的保持会话 / 结束会话按钮

**桌面端四次回修：基于 Playwright 宽视口截图继续压缩视觉噪音**（by codex）

- `app/templates/user_desktop.html`：彻底移除主舞台右侧的大说明浮层，只保留顶部 HUD 与底部医生信息
- `app/templates/user_desktop.html`：把桌面断点进一步下调到 `1100px`，避免中等宽度桌面过早切成单列
- `app/templates/user_desktop.html`：继续收紧标题、副文案、右侧问答舱和按钮尺寸，让舞台占比更高

**桌面端五次回修：右侧从控制台改成真正聊天舱**（by codex）

- `app/templates/user_desktop.html`：桌面端右侧改为聊天气泡式会话舱，不再使用“回答框 + 资料框 + 一排按钮”的调试台布局
- `app/templates/user_desktop.html`：把发送动作收进底部输入壳，辅助按钮收成次级操作，整体更像正式产品而不是后台
- `app/static/user.js`：桌面端聊天模式下也同步写入隐藏 `answer`，保证朗读回答与现有逻辑继续可用

### 2026-03-12（四）

**桌面端六次回修：接入李勇医生公开职业照，主舞台从 demo 占位改成真实终端视觉**（by codex）

- `app/static/doctor-liyong-official.jpg`：接入杭州市第一人民医院公开专家页职业照，用于桌面主舞台承载真实医生形象
- `app/templates/user_desktop.html`：主舞台改成“真实职业照 + 右侧终端信息层”，移除残留英文标签，进一步减少说明型文案
- `app/templates/user_desktop.html`：补上内嵌 favicon，消除浏览器 404 小报错，减少细节上的 demo 感
- `app/static/user.js`：桌面占位结构改为真实职业照版本，视频未接入时也保持正式产品视觉

**桌面端七次回修：参考 Apple / OpenAI Health / One Medical / Ada Health 后继续做减法**（by codex）

- `app/templates/user_desktop.html`：继续压缩顶部与右侧信息密度，把舞台上方状态卡、右侧提问舱和舞台信息层都缩到更接近产品页而不是管理台
- `app/templates/user_desktop.html`：把舞台右侧四宫格小卡片改成一组更轻的胶囊状态，减少 dashboard 感
- `app/templates/user_desktop.html`：新增“快速提问”胶囊，让右侧提问舱在首屏更像真实入口，而不是一块空白聊天面板
- `app/static/user.js`：接入快速提问交互，点击后直接填充并发送问题，提升首屏可用性

**桌面端二次重构：一屏主视窗 + 未来感医疗终端**（by codex）

- `app/templates/user_desktop.html`：把首屏压成完整的一屏布局，避免进入页面后还需要整页下滚才能看到完整主视窗
- `app/templates/user_desktop.html`：移除不合适的英文风格标签，改为更正式的医疗终端表达，并把顶部区域收紧
- `app/templates/user_desktop.html`：增强深色玻璃、HUD 状态层、扫描线和轨道光环，让桌面端更接近未来感 AI 医疗界面
- `app/static/user.js`：同步调整桌面端占位说明和主视窗标题文案，让右侧提问舱与后续视频接入路径表达一致

**用户端视觉重构：Apple 极简 × AI 医疗**（by codex）

- `app/templates/user_desktop.html`：桌面端改为“大视频主区域 + 右侧问答窗”，减少长滚动和信息堆叠
- `app/templates/user_mobile.html`：移动端保留轻量结构，但补全资料与来源展示区域
- `app/static/user.js`：重构为跨桌面/手机安全渲染，修复移动端因 DOM 不存在导致的“公开职业信息 / 官方来源”不显示问题
- 整体视觉方向收敛为更接近 Apple 式极简层级，并叠加 AI 医疗氛围感

### 2026-03-11（三）

**HTTPS 上线骨架准备**（by codex）

- `docker-compose.prod.yml`：预留 `443:443` 端口和证书目录挂载
- `deploy/nginx/default.https.conf.example`：新增 HTTPS 版 Nginx 配置示例
- `deploy/nginx/certs/.gitkeep`：预留证书目录
- `deploy/HTTPS_SETUP.md`：新增 HTTPS 切换说明，方便服务器上直接落地

### 2026-03-11（三）

**控制台新增线上版本信息**（by codex）

- `/api/app-config`：新增 `runtime` 字段，返回当前线上版本、部署提交、部署分支与部署时间
- `/console`：新增“线上版本信息”区块，便于直接核对当前公网环境正在运行的提交
- `.github/workflows/deploy.yml`：自动部署时写入 `app/build_meta.json`，让容器内能读取本次部署元信息
- `.gitignore`：忽略 `app/build_meta.json`，避免部署期生成的元数据被误提交

### 2026-03-11（三）

**自动部署文档同步 + 并发保护**（by codex）

- `.github/workflows/deploy.yml`：新增 `concurrency`，避免连续 push 时重复部署互相打架
- `README.md`：更新自动部署记录，标明 webhook 方案已被 self-hosted runner 方案取代，避免文档继续误导

### 2026-03-11（三）

**Embedding 检索失败自动降级修复**（by codex）

- `app/knowledge.py`：补上 embedding 查询与索引构建异常时的自动回退，避免 OpenAI 向量接口抖动直接把 `/api/chat` 打成 500
- `.gitignore`：新增 `knowledge/.embed_cache.json`，避免本地磁盘缓存被误提交

### 2026-03-11（二）

**自动部署：GitHub Actions self-hosted runner**（by windows-claude + macos-codex）

- 新增 `.github/workflows/deploy.yml`：push main 时在服务器本机执行部署，不依赖入站 SSH 或公网 webhook 接口
- 用 `git fetch + reset --hard origin/main` 替代 `git pull`，保证始终对齐目标提交（Codex P2）
- `cancel-in-progress: false` 确保部署不被打断，避免 docker compose 中途被杀留烂摊子（Codex）
- 注：runner 必须以 root 安装，部署目录 `/root/doctor-avatar` 非 root 用户无法访问（Codex P1）

**安装 Runner（服务器执行一次）：**
```bash
mkdir -p /root/actions-runner && cd /root/actions-runner
curl -o runner.tar.gz -L https://github.com/actions/runner/releases/download/v2.322.0/actions-runner-linux-x64-2.322.0.tar.gz
tar xzf runner.tar.gz
# token 从 GitHub repo Settings → Actions → Runners → New self-hosted runner 获取
./config.sh --url https://github.com/kingcharleslzy-ai/doctor-avatar --token <TOKEN>
./svc.sh install && ./svc.sh start
```

### 2026-03-11（一）

**知识库检索升级：token 匹配 → OpenAI Embedding 语义检索**（by windows-claude）

- `app/knowledge.py`：用 `text-embedding-3-small` 替换原有 token 重叠计数
- 进程内 + 磁盘双层缓存（`knowledge/.embed_cache.json`），知识库未变动时不重复调用 API
- 无 OpenAI key 时自动降级为原 token 搜索，不影响本地开发
- `KnowledgeHit.score` 类型从 `int` 改为 `float`（余弦相似度 0~1）
