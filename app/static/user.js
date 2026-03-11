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
          <div class="portrait-copy">
            <span>Doctor Visual</span>
            <h3>${profileName()}</h3>
            <p>${profileTitle()}<br />${profileHospital()} · ${profileDepartment()}</p>
          </div>
        </div>
      </div>
      <div class="brief-panel">
        <div class="label">AI Medical Core</div>
        <h3>当前以图文与语音问答在线，视频分身接口保持待命。</h3>
        <p>这一版把大部分空间都留给主视窗，让未来的视频分身、字幕与实时会话能自然落位；右侧只保留提问、回答和必要资料，不再把首页切成一堆信息块。</p>
        <div class="brief-stats">
          <div class="brief-stat">
            <span>当前形态</span>
            <strong>主视窗待机</strong>
          </div>
          <div class="brief-stat">
            <span>语音能力</span>
            <strong>浏览器原生</strong>
          </div>
          <div class="brief-stat">
            <span>后续升级</span>
            <strong>实时分身接入</strong>
          </div>
        </div>
        <div class="brief-points">
          <div>核心能力优先放在常见问题答疑、专科方向说明与线下就医建议。</div>
          <div>接回视频分身后，当前主区域会直接切换为实时画面，不需要重做整体页面。</div>
          <div>所有高风险情形仍以医院线下评估、急诊与正式检查为准。</div>
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
  if (!message) {
    return;
  }

  if (input) {
    input.value = "";
  }
  setText("answer", "生成中...");

  try {
    const data = await postJson("/api/chat", {
      message,
      conversation: state.conversation,
    });
    setText("answer", data.answer);
    state.conversation.push({ role: "user", content: message });
    state.conversation.push({ role: "assistant", content: data.answer });
    if (state.conversation.length > 20) {
      state.conversation = state.conversation.slice(-20);
    }
  } catch (error) {
    setText("answer", error.message);
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
  setText("heroTitle", `${profile.name}医生 · AI 临床会话视窗`);
  setText(
    "heroDescription",
    `${profile.public_tagline}。当前主窗口已预留视频分身与实时对话区域，右侧提问舱负责图文与语音问答。`
  );
  setText("hospitalValue", profile.hospital || "-");
  setText("doctorState", profile.name || "-");
  setText("deptState", profile.department || "-");
  setText("focusPrimary", (profile.focus_areas || [])[0] || profile.specialty || "耳鼻咽喉科");
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
    startBtn.textContent = "视频分身即将开放";
  }
  if (keepAliveBtn) {
    keepAliveBtn.disabled = !enabled;
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
  $("message")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      askQuestion();
    }
  });
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
