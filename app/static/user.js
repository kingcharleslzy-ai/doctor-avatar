"use strict";

const state = {
  appConfig: null,
  profile: null,
  ws: null,
  audioContext: null,
  playbackAt: 0,
  audioSources: new Set(),
  micStream: null,
  micSource: null,
  micProcessor: null,
  sessionActive: false,
  muted: false,
  currentAiBubble: null,
  currentAiText: "",
  timerStartedAt: 0,
  timerId: null,
  presenceId: `web-${Date.now()}-${Math.random().toString(16).slice(2)}`,
};

const $ = (id) => document.getElementById(id);

function setText(id, text) {
  const el = $(id);
  if (el) el.textContent = text;
}

function setVisible(id, visible) {
  const el = $(id);
  if (el) el.style.display = visible ? "" : "none";
}

function setVoiceStatus(text) {
  setText("voiceStatus", text);
  setText("connectionState", text || "语音待命");
  setText("vcStatus", text || "语音待命");
}

function setMode(text) {
  setText("modeState", text);
}

function setStage(kind) {
  const avatar = $("vcAvatar");
  const wave = $("vcWaveform");
  const dot = $("connDot");
  if (avatar) {
    avatar.classList.remove("vc-idle", "vc-listening", "vc-thinking", "vc-speaking");
    avatar.classList.add(`vc-${kind}`);
  }
  if (wave) {
    wave.classList.toggle("vc-wave-active", kind === "listening" || kind === "thinking");
    wave.classList.toggle("vc-wave-speak", kind === "speaking");
  }
  if (dot) dot.classList.toggle("live", state.sessionActive);
}

