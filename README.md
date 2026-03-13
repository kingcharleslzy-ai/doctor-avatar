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

当前已为“阿里云主站 + 家里 4090D 渲染机”准备了 `frp` 的 SSH 通道方案：

- 阿里云服务器运行 `frps`
- 家里 4090D 机器运行 `frpc`
- 默认端口：
  - `7000/tcp`：`frps` 控制通道
  - `6000/tcp`：映射后的家里机器 `ssh`

仓库内文件：

- `deploy/frp/frps.toml`
- `deploy/frp/frps.service`
- `.github/workflows/setup-frps.yml`

注意：

- 真正的 `FRP_AUTH_TOKEN` 不会写进仓库，而是放在 GitHub Secret：
  - `FRP_AUTH_TOKEN`
- 阿里云安全组还需要放行：
  - `7000/tcp`
  - `6000/tcp`

如果 `setup-frps.yml` 已成功运行，后续只要家里机器的 `frpc` 也连上，就可以通过：

```bash
ssh -p 6000 charles@47.250.168.45
```

从外网进入家里的 4090D 机器。

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

## 需要填写的内容

### 1. `.env`

- `OPENAI_API_KEY`
- `HEYGEN_API_KEY`
- `HEYGEN_AVATAR_ID`
- `HEYGEN_VOICE_ID`
- `HEYGEN_CONTEXT_ID`

这些 HeyGen 参数现在默认走后端配置，前端和调试页都不再要求手填。

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
2. 用真实 `HEYGEN_AVATAR_ID` 和 `HEYGEN_VOICE_ID` 联调视频效果
3. 连续测试 30 到 50 个高频耳鼻咽喉科问题
4. 再补用户端字幕、会话摘要和隐私提示细节

## CHANGELOG

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
