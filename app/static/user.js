const state = {
  room: null,
  sessionToken: "",
  conversation: [],
  doctorProfile: null,
  appConfig: null,
  mediaRecorder: null,
  isRecording: false,
  microphonePrimed: false,
  presenceSessionId: "",
  dittoWs: null,
  avatarRafId: 0,
  avatarAudioContext: null,
  avatarAnalyser: null,
  avatarMonitorSource: null,
  avatarLevel: 0,
  avatarMode: "idle",
  experimentalVideoEnabled: false,
  askInFlight: false,
  voiceVadRafId: 0,
  voiceRecordStartedAt: 0,
  voiceSpeechDetectedAt: 0,
  voiceLastSpeechAt: 0,
  voiceHasSpeech: false,
  recordingStopReason: "manual",
  voiceSessionActive: false, /* true only when user initiated voice input, enables auto-listen after answer */
};

function hasLiveAvatarMode() {
  return Boolean(state.appConfig?.video_avatar_enabled);
}

function hasDittoMode() {
  return Boolean(state.appConfig?.ditto_enabled);
}

function isExperimentalVideoMode() {
  try {
    const urlFlag = new URLSearchParams(window.location.search).get("expvideo");
    if (urlFlag === "1") return true;
    return window.localStorage.getItem("doctor-avatar-experimental-video") === "1";
  } catch (_) {
    return false;
  }
}

function $(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  const el = $(id);
  if (el) {
    el.textContent = value;
  }
}