function appendMessage(role, text = "") {
  const history = $("chatHistory");
  if (!history) return null;
  const row = document.createElement("div");
  row.className = `msg-row ${role === "user" ? "user" : "ai"}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  row.appendChild(bubble);
  history.appendChild(row);
  history.scrollTop = history.scrollHeight;
  syncTranscript();
  return bubble;
}

function updateBubble(bubble, text) {
  if (!bubble) return;
  bubble.textContent = text;
  const history = $("chatHistory");
  if (history) history.scrollTop = history.scrollHeight;
  syncTranscript();
}

function resetCurrentAiBubble() {
  state.currentAiBubble = null;
  state.currentAiText = "";
}

function appendAiText(text) {
  const content = (text || "").trim();
  if (!content) return;
  if (!state.currentAiBubble) {
    state.currentAiBubble = appendMessage("ai", "");
    state.currentAiText = "";
  }
  if (state.currentAiText.endsWith(content) || state.currentAiText.includes(content)) {
    return;
  }
  state.currentAiText += content;
  updateBubble(state.currentAiBubble, state.currentAiText);
}

function syncTranscript() {
  const transcript = $("vcTranscriptContent");
  const history = $("chatHistory");
  if (transcript && history) {
    transcript.innerHTML = history.innerHTML;
    transcript.scrollTop = transcript.scrollHeight;
  }
}

async function loadAppConfig() {
  const response = await fetch("/api/app-config", { cache: "no-store" });
  if (!response.ok) throw new Error(`配置读取失败 HTTP ${response.status}`);
  state.appConfig = await response.json();
  const realtime = state.appConfig.doubao_realtime || {};
  if (realtime.configured) {
    setMode("MedFlow 实时语音");
    setVoiceStatus("语音待命");
  } else {
    setMode("MedFlow 未配置");
    setVoiceStatus(`缺少配置：${(realtime.missing_fields || []).join("、") || "DOUBAO_REALTIME_API_KEY"}`);
  }
}

async function loadProfile() {
  const response = await fetch("/api/doctor-profile", { cache: "no-store" });
  if (!response.ok) return;
  state.profile = await response.json();
  setText("heroTitle", `${state.profile.name || "李勇医生"} AI 医疗助手`);
  setText("heroDescription", state.profile.public_tagline || "专注耳鼻咽喉科常见问题的健康科普与就医建议，可通过文字或语音进行咨询。");
  setText("hospitalValue", state.profile.hospital || "杭州市第一人民医院");
  setText("clinicNote", state.profile.clinic_note || "提醒：仅供健康科普与就医参考，不替代面诊和处方。");
  setText("doctorBio", (state.profile.public_bio || []).join(" "));

  const focusTags = $("focusTags");
  if (focusTags) {
    focusTags.innerHTML = "";
    (state.profile.focus_areas || []).slice(0, 5).forEach((item) => {
      const span = document.createElement("span");
      span.textContent = item;
      focusTags.appendChild(span);
    });
  }
  const focusList = $("focusList");
  if (focusList) {
    focusList.innerHTML = "";
    (state.profile.clinical_strengths || []).slice(0, 4).forEach((item) => {
      const li = document.createElement("li");
      li.textContent = item;
      focusList.appendChild(li);
    });
  }
  const sources = $("officialSources");
  if (sources) {
    sources.innerHTML = "";
    (state.profile.official_sources || []).slice(0, 3).forEach((item) => {
      const a = document.createElement("a");
      a.href = item.url || "#";
      a.textContent = item.title || item.url || "资料来源";
      a.target = "_blank";
      a.rel = "noopener noreferrer";
      sources.appendChild(a);
    });
  }
}

function canStartRealtime() {
  return Boolean(state.appConfig?.doubao_realtime?.configured);
}

async function ensureAudioContext() {
  if (!state.audioContext) {
    const AudioCtor = window.AudioContext || window.webkitAudioContext;
    if (!AudioCtor) throw new Error("当前浏览器不支持 Web Audio。");
    state.audioContext = new AudioCtor();
  }
  if (state.audioContext.state === "suspended") {
    await state.audioContext.resume();
  }
  state.playbackAt = Math.max(state.playbackAt, state.audioContext.currentTime);
  return state.audioContext;
}

function startTimer() {
  state.timerStartedAt = Date.now();
  stopTimer();
  state.timerId = window.setInterval(() => {
    const seconds = Math.max(0, Math.floor((Date.now() - state.timerStartedAt) / 1000));
    const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
    const ss = String(seconds % 60).padStart(2, "0");
    setText("vcTimer", `${mm}:${ss}`);
  }, 500);
}

function stopTimer() {
  if (state.timerId) {
    window.clearInterval(state.timerId);
    state.timerId = null;
  }
}

function showOverlay(show) {
  const overlay = $("voiceCallOverlay");
  if (overlay) overlay.style.display = show ? "flex" : "none";
  if (show) startTimer();
  else stopTimer();
}

async function startRealtimeSession({ withMic = false } = {}) {
  if (state.sessionActive && state.ws?.readyState === WebSocket.OPEN) {
    if (withMic) await startMic();
    return;
  }
  if (!canStartRealtime()) {
    await loadAppConfig();
    if (!canStartRealtime()) {
      setVoiceStatus("MedFlow 实时语音未配置");
      return;
    }
  }

  await ensureAudioContext();
  resetCurrentAiBubble();
  stopPlayback();
  setMode("正在连接 MedFlow");
  setVoiceStatus("正在连接...");
  setStage("thinking");
  showOverlay(withMic);
  setVisible("startConsultBtn", false);
  setVisible("endConsultBtn", true);

  const protocol = location.protocol === "https:" ? "wss" : "ws";
  const mode = withMic ? "voice" : "text";
  const ws = new WebSocket(`${protocol}://${location.host}/ws/doubao/realtime?mode=${mode}`);
  state.ws = ws;
  ws.binaryType = "arraybuffer";

  ws.addEventListener("open", async () => {
    state.sessionActive = true;
    setMode("MedFlow 实时语音");
    setVoiceStatus(withMic ? "正在打开麦克风..." : "会话已连接");
    setStage(withMic ? "listening" : "idle");
    if (withMic) await startMic();
  });

  ws.addEventListener("message", (event) => {
    try {
      handleRealtimeMessage(JSON.parse(event.data));
    } catch (err) {
      console.warn("Realtime parse failed:", err);
    }
  });

  ws.addEventListener("close", () => {
    state.sessionActive = false;
    setVisible("startConsultBtn", true);
    setVisible("endConsultBtn", false);
    setMode("语音待命");
    setVoiceStatus("语音待命");
    setStage("idle");
    showOverlay(false);
    stopMic();
    resetCurrentAiBubble();
  });

  ws.addEventListener("error", () => {
    setVoiceStatus("MedFlow 连接异常");
    setStage("idle");
  });

  await waitForSocketOpen(ws);
}

function waitForSocketOpen(ws) {
  if (ws.readyState === WebSocket.OPEN) return Promise.resolve();
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      cleanup();
      reject(new Error("MedFlow 连接超时"));
    }, 10000);
    function cleanup() {
      window.clearTimeout(timer);
      ws.removeEventListener("open", onOpen);
      ws.removeEventListener("error", onError);
      ws.removeEventListener("close", onClose);
    }
    function onOpen() {
      cleanup();
      resolve();
    }
    function onError() {
      cleanup();
      reject(new Error("MedFlow 连接异常"));
    }
    function onClose() {
      cleanup();
      reject(new Error("MedFlow 连接已关闭"));
    }
    ws.addEventListener("open", onOpen);
    ws.addEventListener("error", onError);
    ws.addEventListener("close", onClose);
  });
}

