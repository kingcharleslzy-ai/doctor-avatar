# 医生虚拟人 MVP

这是一个新的独立项目，用来搭建你爸的医生虚拟人第一版。

当前版本包含 3 层：

1. `OpenAI` 问答层
2. `本地知识库` 检索层
3. `HeyGen / LiveAvatar` 会话接口层

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

## 需要填写的内容

### 1. `.env`

- `OPENAI_API_KEY`
- `HEYGEN_API_KEY`

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

## 下一步建议

1. 先把你爸的资料填完整
2. 连续测试 30 到 50 个高频问题
3. 调整风格和禁答规则
4. 再接入真正的 HeyGen 前端播放与实时语音
