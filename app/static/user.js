const state = {
  room: null,
  sessionToken: "",
  conversation: [],
  doctorProfile: null,
  appConfig: null,
  recognition: null,
  recognitionAvailable: false,
};

function $(id) {
  return document.getElementById(id);
}

function setText(id, value) {
  const el = $(id);
  if (el) {
    el.textContent = value;
  }
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

function avatarSvg() {
  return `<svg viewBox="0 0 360 480" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" preserveAspectRatio="xMidYMid meet" style="width:100%;height:100%;display:block">
    <defs>
      <radialGradient id="avH" cx="38%" cy="30%" r="62%"><stop offset="0%" stop-color="#dce9f0"/><stop offset="100%" stop-color="#96afc0"/></radialGradient>
      <radialGradient id="avC" cx="28%" cy="20%" r="72%"><stop offset="0%" stop-color="#edf4f8"/><stop offset="100%" stop-color="#bccedd"/></radialGradient>
      <linearGradient id="avR" x1="0%" y1="0%" x2="100%" y2="100%"><stop offset="0%" stop-color="#7ce0d7"/><stop offset="100%" stop-color="#4b7cff"/></linearGradient>
      <filter id="avG"><feGaussianBlur stdDeviation="2.5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
    </defs>
    <circle cx="180" cy="175" r="90" fill="none" stroke="url(#avR)" stroke-width="1.2" opacity="0.3"><animate attributeName="r" values="88;102;88" dur="3s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.3;0.08;0.3" dur="3s" repeatCount="indefinite"/></circle>
    <circle cx="180" cy="175" r="112" fill="none" stroke="url(#avR)" stroke-width="0.7" opacity="0.14"><animate attributeName="r" values="110;128;110" dur="3s" begin="0.5s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.14;0.03;0.14" dur="3s" begin="0.5s" repeatCount="indefinite"/></circle>
    <path d="M93 318 C88 278 108 255 138 248 L162 316 L198 316 L222 248 C252 255 272 278 267 318 L267 450 L93 450Z" fill="url(#avC)"/>
    <path d="M138 248 L162 316 L162 450 L110 450 L110 295 Q116 265 138 248Z" fill="rgba(0,0,0,0.055)"/>
    <path d="M222 248 L198 316 L198 450 L250 450 L250 295 Q244 265 222 248Z" fill="rgba(0,0,0,0.055)"/>
    <path d="M154 252 L162 316 L198 316 L206 252 L180 268Z" fill="rgba(255,255,255,0.3)"/>
    <rect x="165" y="208" width="30" height="46" rx="13" fill="url(#avH)"/>
    <ellipse cx="180" cy="170" rx="55" ry="59" fill="url(#avH)"/>
    <ellipse cx="162" cy="172" rx="18" ry="50" fill="rgba(0,0,0,0.05)"/>
    <path d="M125 158 Q127 104 180 99 Q233 104 235 158 Q226 124 180 122 Q134 124 125 158Z" fill="#22303e" opacity="0.88"/>
    <path d="M144 111 Q170 103 196 106" fill="none" stroke="rgba(255,255,255,0.13)" stroke-width="2.5" stroke-linecap="round"/>
    <ellipse cx="125" cy="173" rx="10" ry="14" fill="url(#avH)"/>
    <ellipse cx="235" cy="173" rx="10" ry="14" fill="url(#avH)"/>
    <ellipse cx="160" cy="165" rx="9" ry="10" fill="#1b2b3a"/>
    <ellipse cx="200" cy="165" rx="9" ry="10" fill="#1b2b3a"/>
    <circle cx="160" cy="165" r="5" fill="#2d4868"/>
    <circle cx="200" cy="165" r="5" fill="#2d4868"/>
    <circle cx="162" cy="162" r="2.8" fill="white" opacity="0.88"/>
    <circle cx="202" cy="162" r="2.8" fill="white" opacity="0.88"/>
    <path d="M150 151 Q160 147 170 150" fill="none" stroke="#22303e" stroke-width="2.2" stroke-linecap="round"/>
    <path d="M190 150 Q200 147 210 151" fill="none" stroke="#22303e" stroke-width="2.2" stroke-linecap="round"/>
    <path d="M176 177 Q180 186 184 177" fill="none" stroke="rgba(0,0,0,0.15)" stroke-width="1.6" stroke-linecap="round"/>
    <path d="M166 192 Q180 202 194 192" fill="none" stroke="rgba(50,75,90,0.48)" stroke-width="2" stroke-linecap="round"/>
    <path d="M148 258 Q136 276 134 298 Q132 316 143 326 Q155 338 167 326 Q179 314 175 298" fill="none" stroke="#7ce0d7" stroke-width="4" stroke-linecap="round" filter="url(#avG)"/>
    <circle cx="175" cy="296" r="10" fill="none" stroke="#7ce0d7" stroke-width="3.5" filter="url(#avG)"/>
    <circle cx="175" cy="296" r="4.5" fill="#7ce0d7" opacity="0.38"/>
    <path d="M148 258 Q150 244 158 240 Q166 236 170 244" fill="none" stroke="#7ce0d7" stroke-width="3" stroke-linecap="round"/>
    <circle cx="148" cy="258" r="4.5" fill="#7ce0d7" opacity="0.62"/>
    <circle cx="170" cy="244" r="4.5" fill="#7ce0d7" opacity="0.62"/>
    <rect x="204" y="276" width="40" height="34" rx="7" fill="rgba(255,255,255,0.1)" stroke="rgba(255,255,255,0.15)" stroke-width="1.2"/>
    <rect x="219" y="283" width="10" height="20" rx="3" fill="#7ce0d7" opacity="0.76"/>
    <rect x="213" y="289" width="22" height="8" rx="3" fill="#7ce0d7" opacity="0.76"/>
    <circle cx="95" cy="138" r="3.5" fill="#7ce0d7" opacity="0.5" filter="url(#avG)"><animate attributeName="cy" values="138;124;138" dur="2.7s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.5;0.14;0.5" dur="2.7s" repeatCount="indefinite"/></circle>
    <circle cx="270" cy="158" r="2.5" fill="#4b7cff" opacity="0.44" filter="url(#avG)"><animate attributeName="cy" values="158;143;158" dur="3.3s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.44;0.11;0.44" dur="3.3s" repeatCount="indefinite"/></circle>
    <circle cx="76" cy="245" r="3" fill="#7ce0d7" opacity="0.36"><animate attributeName="cy" values="245;229;245" dur="3s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.36;0.09;0.36" dur="3s" repeatCount="indefinite"/></circle>
    <circle cx="284" cy="224" r="2" fill="#a3f1ec" opacity="0.4"><animate attributeName="cy" values="224;208;224" dur="3.9s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.4;0.1;0.4" dur="3.9s" repeatCount="indefinite"/></circle>
    <circle cx="314" cy="310" r="2.5" fill="#4b7cff" opacity="0.26"><animate attributeName="cy" values="310;294;310" dur="2.9s" repeatCount="indefinite"/><animate attributeName="opacity" values="0.26;0.06;0.26" dur="2.9s" repeatCount="indefinite"/></circle>
  </svg>`;
}

function desktopPlaceholderMarkup() {
  return `
    <div class="avatar-wrap">
      ${avatarSvg()}
      <div class="avatar-info">
        <div class="av-badge">AI AVATAR · STANDBY</div>
        <div class="av-name">${profileName()}医生</div>
        <div class="av-meta">${profileHospital()} · ${profileDepartment()} · ${(state.doctorProfile?.focus_areas || [])[0] || ""}</div>
      </div>
    </div>
  `;
}

function mobilePlaceholderMarkup() {
  return `
    <div class="avatar-wrap">
      ${avatarSvg()}
      <div class="avatar-info">
        <div class="av-badge">AI AVATAR · STANDBY</div>
        <div class="av-name">${profileName()}医生</div>
        <div class="av-meta">${profileHospital()} · ${profileDepartment()}</div>
      </div>
    </div>
  `;
}

function renderVideoPlaceholder() {
  const stage = $("videoStage");
  if (!stage || state.room) {
    return;
  }
  stage.innerHTML = isMobileLayout() ? mobilePlaceholderMarkup() : desktopPlaceholderMarkup();
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
    setText("connectionState", state.appConfig?.video_avatar_enabled ? "未连接" : "未启用");
    setText("modeState", state.appConfig?.video_avatar_enabled ? "等待会话启动" : "图文问答主流程");
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
  if (!state.appConfig || !state.appConfig.video_avatar_enabled) {
    setText("answer", "视频分身能力当前未启用，现阶段请先使用文本问答。相关接口已保留，后续可随时接回。");
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
      setBtnText(startBtn, "视频通话");
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
  setText("connectionState", state.appConfig?.video_avatar_enabled ? "未连接" : "未启用");
  setText("modeState", state.appConfig?.video_avatar_enabled ? "等待会话启动" : "图文问答主流程");
  renderVideoPlaceholder();
}

async function askQuestion() {
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
    try {
      const data = await postJson("/api/chat", { message, conversation: state.conversation });
      setText("answer", data.answer);
      updateChatMessage(loadingRow, data.answer);
      state.conversation.push({ role: "user", content: message });
      state.conversation.push({ role: "assistant", content: data.answer });
      if (state.conversation.length > 20) state.conversation = state.conversation.slice(-20);
    } catch (error) {
      setText("answer", error.message);
      updateChatMessage(loadingRow, `出错了：${error.message}`);
    }
  } else {
    setText("answer", "生成中...");
    try {
      const data = await postJson("/api/chat", { message, conversation: state.conversation });
      setText("answer", data.answer);
      state.conversation.push({ role: "user", content: message });
      state.conversation.push({ role: "assistant", content: data.answer });
      if (state.conversation.length > 20) state.conversation = state.conversation.slice(-20);
    } catch (error) {
      setText("answer", error.message);
    }
  }
}

function setVoiceStatus(message) {
  setText("voiceStatus", message);
}

function initRecognition() {
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!Recognition) {
    setVoiceStatus("当前浏览器不支持原生语音输入，请改用手动输入。");
    return;
  }

  const recognition = new Recognition();
  recognition.lang = "zh-CN";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    setVoiceStatus("正在听你说话，请开始讲话。");
    setText("voiceInputBtn", "正在录音...");
  };

  recognition.onresult = (event) => {
    const transcript = event.results?.[0]?.[0]?.transcript || "";
    if (transcript && $("message")) {
      $("message").value = transcript.trim();
      setVoiceStatus("已识别语音内容，你可以直接提交，或再检查一下文字。");
    }
  };

  recognition.onerror = (event) => {
    setVoiceStatus(`语音输入失败：${event.error || "未知错误"}。`);
  };

  recognition.onend = () => {
    setText("voiceInputBtn", "语音输入");
  };

  state.recognition = recognition;
  state.recognitionAvailable = true;
}

