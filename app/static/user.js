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

function desktopPlaceholderMarkup() {
  return `
    <div class="desktop-placeholder">
      <div class="portrait-panel">
        <div class="portrait-frame">
          <div class="portrait-photo-shell">
            <img class="portrait-photo" src="/static/doctor-liyong-official.jpg" alt="${profileName()}医生公开职业照" />
          </div>
          <div class="portrait-signal">视频通道待机</div>
        </div>
      </div>
    </div>
  `;
}

function mobilePlaceholderMarkup() {
  return `
    <div class="mobile-placeholder">
      <div class="portrait-mobile">
        <div class="badge">Doctor Visual</div>
        <div class="name">${profileName()}</div>
        <div class="meta">${profileTitle()}<br />${profileHospital()} · ${profileDepartment()}</div>
        <div class="note">当前先用医生主视觉卡片承接移动端入口。后续接回视频分身时，这里会直接切换成实时画面。</div>
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
    startBtn.textContent = "连接中...";
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
      startBtn.textContent = "开始视频咨询";
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
    startBtn.textContent = "视频分身";
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
