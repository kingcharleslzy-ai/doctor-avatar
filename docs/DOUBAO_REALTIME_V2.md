# 豆包端到端实时语音接入说明

本文记录当前数字人页面的唯一主链路。前端、后台和部署文档只维护豆包实时语音方案。

## 1. 官方能力映射

火山官方「端到端实时语音大模型API接入文档」中，控制台可见字段对应到当前代码如下：

| 控制台/文档字段 | 当前配置 | 说明 |
|---|---|---|
| 基础人设 | `DOUBAO_REALTIME_BOT_NAME` / `dialog.bot_name` | O/O2.0 支持，最长 20 字符 |
| 背景人设 | `DOUBAO_REALTIME_SYSTEM_ROLE` / `dialog.system_role` | 基础医疗边界和角色设定 |
| 模型对话风格 | `DOUBAO_REALTIME_SPEAKING_STYLE` / `dialog.speaking_style` | 控制语气、简洁度、表达风格 |
| 开场白 | `DOUBAO_REALTIME_OPENING_REMARK` / `SayHello(300)` | Session started 后主动发送 |
| 音色 | `DOUBAO_REALTIME_SPEAKER` / `tts.speaker` | 默认清爽沉稳男声 |
| 联网能力 | `DOUBAO_REALTIME_ENABLE_WEBSEARCH` / `enable_volc_websearch` | 默认关闭 |
| ASR 停顿判断 | `DOUBAO_REALTIME_END_SMOOTH_WINDOW_MS` / `asr.extra.end_smooth_window_ms` | 默认 1200ms |
| ASR 热词 | `DOUBAO_REALTIME_HOTWORDS` / `asr.extra.context.hotwords` | 耳鼻喉常见词 |
| 用户退出意图 | `DOUBAO_REALTIME_ENABLE_USER_QUERY_EXIT` | 开启后 `TTSEnded` 可能带退出信号 |
| 打断体验 | `ASRInfo(450)` -> 前端停止本地播报 | `keep_alive` 模式下优先使用服务端首字识别信号，不用音量阈值乱发 `ClientInterrupt` |

## 2. 当前请求流程

```text
StartConnection
StartSession
  tts.speaker/audio_config
  asr.extra.end_smooth_window_ms/hotwords
  dialog.bot_name/system_role/speaking_style/extra
SayHello

用户语音:
  TaskRequest PCM 16k -> ASRResponse -> 后端问诊状态机
  UpdateConfig -> 单问题/阶段总结走 SayHello
  复杂说明才走 ChatRAGText external_rag
  TTSResponse PCM 24k -> 浏览器播放

用户文字:
  UpdateConfig -> 单问题/阶段总结走 SayHello
  复杂说明才走 ChatTextQuery/ChatRAGText
  TTSResponse PCM 24k -> 浏览器播放
```

语音和文字路径都优先由后端状态机决定本轮唯一问题或阶段总结，再用 `SayHello` 输出语音；只有需要结合外部资料做复杂说明时才使用 `ChatRAGText`。这样能减少实时语音中模型追加多个问题、重复追问或偏离主诉。

麦克风常开使用 `input_mod=keep_alive`。前端按官方建议把上行音频切成 16kHz PCM、20ms 左右的小包；当服务端返回 `ASRInfo(450)` 表示识别到用户首字时，前端停止本地播报并等待新的 ASR 结果。`ClientInterrupt(515)` 主要保留给 `push_to_talk` 场景，当前页面不把普通环境声或音量阈值直接当成上游打断事件。

## 3. 为什么默认关闭联网

医疗问诊页更需要口径稳定。当前项目优先使用：

- `knowledge/*.md`
- SQLite 医生资料库
- `app/consultation_flow.py` 的问诊状态机

联网搜索可用于非诊疗类实时资料，但要单独配置融合搜索 API Key，并在合同和页面口径上明确它不是医疗诊断依据。

## 4. 关键文件

- `app/doubao_realtime.py`：帧协议、鉴权、StartSession payload。
- `app/main.py`：浏览器 WebSocket 到豆包 WebSocket 的代理。
- `app/consultation_flow.py`：每轮问诊阶段、`UpdateConfig`、`external_rag`。
- `app/static/user.js`：麦克风采集、PCM 下采样、音频播放、文字/语音事件处理。

## 5. 常用验证

```bash
npm ci
python -m compileall app scripts/validate_doubao_realtime.py scripts/validate_doubao_cloud.py
node --check app/static/user.js
npm run validate:consultation-flow
npm run validate:doubao-realtime
npm run validate:doubao-cloud
npm run validate:user
```

官方文档：<https://www.volcengine.com/docs/6561/1594356?lang=zh>
