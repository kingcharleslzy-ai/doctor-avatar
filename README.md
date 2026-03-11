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

## 当前前端能力

用户端现在已经可以：

- 展示李勇医生公开职业资料与专科方向
- 按设备自动切换桌面版和手机版
- 提供一个面向用户的文本提问入口
- 保留视频分身入口与接口，但当前默认不启用高成本的实时视频链路

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

### 2026-03-11（四）

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

### 2026-03-11（四-4）

**HTTPS 上线骨架准备**（by codex）

- `docker-compose.prod.yml`：预留 `443:443` 端口和证书目录挂载
- `deploy/nginx/default.https.conf.example`：新增 HTTPS 版 Nginx 配置示例
- `deploy/nginx/certs/.gitkeep`：预留证书目录
- `deploy/HTTPS_SETUP.md`：新增 HTTPS 切换说明，方便服务器上直接落地

### 2026-03-11（四-3）

**控制台新增线上版本信息**（by codex）

- `/api/app-config`：新增 `runtime` 字段，返回当前线上版本、部署提交、部署分支与部署时间
- `/console`：新增“线上版本信息”区块，便于直接核对当前公网环境正在运行的提交
- `.github/workflows/deploy.yml`：自动部署时写入 `app/build_meta.json`，让容器内能读取本次部署元信息
- `.gitignore`：忽略 `app/build_meta.json`，避免部署期生成的元数据被误提交

### 2026-03-11（四-2）

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