function ensurePresenceSessionId() {
  if (state.presenceSessionId) return state.presenceSessionId;
  const storageKey = "doctor-avatar-presence-id";
  let value = "";
  try {
    value = window.localStorage.getItem(storageKey) || "";
    if (!value) {
      value = `presence-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
      window.localStorage.setItem(storageKey, value);
    }
  } catch (_) {
    value = `presence-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }
  state.presenceSessionId = value;
  return value;
}

// 只更新按钮内有实际内容的文字节点，保留 SVG 图标不被清除
function setBtnText(btn, text) {
  if (!btn) return;
  let tn = [...btn.childNodes].find(n => n.nodeType === Node.TEXT_NODE && n.textContent.trim());
  if (tn) { tn.textContent = "\u00a0" + text; }
  else { btn.appendChild(document.createTextNode("\u00a0" + text)); }
}

function isMobileLayout() {
  return window.innerWidth <= 920;
}

// 聊天气泡模式（移动端）
function isChatMode() {
  return !!$("chatHistory");
}

function appendChatMessage(role, text) {
  const history = $("chatHistory");
  if (!history) return null;
  const row = document.createElement("div");
  row.className = `msg-row ${role}`;
  if (role === "ai") {
    const label = document.createElement("div");
    label.className = "ai-label";
    label.textContent = "AI 医疗助手";
    row.appendChild(label);
  }
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  if (text === null) {
    bubble.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div>';
  } else {
    bubble.textContent = text;
  }
  row.appendChild(bubble);
  history.appendChild(row);
  history.scrollTop = history.scrollHeight;
  return row;
}

function updateChatMessage(row, text) {
  if (!row) return;
  const bubble = row.querySelector(".bubble");
  if (bubble) bubble.textContent = text;
  const history = $("chatHistory");
  if (history) history.scrollTop = history.scrollHeight;
}

function currentProfile() {
  return state.doctorProfile || {};
}

function profileName() {
  return currentProfile().name || "李勇";
}

function profileTitle() {
  return currentProfile().title || "主任医师 / 教授 / 硕士生导师";
}

function profileHospital() {
  return currentProfile().hospital || "杭州市第一人民医院";
}

function profileDepartment() {
  return currentProfile().department || "耳鼻咽喉科";
}

function setConversationBusy(isBusy) {
  state.askInFlight = Boolean(isBusy);
  ["askBtn", "voiceInputBtn", "speakAnswerBtn"].forEach((id) => {
    const el = $(id);
    if (el) {
      el.disabled = state.askInFlight;
    }
  });
  if (!hasLiveAvatarMode()) {
    const startBtn = $("startConsultBtn");
    if (startBtn) {
      startBtn.disabled = state.askInFlight;
    }
  }
}

function updatePrimaryActionUi() {
  const startBtn = $("startConsultBtn");
  if (!startBtn) return;
  if (hasLiveAvatarMode()) {
    setBtnText(startBtn, state.room ? "视频会话中" : "视频通话");
    return;
  }
  setBtnText(startBtn, state.isRecording ? "结束说话" : "开始问诊");
}

function avatarSvg() {
  return `<svg viewBox="0 0 360 480" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" preserveAspectRatio="xMidYMid meet" style="width:100%;height:100%;display:block">
    <defs>
      <linearGradient id="avatarCore" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#dcecff" />
        <stop offset="100%" stop-color="#9bb6cc" />
      </linearGradient>
      <linearGradient id="avatarCoat" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#f7fbff" />
        <stop offset="100%" stop-color="#d1dde8" />
      </linearGradient>
      <linearGradient id="avatarAccent" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" stop-color="#8ef0e8" />
        <stop offset="100%" stop-color="#4b7cff" />
      </linearGradient>
    </defs>
    <g opacity="0.65">
      <circle cx="180" cy="192" r="106" fill="none" stroke="url(#avatarAccent)" stroke-width="1.3">
        <animate attributeName="r" values="102;112;102" dur="4.2s" repeatCount="indefinite"/>
        <animate attributeName="opacity" values="0.32;0.12;0.32" dur="4.2s" repeatCount="indefinite"/>
      </circle>
      <circle cx="180" cy="192" r="134" fill="none" stroke="url(#avatarAccent)" stroke-width="0.9" opacity="0.22">
        <animate attributeName="r" values="130;148;130" dur="4.2s" begin="0.7s" repeatCount="indefinite"/>
        <animate attributeName="opacity" values="0.22;0.05;0.22" dur="4.2s" begin="0.7s" repeatCount="indefinite"/>
      </circle>
    </g>
    <g id="avatarHeadGroup">
      <animateTransform attributeName="transform" type="translate" values="0 0; 0 -5; 0 0" dur="4.6s" repeatCount="indefinite"/>
      <path d="M96 344 C100 286 130 248 180 240 C230 248 260 286 264 344 L264 458 L96 458 Z" fill="url(#avatarCoat)" />
      <path d="M155 244 L168 314 L192 314 L205 244 L180 260 Z" fill="rgba(255,255,255,0.52)" />
      <rect x="164" y="203" width="32" height="44" rx="14" fill="url(#avatarCore)" />
      <ellipse cx="180" cy="162" rx="58" ry="64" fill="url(#avatarCore)" />
      <path d="M126 150 Q128 94 180 92 Q232 94 234 150 Q222 114 180 114 Q138 114 126 150 Z" fill="#22303e" opacity="0.92" />
      <ellipse cx="125" cy="168" rx="10" ry="15" fill="url(#avatarCore)" />
      <ellipse cx="235" cy="168" rx="10" ry="15" fill="url(#avatarCore)" />
      <path d="M147 151 Q160 144 173 149" fill="none" stroke="#22303e" stroke-width="2.4" stroke-linecap="round" />
      <path d="M187 149 Q200 144 213 151" fill="none" stroke="#22303e" stroke-width="2.4" stroke-linecap="round" />
      <ellipse id="avatarLeftEye" cx="160" cy="168" rx="9" ry="8.5" fill="#1c2d40">
        <animate attributeName="ry" values="8.5;8.5;1.2;8.5;8.5" dur="5.3s" repeatCount="indefinite"/>
      </ellipse>
      <ellipse id="avatarRightEye" cx="200" cy="168" rx="9" ry="8.5" fill="#1c2d40">
        <animate attributeName="ry" values="8.5;8.5;1.2;8.5;8.5" dur="5.3s" begin="0.05s" repeatCount="indefinite"/>
      </ellipse>
      <circle cx="162" cy="165" r="2.6" fill="#ffffff" opacity="0.82" />
      <circle cx="202" cy="165" r="2.6" fill="#ffffff" opacity="0.82" />
      <path d="M176 183 Q180 190 184 183" fill="none" stroke="rgba(16,24,40,0.22)" stroke-width="1.8" stroke-linecap="round" />
      <ellipse id="avatarMouth" cx="180" cy="206" rx="16" ry="3.6" fill="#24415e" />
    </g>
    <g opacity="0.72">
      <circle cx="105" cy="136" r="3.4" fill="#8ef0e8">
        <animate attributeName="cy" values="136;122;136" dur="2.8s" repeatCount="indefinite"/>
      </circle>
      <circle cx="272" cy="156" r="2.4" fill="#4b7cff">
        <animate attributeName="cy" values="156;141;156" dur="3.2s" repeatCount="indefinite"/>
      </circle>
      <circle cx="88" cy="256" r="2.8" fill="#8ef0e8">
        <animate attributeName="cy" values="256;238;256" dur="3.1s" repeatCount="indefinite"/>
      </circle>
    </g>
  </svg>`;
}

function avatarModeLabel(mode) {
  return ({
    idle: "待命中",
    listening: "正在聆听",
    thinking: "理解问题中",
    speaking: "正在回答",
  })[mode] || "待命中";
}

function avatarModeHint(mode, hint = "") {
  if (hint) return hint;
  return ({
    idle: "你可以直接输入文字，或点语音按钮开始说话。",
    listening: "正在采集你的声音，停下后会自动转写。",
    thinking: "正在整理问题和资料，请稍候。",
    speaking: "语音已开始播放，口型和状态会同步变化。",
  })[mode] || "";
}

function avatarStageMarkup(mode = "idle", hint = "") {
  const focus = (state.doctorProfile?.focus_areas || [])[0] || profileDepartment();
  return `
    <div style="position:relative;width:100%;height:100%;overflow:hidden;border-radius:inherit;background:
      radial-gradient(circle at 18% 12%, rgba(124,226,218,0.18), transparent 22%),
      radial-gradient(circle at 82% 10%, rgba(75,124,255,0.16), transparent 24%),
      linear-gradient(180deg, #0f1723 0%, #08101a 100%);">
      <div style="position:absolute;inset:0;background-image:
        linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px);
        background-size: 32px 32px; opacity:.45;"></div>
      <div style="position:absolute;inset:18px;border-radius:18px;border:1px solid rgba(255,255,255,.08);pointer-events:none;"></div>
      <div style="position:absolute;top:18px;left:18px;display:flex;gap:8px;align-items:center;z-index:2;">
        <div style="padding:6px 11px;border-radius:999px;background:rgba(124,226,218,.10);color:#aaf4ef;border:1px solid rgba(124,226,218,.18);font-size:10px;letter-spacing:.12em;text-transform:uppercase;">Web 2D Avatar</div>
        <div id="avatarModePill" style="padding:6px 11px;border-radius:999px;background:rgba(255,255,255,.07);color:#d7e7fb;border:1px solid rgba(255,255,255,.09);font-size:11px;">${avatarModeLabel(mode)}</div>
      </div>
      <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:38px 26px 124px;">
        <div style="width:min(80%, 480px);max-width:100%;aspect-ratio:3/4;">
          ${avatarSvg()}
        </div>
      </div>
      <div style="position:absolute;left:20px;right:20px;bottom:22px;display:grid;gap:12px;z-index:2;">
        <div style="display:flex;gap:8px;flex-wrap:wrap;">
          <span style="padding:5px 10px;border-radius:999px;background:rgba(255,255,255,.06);color:#d7e7fb;border:1px solid rgba(255,255,255,.08);font-size:11px;">${profileHospital()}</span>
          <span style="padding:5px 10px;border-radius:999px;background:rgba(255,255,255,.06);color:#d7e7fb;border:1px solid rgba(255,255,255,.08);font-size:11px;">${profileDepartment()}</span>
          <span style="padding:5px 10px;border-radius:999px;background:rgba(255,255,255,.06);color:#d7e7fb;border:1px solid rgba(255,255,255,.08);font-size:11px;">${focus}</span>
        </div>
        <div style="padding:14px 16px 16px;border-radius:18px;background:linear-gradient(180deg, rgba(8,14,22,.10), rgba(8,14,22,.42));border:1px solid rgba(255,255,255,.08);backdrop-filter: blur(12px);">
          <div style="display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px;">
            <div>
              <div style="font-size:12px;letter-spacing:.12em;color:rgba(187,212,237,.72);text-transform:uppercase;">${profileName()} 医生语音助手</div>
              <div id="avatarModeText" style="margin-top:4px;font-size:24px;font-weight:700;color:#f5fbff;letter-spacing:-.04em;">${avatarModeLabel(mode)}</div>
            </div>
            <div style="display:flex;align-items:flex-end;gap:4px;height:30px;">
              <span class="avatar-meter-bar" style="width:4px;height:12px;border-radius:999px;background:rgba(142,240,232,.35);"></span>
              <span class="avatar-meter-bar" style="width:4px;height:18px;border-radius:999px;background:rgba(142,240,232,.55);"></span>
              <span class="avatar-meter-bar" style="width:4px;height:24px;border-radius:999px;background:rgba(75,124,255,.75);"></span>
              <span class="avatar-meter-bar" style="width:4px;height:16px;border-radius:999px;background:rgba(142,240,232,.55);"></span>
            </div>
          </div>
          <div id="avatarModeHint" style="font-size:13px;line-height:1.7;color:rgba(216,232,245,.82);">${avatarModeHint(mode, hint)}</div>
        </div>
      </div>
    </div>
  `;
}

function cacheAvatarElements() {
  state.avatarElements = {
    mouth: document.getElementById("avatarMouth"),
    modeText: document.getElementById("avatarModeText"),
    modeHint: document.getElementById("avatarModeHint"),
    modePill: document.getElementById("avatarModePill"),
    meterBars: [...document.querySelectorAll(".avatar-meter-bar")],
  };
}

function setAvatarLevel(level = 0) {
  state.avatarLevel = Math.max(0, Math.min(1, level));
  const mouth = state.avatarElements?.mouth;
  if (mouth) {
    mouth.setAttribute("ry", `${3.6 + state.avatarLevel * 12}`);
    mouth.setAttribute("rx", `${16 - state.avatarLevel * 2}`);
  }
  (state.avatarElements?.meterBars || []).forEach((bar, index) => {
    const boost = Math.max(0.15, state.avatarLevel * (0.7 + index * 0.16));
    bar.style.transform = `scaleY(${boost})`;
    bar.style.transformOrigin = "center bottom";
    bar.style.opacity = `${0.32 + boost * 0.68}`;
  });
}

function setAvatarMode(mode = "idle", hint = "") {
  state.avatarMode = mode;
  const label = avatarModeLabel(mode);
  const message = avatarModeHint(mode, hint);
  if (state.avatarElements?.modeText) state.avatarElements.modeText.textContent = label;
  if (state.avatarElements?.modeHint) state.avatarElements.modeHint.textContent = message;
  if (state.avatarElements?.modePill) state.avatarElements.modePill.textContent = label;
}

function stopAvatarMonitoring() {
  if (state.avatarRafId) {
    cancelAnimationFrame(state.avatarRafId);
    state.avatarRafId = 0;
  }
  try { state.avatarMonitorSource?.disconnect(); } catch (_) {}
  try { state.avatarAnalyser?.disconnect?.(); } catch (_) {}
  try { state.avatarAudioContext?.close?.(); } catch (_) {}
  state.avatarMonitorSource = null;
  state.avatarAnalyser = null;
  state.avatarAudioContext = null;
  setAvatarLevel(0);
}

function stopVoiceActivityDetection() {
  if (state.voiceVadRafId) {
    cancelAnimationFrame(state.voiceVadRafId);
    state.voiceVadRafId = 0;
  }
  state.voiceRecordStartedAt = 0;
  state.voiceSpeechDetectedAt = 0;
  state.voiceLastSpeechAt = 0;
  state.voiceHasSpeech = false;
}

function stopVoiceRecording(reason = "manual") {
  state.recordingStopReason = reason;
  stopVoiceActivityDetection();
  if (state.mediaRecorder && state.mediaRecorder.state !== "inactive") {
    state.mediaRecorder.stop();
  }
}

function startVoiceActivityDetection(analyser) {
  stopVoiceActivityDetection();
  state.voiceRecordStartedAt = performance.now();
  const buffer = new Uint8Array(analyser.fftSize);
  const threshold = 0.02;
  const warmupMs = 450;
  const minSpeechMs = 280;
  const silenceMs = 1100;
  const idleTimeoutMs = 6500;
  const maxRecordMs = 15000;

  const tick = () => {
    if (!state.isRecording || !state.mediaRecorder || state.mediaRecorder.state === "inactive") {
      stopVoiceActivityDetection();
      return;
    }

    analyser.getByteTimeDomainData(buffer);
    let power = 0;
    for (let i = 0; i < buffer.length; i += 1) {
      const normalized = (buffer[i] - 128) / 128;
      power += normalized * normalized;
    }
    const rms = Math.sqrt(power / Math.max(1, buffer.length));
    const now = performance.now();
    const elapsed = now - state.voiceRecordStartedAt;

    if (rms >= threshold) {
      if (!state.voiceHasSpeech && elapsed >= warmupMs) {
        state.voiceHasSpeech = true;
        state.voiceSpeechDetectedAt = now;
        setVoiceStatus("正在听你说话，说完后会自动提交…");
      }
      if (state.voiceHasSpeech) {
        state.voiceLastSpeechAt = now;
      }
    }

    if (!state.voiceHasSpeech && elapsed >= idleTimeoutMs) {
      setVoiceStatus("暂时没检测到清晰语音，本次先结束，你可以再试一次。");
      stopVoiceRecording("idle-timeout");
      return;
    }

    if (state.voiceHasSpeech) {
      const speechElapsed = now - state.voiceSpeechDetectedAt;
      const silenceElapsed = now - (state.voiceLastSpeechAt || state.voiceSpeechDetectedAt);
      if (speechElapsed >= minSpeechMs && silenceElapsed >= silenceMs) {
        setVoiceStatus("已检测到你说完，正在自动提交…");
        stopVoiceRecording("auto-silence");
        return;
      }
    }

    if (elapsed >= maxRecordMs) {
      setVoiceStatus("本轮说话时间较长，先为你提交当前内容…");
      stopVoiceRecording("max-duration");
      return;
    }

    state.voiceVadRafId = requestAnimationFrame(tick);
  };

  state.voiceVadRafId = requestAnimationFrame(tick);
}

function startAvatarMonitoring(audioContext, analyser, sourceNode, mode) {
  stopAvatarMonitoring();
  state.avatarAudioContext = audioContext;
  state.avatarAnalyser = analyser;
  state.avatarMonitorSource = sourceNode;
  setAvatarMode(mode);
  const buffer = new Uint8Array(analyser.frequencyBinCount);
  const tick = () => {
    analyser.getByteFrequencyData(buffer);
    let sum = 0;
    for (let i = 0; i < buffer.length; i += 1) sum += buffer[i];
    const avg = sum / Math.max(1, buffer.length);
    setAvatarLevel(Math.min(1, avg / 72));
    state.avatarRafId = requestAnimationFrame(tick);
  };
  tick();
}

function createAvatarAudioContext() {
  const Ctx = window.AudioContext || window.webkitAudioContext;
  return Ctx ? new Ctx() : null;
}

function renderAvatarStage(mode = "idle", hint = "") {
  const stage = $("videoStage");
  if (!stage || state.room) return;
  stage.innerHTML = avatarStageMarkup(mode, hint);
  cacheAvatarElements();
  setAvatarMode(mode, hint);
  setAvatarLevel(0);
}

function renderVideoPlaceholder() {
  const stage = $("videoStage");
  if (!stage || state.room) {
    return;
  }
  renderAvatarStage("idle");
}

function renderVideoLoading(message = "视频生成中，请稍候…") {
  const stage = $("videoStage");
  if (!stage || state.room) {
    return;
  }
  stage.innerHTML = `
    <div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;background:radial-gradient(circle at top, rgba(68,151,255,.22), rgba(4,10,24,.96));border-radius:inherit;padding:24px;box-sizing:border-box;">
      <div style="display:flex;flex-direction:column;gap:12px;align-items:center;text-align:center;">
        <div style="font-size:13px;letter-spacing:.12em;color:rgba(188,224,255,.78);">AI VIDEO PREPARING</div>
        <div style="font-size:16px;font-weight:600;color:#eef6ff;">${message}</div>
        <div style="font-size:12px;color:rgba(188,224,255,.62);">语音会先开始播放，随后自动切换到视频画面</div>
      </div>
    </div>
  `;
}

function updateVideoModeUi() {
  const startBtn = $("startConsultBtn");
  const keepAliveBtn = $("keepAliveBtn");
  const disconnectBtn = $("disconnectBtn");
  const connDot = $("connDot");

  const liveEnabled = hasLiveAvatarMode();
  const dittoEnabled = hasDittoMode();
  const experimentalVideo = state.experimentalVideoEnabled && dittoEnabled;

  if (startBtn) {
    if (liveEnabled) setBtnText(startBtn, "视频通话");
    else setBtnText(startBtn, state.isRecording ? "结束说话" : "开始问诊");
  }

  if (keepAliveBtn) {
    keepAliveBtn.disabled = !liveEnabled;
    keepAliveBtn.style.display = liveEnabled ? "" : "none";
  }
  if (disconnectBtn) {
    disconnectBtn.style.display = liveEnabled ? "" : "none";
  }

  if (connDot) {
    connDot.classList.toggle("live", liveEnabled || dittoEnabled || !liveEnabled);
  }

  if (liveEnabled) {
    setText("connectionState", "未连接");
    setText("modeState", "等待会话启动");
  } else if (dittoEnabled) {
    setText("connectionState", state.isRecording ? "正在聆听" : "语音待命");
    setText("modeState", experimentalVideo ? "主语音 + 实验视频" : "Web 2D 语音主流程");
  } else {
    setText("connectionState", state.isRecording ? "正在聆听" : "语音待命");
    setText("modeState", "Web 2D 语音主流程");
  }
  updatePrimaryActionUi();
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const err = await response.json();
      detail = err.detail || JSON.stringify(err);
    } catch (_) {}
    throw new Error(detail);
  }
  return response.json();
}

