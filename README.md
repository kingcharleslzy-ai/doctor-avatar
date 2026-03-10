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
- 控制台：`/console`

## 需要填写的内容

### 1. `.env`

- `OPENAI_API_KEY`
- `HEYGEN_API_KEY`
- `HEYGEN_AVATAR_ID`
- `HEYGEN_VOICE_ID`
- `HEYGEN_CONTEXT_ID`

这些 HeyGen 参数现在默认走后端配置，前端和调试页都不再要求手填。

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
- 由后端自动发起 LiveAvatar 视频会话
- 在不暴露内部参数的情况下连接远端视频
- 提供一个面向用户的文本提问入口

控制台现在已经可以：

- 创建 LiveAvatar token
- 启动 session
- 用返回的 `livekit_url` 和 `livekit_client_token` 直接连接 LiveKit
- 自动请求麦克风并订阅远端音视频
- 显示 session 信息和事件日志
- 显示后端当前采用的 LiveAvatar 预设配置
- 单独调试 OpenAI 问答层

## 下一步建议

1. 把你爸的内部口吻、常见回答和禁答规则补进知识库
2. 用真实 `HEYGEN_AVATAR_ID` 和 `HEYGEN_VOICE_ID` 联调视频效果
3. 连续测试 30 到 50 个高频耳鼻咽喉科问题
4. 再补用户端字幕、会话摘要和隐私提示细节