function handleRealtimeMessage(message) {
  if (message.type === "error") {
    setVoiceStatus(message.message || "MedFlow 实时语音异常");
    appendMessage("ai", message.message || "连接异常，请稍后重试。");
    setStage("idle");
    return;
  }
  if (message.type === "status") {
    if (message.status === "session_started") setVoiceStatus(state.muted ? "已静音" : "请直接说话");
    if (message.status === "finished") endRealtimeSession({ closeSocket: false });
    if (message.status === "user_exit_intent") setVoiceStatus("已识别到结束意图");
    return;
  }
  if (message.type === "rag_context") {
    setVoiceStatus(message.stage_label ? `问诊阶段：${message.stage_label}` : "正在整理资料");
    setStage("thinking");
    resetCurrentAiBubble();
    return;
  }
  if (message.type === "asr") {
    const text = (message.text || "").trim();
    if (!text) return;
    if (message.is_interim) {
      setVoiceStatus(`正在听：${text}`);
    } else {
      appendMessage("user", text);
      setVoiceStatus("正在生成回答...");
      setStage("thinking");
      resetCurrentAiBubble();
    }
    return;
  }
  if (message.type === "chat") {
    appendAiText(message.content || "");
    setStage("speaking");
    setVoiceStatus("正在回答");
    return;
  }
  if (message.type === "chat_end") {
    resetCurrentAiBubble();
    setVoiceStatus(state.muted ? "已静音" : "请继续说话");
    setStage(state.muted ? "idle" : "listening");
    return;
  }
  if (message.type === "tts_start") {
    if (message.text) appendAiText(message.text);
    setStage("speaking");
    return;
  }
  if (message.type === "tts_end") {
    setStage(state.muted ? "idle" : "listening");
    return;
  }
  if (message.type === "audio") {
    playPcm16(message.audio, message.sample_rate || 24000);
  }
}

async function sendTextFromBox() {
  const input = $("message");
  const content = (input?.value || "").trim();
  if (!content) return;
  await startRealtimeSession({ withMic: false });
  if (!state.ws || state.ws.readyState !== WebSocket.OPEN) {
    setVoiceStatus("连接尚未就绪，请稍后重试");
    return;
  }
  input.value = "";
  appendMessage("user", content);
  resetCurrentAiBubble();
  setVoiceStatus("正在生成回答...");
  setStage("thinking");
  state.ws.send(JSON.stringify({ type: "text", content }));
}

async function startMic() {
  if (state.micStream) return;
  const context = await ensureAudioContext();
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      channelCount: 1,
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });
  state.micStream = stream;
  state.micSource = context.createMediaStreamSource(stream);
  state.micProcessor = context.createScriptProcessor(4096, 1, 1);
  state.micProcessor.onaudioprocess = (event) => {
    event.outputBuffer.getChannelData(0).fill(0);
    if (!state.ws || state.ws.readyState !== WebSocket.OPEN || state.muted) return;
    const pcm = downsampleToPcm16(event.inputBuffer.getChannelData(0), context.sampleRate, 16000);
    if (pcm.byteLength > 0) state.ws.send(pcm);
  };
  state.micSource.connect(state.micProcessor);
  state.micProcessor.connect(context.destination);
  setVoiceStatus("请直接说话");
  setStage("listening");
}

function stopMic() {
  if (state.micProcessor) {
    state.micProcessor.disconnect();
    state.micProcessor.onaudioprocess = null;
    state.micProcessor = null;
  }
  if (state.micSource) {
    state.micSource.disconnect();
    state.micSource = null;
  }
  if (state.micStream) {
    state.micStream.getTracks().forEach((track) => track.stop());
    state.micStream = null;
  }
}

function downsampleToPcm16(input, inputRate, outputRate) {
  if (inputRate === outputRate) return floatToInt16(input).buffer;
  const ratio = inputRate / outputRate;
  const length = Math.floor(input.length / ratio);
  const result = new Float32Array(length);
  for (let i = 0; i < length; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(Math.floor((i + 1) * ratio), input.length);
    let sum = 0;
    for (let j = start; j < end; j += 1) sum += input[j];
    result[i] = sum / Math.max(1, end - start);
  }
  return floatToInt16(result).buffer;
}