async function sendPresenceHeartbeat() {
  const sessionId = ensurePresenceSessionId();
  try {
    await postJson("/api/ops/presence", { session_id: sessionId });
  } catch (_) {}
}

function startPresenceHeartbeat() {
  sendPresenceHeartbeat();
  window.setInterval(sendPresenceHeartbeat, 45000);
}

async function getJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const err = await response.json();
      detail = err.detail || JSON.stringify(err);
    } catch (_) {}
    throw new Error(detail);
  }
  return response.json();
}

function renderRemoteTrack(track) {
  const container = $("videoStage");
  if (!container) {
    return;
  }
  container.innerHTML = "";
  const element = track.attach();
  element.autoplay = true;
  element.playsInline = true;
  element.style.width = "100%";
  element.style.height = "100%";
  element.style.objectFit = "cover";
  container.appendChild(element);
}

function attachRoomListeners(room) {
  const { RoomEvent, Track } = window.LivekitClient;

  room.on(RoomEvent.Connected, () => {
    setText("connectionState", "已连接");
    setText("modeState", "实时视频会话");
  });
  room.on(RoomEvent.Disconnected, () => {
    updateVideoModeUi();
    renderVideoPlaceholder();
  });
  room.on(RoomEvent.TrackSubscribed, (track) => {
    if (track.kind === Track.Kind.Video) {
      renderRemoteTrack(track);
    }
    if (track.kind === Track.Kind.Audio) {
      track.attach();
    }
  });
}