function startVoiceInput() {
  if (!state.recognitionAvailable || !state.recognition) {
    setVoiceStatus("当前浏览器不支持原生语音输入，请改用手动输入。");
    return;
  }
  try {
    state.recognition.start();
  } catch (_) {
    setVoiceStatus("语音输入正在进行中，或浏览器还没准备好。");
  }
}

function speakAnswer() {
  const answer = $("answer")?.textContent.trim();
  if (!answer || answer === "尚未生成回答。") {
    setVoiceStatus("还没有可朗读的回答。");
    return;
  }

  if (!("speechSynthesis" in window)) {
    setVoiceStatus("当前浏览器不支持原生语音朗读。");
    return;
  }

  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(answer);
  utterance.lang = "zh-CN";
  utterance.rate = 1;
  utterance.pitch = 1;
  utterance.onstart = () => setVoiceStatus("正在朗读回答。");
  utterance.onend = () => setVoiceStatus("朗读已完成。");
  utterance.onerror = () => setVoiceStatus("朗读失败，请稍后再试。");
  window.speechSynthesis.speak(utterance);
}

function stopSpeech() {
  if ("speechSynthesis" in window) {
    window.speechSynthesis.cancel();
    setVoiceStatus("已停止朗读。");
  }
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

  const enabled = Boolean(config.video_avatar_enabled);
  const startBtn = $("startConsultBtn");
  const keepAliveBtn = $("keepAliveBtn");

  if (startBtn && !enabled) {
    setBtnText(startBtn, "视频通话");
  }
  if (keepAliveBtn) {
    keepAliveBtn.disabled = !enabled;
    keepAliveBtn.style.display = enabled ? "" : "none";
  }
  const disconnectBtn = $("disconnectBtn");
  if (disconnectBtn) {
    disconnectBtn.style.display = enabled ? "" : "none";
  }

  setText("connectionState", enabled ? "未连接" : "未启用");
  setText("modeState", enabled ? "等待会话启动" : "图文问答主流程");
  renderVideoPlaceholder();
}

function wireUi() {
  $("startConsultBtn")?.addEventListener("click", startConsultation);
  $("keepAliveBtn")?.addEventListener("click", keepAlive);
  $("disconnectBtn")?.addEventListener("click", disconnectRoom);
  $("askBtn")?.addEventListener("click", askQuestion);
  $("voiceInputBtn")?.addEventListener("click", startVoiceInput);
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
      askQuestion();
    });
  });
  const msgEl = $("message");
  if (msgEl) {
    msgEl.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
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
initRecognition();
loadAppConfig().catch((error) => {
  setText("answer", error.message);
});
loadProfile().catch((error) => {
  setText("doctorBio", error.message);
  renderVideoPlaceholder();
});