function floatToInt16(input) {
  const output = new Int16Array(input.length);
  for (let i = 0; i < input.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, input[i]));
    output[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
  }
  return output;
}

async function playPcm16(base64Audio, sampleRate) {
  if (!base64Audio) return;
  const context = await ensureAudioContext();
  const binary = atob(base64Audio);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  const samples = new Int16Array(bytes.buffer);
  const buffer = context.createBuffer(1, samples.length, sampleRate);
  const channel = buffer.getChannelData(0);
  for (let i = 0; i < samples.length; i += 1) channel[i] = samples[i] / 32768;
  const source = context.createBufferSource();
  source.buffer = buffer;
  source.connect(context.destination);
  const startAt = Math.max(context.currentTime + 0.02, state.playbackAt);
  source.start(startAt);
  state.playbackAt = startAt + buffer.duration;
  state.audioSources.add(source);
  source.onended = () => state.audioSources.delete(source);
}

function stopPlayback() {
  state.audioSources.forEach((source) => {
    try { source.stop(); } catch (_) {}
  });
  state.audioSources.clear();
  if (state.audioContext) state.playbackAt = state.audioContext.currentTime;
}

function sendInterrupt() {
  stopPlayback();
  if (state.ws?.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify({ type: "interrupt" }));
  }
  setVoiceStatus(state.sessionActive ? "已停止播放" : "语音待命");
  setStage(state.sessionActive && !state.muted ? "listening" : "idle");
}

function toggleMute() {
  state.muted = !state.muted;
  const button = $("vcMuteBtn");
  if (button) {
    button.classList.toggle("vc-muted", state.muted);
    button.title = state.muted ? "取消静音" : "静音";
  }
  setVoiceStatus(state.muted ? "已静音" : "请直接说话");
  setStage(state.muted ? "idle" : "listening");
}

function endRealtimeSession({ closeSocket = true } = {}) {
  stopPlayback();
  stopMic();
  showOverlay(false);
  if (closeSocket && state.ws?.readyState === WebSocket.OPEN) {
    state.ws.send(JSON.stringify({ type: "finish" }));
    state.ws.close();
  }
  state.ws = null;
  state.sessionActive = false;
  state.muted = false;
  setVisible("startConsultBtn", true);
  setVisible("endConsultBtn", false);
  setMode("语音待命");
  setVoiceStatus("语音待命");
  setStage("idle");
  resetCurrentAiBubble();
}

function bindEvents() {
  $("askBtn")?.addEventListener("click", sendTextFromBox);
  $("message")?.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key === "Enter") {
      event.preventDefault();
      sendTextFromBox();
    }
  });
  $("startConsultBtn")?.addEventListener("click", () => startRealtimeSession({ withMic: true }));
  $("voiceInputBtn")?.addEventListener("click", () => startRealtimeSession({ withMic: true }));
  $("endConsultBtn")?.addEventListener("click", () => endRealtimeSession());
  $("stopSpeechBtn")?.addEventListener("click", sendInterrupt);
  $("vcEndBtn")?.addEventListener("click", () => endRealtimeSession());
  $("vcMuteBtn")?.addEventListener("click", toggleMute);
  $("vcTranscriptBtn")?.addEventListener("click", () => {
    const panel = $("vcTranscriptPanel");
    if (!panel) return;
    panel.style.display = panel.style.display === "none" ? "block" : "none";
    syncTranscript();
  });
  $("vcTranscriptClose")?.addEventListener("click", () => setVisible("vcTranscriptPanel", false));
  window.addEventListener("beforeunload", () => {
    if (state.ws?.readyState === WebSocket.OPEN) state.ws.send(JSON.stringify({ type: "finish" }));
  });
}

async function sendPresence() {
  try {
    await fetch("/api/ops/presence", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: state.presenceId }),
    });
  } catch (_) {}
}

async function init() {
  bindEvents();
  const history = $("chatHistory");
  if (history) history.innerHTML = "";
  appendMessage("ai", "您好，我是李勇医生的 AI 助手，专注耳鼻咽喉科常见问题的健康科普与就医建议。请问有什么可以帮您？");
  try {
    await Promise.all([loadAppConfig(), loadProfile()]);
  } catch (error) {
    setVoiceStatus(error.message || "初始化失败");
  }
  setStage("idle");
  await sendPresence();
  window.setInterval(sendPresence, 60_000);
}

document.addEventListener("DOMContentLoaded", init);