async function connectLiveKit(startData) {
  if (!startData.livekit_url || !startData.livekit_client_token) {
    throw new Error("缺少视频连接信息。");
  }
  if (!window.LivekitClient) {
    throw new Error("LiveKit SDK 未加载。");
  }

  if (state.room) {
    await state.room.disconnect();
    state.room = null;
  }

  const room = new window.LivekitClient.Room({
    adaptiveStream: true,
    dynacast: true,
  });

  attachRoomListeners(room);
  await room.connect(startData.livekit_url, startData.livekit_client_token, {
    autoSubscribe: true,
  });
  await room.localParticipant.setMicrophoneEnabled(true);
  state.room = room;
}

async function startConsultation() {
  if (!state.appConfig) {
    return;
  }

  if (!hasLiveAvatarMode() && hasDittoMode()) {
    setVoiceStatus(state.isRecording ? "再次点击即可结束说话并自动转写。" : "实时语音主路线已启用，正在准备麦克风。");
    const message = $("message");
    if (message) {
      message.focus();
      message.placeholder = "先说出或输入问题，系统会先语音回答；实验视频仅在手动开启时启用。";
    }
    renderAvatarStage("idle", "实时语音主路线已启用。你说话时会进入聆听态，回答时会自动口播。");
    await toggleVoiceInput();
    return;
  }

  if (!hasLiveAvatarMode()) {
    setVoiceStatus(state.isRecording ? "再次点击即可结束说话并自动转写。" : "实时语音模式已启用，正在准备麦克风。");
    renderAvatarStage("idle", "当前优先走 Web 2D 实时语音助手，不再默认等待视频生成。");
    await toggleVoiceInput();
    return;
  }

  const startBtn = $("startConsultBtn");
  if (startBtn) {
    startBtn.disabled = true;
    setBtnText(startBtn, "连接中…");
  }

  try {
    const tokenData = await postJson("/api/liveavatar/token", {});
    state.sessionToken = tokenData.data.session_token || "";
    const sessionData = await postJson("/api/liveavatar/session", {
      session_token: state.sessionToken,
    });
    await connectLiveKit(sessionData.data);
  } catch (error) {
    setText("connectionState", "连接失败");
    setText("answer", error.message);
  } finally {
    if (startBtn) {
      startBtn.disabled = false;
      updateVideoModeUi();
    }
  }
}

