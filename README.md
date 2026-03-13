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
- `DOCTOR_MEMORY_DB_PATH`
- `DOCTOR_MEMORY_BOOTSTRAP`

如果你要保护公网控制台，这两个必须填写。

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

控制台现在已经可以：

- 创建 LiveAvatar token
- 启动 session
- 用返回的 `livekit_url` 和 `livekit_client_token` 直接连接 LiveKit
- 自动请求麦克风并订阅远端音视频
- 显示 session 信息和事件日志
- 显示后端当前采用的 LiveAvatar 预设配置
- 单独调试 OpenAI 问答层

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