async function keepAlive() {
  if (!state.appConfig?.video_avatar_enabled || !state.sessionToken) {
    return;
  }
  try {
    await postJson("/api/liveavatar/keepalive", {
      session_token: state.sessionToken,
    });
  } catch (error) {
    setText("answer", error.message);
  }
}

async function disconnectRoom() {
  if (state.room) {
    await state.room.disconnect();
    state.room = null;
  }
  updateVideoModeUi();
  renderVideoPlaceholder();
}

async function askQuestion() {
  if (state.askInFlight) return;
  const input = $("message");
  const message = input?.value.trim();
  if (!message) return;
  if (input) {
    input.value = "";
    input.style.height = "auto";
  }

  if (isChatMode()) {
    appendChatMessage("user", message);
    const loadingRow = appendChatMessage("ai", null);
    setAvatarMode("thinking");
    setText("connectionState", "理解问题中");
    state.askInFlight = true;
    /* Keep voiceInputBtn enabled so user can interrupt */
    const voiceBtn = $("voiceInputBtn");
    if (voiceBtn) voiceBtn.disabled = false;
    try {
      /* Try SSE voice-chat (streaming text + audio) */
      let usedSSE = false;
      let fullText = "";
      try {
        _voiceChatAbort = new AbortController();
        const resp = await fetch("/api/voice-chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message, conversation: state.conversation }),
          signal: _voiceChatAbort.signal,
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const reader = resp.body.getReader();
        const decoder = new TextDecoder();
        let sseBuffer = "";
        _ttsQueue = [];
        _ttsPlaying = false;
        if (_currentAudio) { _currentAudio.pause(); _currentAudio = null; }

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          sseBuffer += decoder.decode(value, { stream: true });
          const lines = sseBuffer.split("\n");
          sseBuffer = lines.pop() || "";
          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const evt = JSON.parse(line.slice(6));
              if (evt.type === "text") {
                fullText += evt.token;
                updateChatMessage(loadingRow, fullText);
              } else if (evt.type === "audio") {
                const binary = Uint8Array.from(atob(evt.audio), c => c.charCodeAt(0));
                const blob = new Blob([binary], { type: evt.format || "audio/mpeg" });
                _ttsQueue.push({ blob, isLast: false });
                if (!_ttsPlaying) _playNextInQueue();
              } else if (evt.type === "done") {
                fullText = evt.full_text || fullText;
              }
            } catch (_) { /* skip malformed SSE lines */ }
          }
        }
        usedSSE = true;
      } catch (sseErr) {
        if (sseErr.name === "AbortError") throw sseErr;
        /* SSE failed (e.g. mobile ReadableStream issues) — fallback to non-streaming */
        console.warn("SSE voice-chat failed, falling back:", sseErr);
      }

      /* Fallback: if SSE didn't produce text, use regular chat + TTS */
      if (!fullText) {
        const data = await postJson("/api/chat", { message, conversation: state.conversation });
        fullText = data.answer;
        updateChatMessage(loadingRow, fullText);
      }

      setText("answer", fullText);
      updateChatMessage(loadingRow, fullText);
      state.conversation.push({ role: "user", content: message });
      state.conversation.push({ role: "assistant", content: fullText });
      if (state.conversation.length > 20) state.conversation = state.conversation.slice(-20);

      /* If SSE didn't play audio (or fallback path), speak now */
      if (!usedSSE || (_ttsQueue.length === 0 && !_ttsPlaying && !_currentAudio)) {
        void speakAnswer(fullText);
      }

      if (state.experimentalVideoEnabled && state.appConfig?.ditto_stream?.enabled) startDittoStream(fullText);
      else if (state.experimentalVideoEnabled && state.appConfig?.ditto_enabled) void generateDittoVideo(fullText);
    } catch (error) {
      if (error.name === "AbortError") {
        /* User interrupted — not an error */
      } else {
        setText("answer", error.message);
        updateChatMessage(loadingRow, `出错了：${error.message}`);
        setAvatarMode("idle", "这次回答失败了，可以重试或换一种问法。");
        setText("connectionState", "语音待命");
      }
    } finally {
      state.askInFlight = false;
      _voiceChatAbort = null;
      updateVideoModeUi();
    }
  } else {
    setText("answer", "生成中...");
    setAvatarMode("thinking");
    setText("connectionState", "理解问题中");
    setConversationBusy(true);
    try {
      const data = await postJson("/api/chat", { message, conversation: state.conversation });
      setText("answer", data.answer);
      state.conversation.push({ role: "user", content: message });
      state.conversation.push({ role: "assistant", content: data.answer });
      if (state.conversation.length > 20) state.conversation = state.conversation.slice(-20);
      void speakAnswer(data.answer);
      if (state.experimentalVideoEnabled && state.appConfig?.ditto_stream?.enabled) startDittoStream(data.answer);
      else if (state.experimentalVideoEnabled && state.appConfig?.ditto_enabled) void generateDittoVideo(data.answer);
    } catch (error) {
      setText("answer", error.message);
      setAvatarMode("idle", "这次回答失败了，可以重试或改成文字输入。");
      setText("connectionState", "语音待命");
    } finally {
      setConversationBusy(false);
      updateVideoModeUi();
    }
  }
}

function setVoiceStatus(message) {
  setText("voiceStatus", message);
}

async function prepareMicrophoneAccess() {
  if (state.microphonePrimed) {
    return true;
  }
  if (!navigator.mediaDevices?.getUserMedia) {
    return false;
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((track) => track.stop());
    state.microphonePrimed = true;
    setAvatarMode("idle", "麦克风已就绪，说话时会切到聆听状态。");
    setText("connectionState", "语音待命");
    return true;
  } catch (error) {
    const denied = error?.name === "NotAllowedError" || error?.name === "PermissionDeniedError";
    setVoiceStatus(denied ? "你拒绝了麦克风权限，可以先改用文字输入。" : "当前浏览器未能获取麦克风权限，可先使用文字输入。");
    return false;
  }
}

async function toggleVoiceInput() {
  if (state.isRecording) {
    stopVoiceRecording("manual");
    return;
  }
  /* Interrupt any ongoing TTS playback or SSE stream */
  _stopAllTts();
  setConversationBusy(false);
  state.voiceSessionActive = true; /* User explicitly started voice mode */

  const micOk = await prepareMicrophoneAccess();
  if (!micOk) return;

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const audioContext = createAvatarAudioContext();
    let analyser = null;
    if (audioContext) {
      const sourceNode = audioContext.createMediaStreamSource(stream);
      analyser = audioContext.createAnalyser();
      analyser.fftSize = 128;
      analyser.smoothingTimeConstant = 0.65;
      sourceNode.connect(analyser);
      startAvatarMonitoring(audioContext, analyser, sourceNode, "listening");
    } else {
      setAvatarMode("listening");
    }
    const mimeType = MediaRecorder.isTypeSupported("audio/webm;codecs=opus")
      ? "audio/webm;codecs=opus"
      : MediaRecorder.isTypeSupported("audio/mp4")
        ? "audio/mp4"
        : "";
    const recorder = mimeType
      ? new MediaRecorder(stream, { mimeType })
      : new MediaRecorder(stream);
    const chunks = [];

    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data);
    };

    recorder.onstop = async () => {
      stream.getTracks().forEach((t) => t.stop());
      stopVoiceActivityDetection();
      stopAvatarMonitoring();
      setAvatarMode("thinking", "录音结束，正在转写你的问题。");
      setText("connectionState", "转写中");
      state.isRecording = false;
      const stopReason = state.recordingStopReason || "manual";
      state.recordingStopReason = "manual";
      state.mediaRecorder = null;
      const voiceBtn = $("voiceInputBtn");
      if (voiceBtn) voiceBtn.textContent = "🎤 语音";
      updatePrimaryActionUi();
      if (chunks.length === 0) {
        setVoiceStatus(stopReason === "idle-timeout" ? "没有听清你的说话，可以再试一次。" : "未录到音频。");
        setAvatarMode("idle", "这次没有采到有效语音，可以直接重试。");
        setText("connectionState", "语音待命");
        return;
      }
      setVoiceStatus(
        stopReason === "auto-silence"
          ? "你说完了，正在识别…"
          : stopReason === "max-duration"
            ? "已按阶段提交，正在识别…"
            : "识别中…"
      );
      const blob = new Blob(chunks, { type: recorder.mimeType });
      const form = new FormData();
      form.append("audio", blob, "audio.webm");
      try {
        const resp = await fetch("/api/stt", { method: "POST", body: form });
        if (!resp.ok) {
          const err = await resp.json().catch(() => ({}));
          throw new Error(err.detail || `HTTP ${resp.status}`);
        }
        const result = await resp.json();
        const text = (result.text || "").trim();
        if (text && $("message")) {
          $("message").value = text;
          setVoiceStatus("已识别，正在发送问题…");
          setAvatarMode("thinking", "转写已完成，正在提交给医生助手。");
          await askQuestion();
        } else {
          setVoiceStatus("未识别到语音内容，请重试。");
          setAvatarMode("idle", "这次没有识别到有效内容，可以再说一遍。");
          setText("connectionState", "语音待命");
        }
      } catch (exc) {
        setVoiceStatus(`识别失败：${exc.message}`);
        setAvatarMode("idle", "语音识别失败，你也可以先改成文字输入。");
        setText("connectionState", "语音待命");
      }
    };

    recorder.start();
    state.mediaRecorder = recorder;
    state.isRecording = true;
    state.recordingStopReason = "manual";
    const voiceBtn = $("voiceInputBtn");
    if (voiceBtn) voiceBtn.textContent = "⏹ 停止录音";
    updatePrimaryActionUi();
    setText("connectionState", "正在聆听");
    setVoiceStatus("正在录音，说完后会自动提交，也可以手动结束。");
    startVoiceActivityDetection(analyser || state.avatarAnalyser);
  } catch (exc) {
    setVoiceStatus(`麦克风启动失败：${exc.message}`);
    setText("connectionState", "语音待命");
  }
}

let _currentAudio = null;
let _voiceChatAbort = null; /* AbortController for interrupting voice-chat SSE */

/* ---- Sentence-level streaming TTS queue ---- */
let _ttsQueue = [];
let _ttsPlaying = false;

function _stopAllTts() {
  /* Interrupt: stop current audio, clear queue, abort SSE */
  if (_currentAudio) { _currentAudio.pause(); _currentAudio = null; }
  _ttsQueue = [];
  _ttsPlaying = false;
  if (_voiceChatAbort) { _voiceChatAbort.abort(); _voiceChatAbort = null; }
  stopAvatarMonitoring();
}

function _splitSentences(text) {
  /* Split Chinese/English text into sentences at natural boundaries */
  return text.split(/(?<=[。！？；\n.!?;])\s*/).filter(s => s.trim().length > 0);
}

async function _fetchTtsBlob(text) {
  const resp = await fetch("/api/tts/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!resp.ok) throw new Error(`TTS HTTP ${resp.status}`);
  return await resp.blob();
}

async function _playNextInQueue() {
  if (_ttsPlaying || _ttsQueue.length === 0) return;
  _ttsPlaying = true;
  const { blob, isLast } = _ttsQueue.shift();
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  const audioContext = createAvatarAudioContext();
  if (audioContext) {
    const sourceNode = audioContext.createMediaElementSource(audio);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.72;
    sourceNode.connect(analyser);
    analyser.connect(audioContext.destination);
    startAvatarMonitoring(audioContext, analyser, sourceNode, "speaking");
  } else {
    setAvatarMode("speaking");
  }
  _currentAudio = audio;
  audio.onplay = () => {
    setVoiceStatus("正在朗读回答。");
    setAvatarMode("speaking");
    setText("connectionState", "正在回答");
  };
  audio.onended = () => {
    URL.revokeObjectURL(url);
    _currentAudio = null;
    _ttsPlaying = false;
    if (_ttsQueue.length > 0) {
      _playNextInQueue();
    } else {
      stopAvatarMonitoring();
      setAvatarMode("idle", "回答完毕，正在自动开启麦克风…");
      setVoiceStatus("回答完毕，准备继续对话。");
      setText("connectionState", "语音待命");
      /* Auto-start recording only if user initiated voice mode */
      setTimeout(() => {
        if (!state.isRecording && !_ttsPlaying && state.microphonePrimed && state.voiceSessionActive) {
          toggleVoiceInput();
        }
      }, 600);
    }
  };
  audio.onerror = () => {
    stopAvatarMonitoring();
    URL.revokeObjectURL(url);
    _currentAudio = null;
    _ttsPlaying = false;
    _ttsQueue = [];
    setAvatarMode("idle", "语音播放失败，你可以继续文字追问。");
    setVoiceStatus("朗读失败，请稍后再试。");
    setText("connectionState", "语音待命");
  };
  try {
    await audio.play();
  } catch (playErr) {
    /* Autoplay blocked (common on mobile) — skip to next or finish */
    console.warn("Audio play blocked:", playErr);
    URL.revokeObjectURL(url);
    _currentAudio = null;
    _ttsPlaying = false;
    if (_ttsQueue.length > 0) {
      _playNextInQueue();
    } else {
      stopAvatarMonitoring();
      setAvatarMode("idle", "回答完毕。");
      setVoiceStatus("朗读完成。");
      setText("connectionState", "语音待命");
      setTimeout(() => {
        if (!state.isRecording && !_ttsPlaying && state.microphonePrimed) {
          toggleVoiceInput();
        }
      }, 600);
    }
  }
}

async function speakAnswer(textOverride) {
  const answer = (textOverride || $("answer")?.textContent || "").trim();
  if (!answer || answer === "尚未生成回答。") {
    setVoiceStatus("还没有可朗读的回答。");
    return;
  }
  try {
    setVoiceStatus("语音准备中…");
    setAvatarMode("thinking", "回答已生成，正在准备语音播报。");
    if (_currentAudio) { _currentAudio.pause(); _currentAudio = null; }
    _ttsQueue = [];
    _ttsPlaying = false;

    const sentences = _splitSentences(answer);
    if (sentences.length === 0) return;

    /* Fetch first sentence immediately, start playing ASAP */
    const firstBlob = await _fetchTtsBlob(sentences[0]);
    _ttsQueue.push({ blob: firstBlob, isLast: sentences.length === 1 });
    _playNextInQueue();

    /* Fetch remaining sentences in parallel while first plays */
    if (sentences.length > 1) {
      const remaining = sentences.slice(1);
      const promises = remaining.map((s, i) =>
        _fetchTtsBlob(s).then(blob => ({ blob, index: i, isLast: i === remaining.length - 1 }))
      );
      /* Process in order as they resolve */
      const results = await Promise.all(promises);
      results.sort((a, b) => a.index - b.index);
      for (const r of results) {
        _ttsQueue.push({ blob: r.blob, isLast: r.isLast });
        if (!_ttsPlaying) _playNextInQueue();
      }
    }
  } catch (exc) {
    stopAvatarMonitoring();
    setAvatarMode("idle", "当前朗读启动失败，但你仍可继续文字对话。");
    setVoiceStatus(`朗读失败：${exc.message}`);
    setText("connectionState", "语音待命");
  }
}

function stopSpeech() {
  _stopAllTts(); /* Stop current audio, clear queue, abort SSE */
  state.voiceSessionActive = false; /* Exit continuous voice mode */
  if ("speechSynthesis" in window) window.speechSynthesis.cancel();
  setAvatarMode("idle", "已停止朗读，你可以继续追问。");
  setVoiceStatus("已停止朗读。");
  setText("connectionState", "语音待命");
}

async function generateDittoVideo(text) {
  const stage = $("videoStage");
  if (!stage || state.room) return;
  try {
    setText("modeState", "视频生成中…");
    renderVideoLoading();
    const response = await fetch("/api/ditto/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || `HTTP ${response.status}`);
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    stage.innerHTML = "";
    const video = document.createElement("video");
    video.src = url;
    video.autoplay = true;
    video.playsInline = true;
    video.style.cssText = "width:100%;height:100%;object-fit:cover;border-radius:inherit;";
    const restore = () => {
      URL.revokeObjectURL(url);
      renderVideoPlaceholder();
      updateVideoModeUi();
    };
    video.onended = restore;
    video.onerror = restore;
    stage.appendChild(video);
    setText("modeState", "视频播放中");
  } catch (exc) {
    updateVideoModeUi();
    console.warn("Ditto:", exc.message);
  }
}

function startDittoStream(text) {
  const stage = $("videoStage");
  if (!stage || state.room) return;

  // 关闭上一个流（如果有）
  if (state.dittoWs) {
    try { state.dittoWs.close(); } catch (_) {}
    state.dittoWs = null;
  }

  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/ditto/stream`);
  state.dittoWs = ws;

  // 先显示 loading，首帧到达后再换成 Canvas，避免黑屏
  renderVideoLoading("实时视频准备中，首帧约 1-2 秒…");

  let canvas = null;
  let ctx = null;

  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    ws.send(JSON.stringify({ text }));
  };

  // 10 秒内未收到首帧视为超时，回退占位
  const firstFrameTimeout = setTimeout(() => {
    if (!canvas && state.dittoWs === ws) {
      ws.close();
      renderVideoPlaceholder();
      if (isChatMode()) {
        const row = appendChatMessage("ai", "视频连接超时，请稍后重试。");
        if (row) setTimeout(() => row.remove(), 4000);
      }
    }
  }, 10000);

  ws.onmessage = (event) => {
    if (event.data instanceof ArrayBuffer) {
      clearTimeout(firstFrameTimeout);
      // 首帧时挂载 Canvas
      if (!canvas) {
        stage.innerHTML = "";
        canvas = document.createElement("canvas");
        canvas.width = 512;
        canvas.height = 512;
        canvas.style.cssText = "width:100%;height:100%;object-fit:cover;border-radius:inherit;display:block;";
        stage.appendChild(canvas);
        ctx = canvas.getContext("2d");
      }
      // JPEG 帧 → 画到 Canvas
      const blob = new Blob([event.data], { type: "image/jpeg" });
      const url = URL.createObjectURL(blob);
      const img = new Image();
      img.onload = () => { ctx.drawImage(img, 0, 0, canvas.width, canvas.height); URL.revokeObjectURL(url); };
      img.src = url;
    } else {
      try {
        const payload = JSON.parse(event.data);
        if (payload.done) {
          clearTimeout(firstFrameTimeout);
          ws.close();
          setTimeout(() => renderVideoPlaceholder(), 1500);
        }
        if (payload.error) {
          clearTimeout(firstFrameTimeout);
          console.warn("Ditto stream error:", payload.error);
          ws.close();
          renderVideoPlaceholder();
          if (isChatMode()) {
            const row = appendChatMessage("ai", `视频生成失败：${payload.error}`);
            if (row) setTimeout(() => row.remove(), 5000);
          }
        }
      } catch (_) {}
    }
  };

  ws.onerror = () => {
    clearTimeout(firstFrameTimeout);
    renderVideoPlaceholder();
    state.dittoWs = null;
  };

  ws.onclose = () => {
    clearTimeout(firstFrameTimeout);
    state.dittoWs = null;
  };
}

function renderList(id, items) {
  const el = $(id);
  if (!el) {
    return;
  }
  el.innerHTML = "";
  (items || []).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    el.appendChild(li);
  });
}

function renderSources(items) {
  const container = $("officialSources");
  if (!container) {
    return;
  }
  container.innerHTML = "";

  (items || []).forEach((item) => {
    const a = document.createElement("a");
    a.href = item.url;
    a.target = "_blank";
    a.rel = "noreferrer";
    a.textContent = item.title;
    container.appendChild(a);
  });

  if (!items || items.length === 0) {
    container.textContent = "暂未配置官方来源。";
  }
}

async function loadProfile() {
  const profile = await getJson("/api/doctor-profile");
  state.doctorProfile = profile;

  setText("brandSubtitle", `${profile.hospital} · ${profile.department}`);
  setText("brandMeta", `${profile.hospital} · ${profile.department}`);
  setText("heroTitle", `${profile.name}医生`);
  setText(
    "heroDescription",
    `当前主舞台优先保留给医生形象与后续视频会话，图文与语音交互全部收进右侧提问舱。`
  );
  setText("heroSummary", `${profile.public_tagline}。`);
  setText("identityNote", "当前优先保留主舞台和低干扰会话布局，后续视频分身、字幕和实时状态会直接叠加在这里。");
  setText("hospitalValue", profile.hospital || "-");
  setText("doctorState", profile.name || "-");
  setText("deptState", profile.department || "-");
  setText("focusPrimary", (profile.focus_areas || [])[0] || profile.specialty || "耳鼻咽喉科");
  setText("focusPrimaryCard", (profile.focus_areas || [])[0] || profile.specialty || "耳鼻咽喉科");
  setText(
    "clinicNote",
    `提醒：${profile.clinic_note || "本页面仅供健康科普与就医参考，不替代面诊。"}${profile.telephone ? ` 医院电话：${profile.telephone}。` : ""}`
  );
  setText(
    "doctorBio",
    [
      `${profile.name || ""}，${profile.title || ""}`,
      `${profile.hospital_alias || profile.hospital || ""}`,
      ...(profile.public_bio || []),
    ].filter(Boolean).join("\n")
  );

  const tagContainer = $("focusTags");
  if (tagContainer) {
    tagContainer.innerHTML = "";
    (profile.focus_areas || []).slice(0, 5).forEach((item) => {
      const span = document.createElement("span");
      span.className = "chip";
      span.textContent = item;
      tagContainer.appendChild(span);
    });
  }

  renderList("focusList", profile.focus_areas || []);
  renderSources(profile.official_sources || []);
  renderVideoPlaceholder();
}

async function loadAppConfig() {
  const config = await getJson("/api/app-config");
  state.appConfig = config;
  state.experimentalVideoEnabled = isExperimentalVideoMode();
  updateVideoModeUi();
  renderVideoPlaceholder();
}

function wireUi() {
  $("startConsultBtn")?.addEventListener("click", startConsultation);
  $("keepAliveBtn")?.addEventListener("click", keepAlive);
  $("disconnectBtn")?.addEventListener("click", disconnectRoom);
  $("askBtn")?.addEventListener("click", () => {
    state.voiceSessionActive = false; /* Text submit exits voice mode */
    askQuestion();
  });
  $("voiceInputBtn")?.addEventListener("click", toggleVoiceInput);
  $("speakAnswerBtn")?.addEventListener("click", speakAnswer);
  $("stopSpeechBtn")?.addEventListener("click", stopSpeech);
  document.querySelectorAll("#quickPrompts .prompt-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      const question = btn.dataset.question || btn.textContent || "";
      const msgEl = $("message");
      if (!msgEl) return;
      msgEl.value = question.trim();
      msgEl.style.height = "auto";
      msgEl.style.height = Math.min(msgEl.scrollHeight, 120) + "px";
      state.voiceSessionActive = false; /* Quick prompt exits voice mode */
      askQuestion();
    });
  });
  const msgEl = $("message");
  if (msgEl) {
    msgEl.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        state.voiceSessionActive = false; /* Keyboard submit exits voice mode */
        askQuestion();
      }
    });
    // 自动伸缩高度（聊天模式）
    msgEl.addEventListener("input", () => {
      msgEl.style.height = "auto";
      msgEl.style.height = Math.min(msgEl.scrollHeight, 120) + "px";
    });
  }
  let resizeTimer;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(renderVideoPlaceholder, 150);
  });
}

wireUi();
startPresenceHeartbeat();
loadAppConfig().catch((error) => {
  setText("answer", error.message);
});
loadProfile().catch((error) => {
  setText("doctorBio", error.message);
  renderVideoPlaceholder();
});
