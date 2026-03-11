const state = {
  room: null,
  sessionToken: "",
  conversation: [],
  doctorProfile: null,
  appConfig: null,
};

function $(id) {
  return document.getElementById(id);
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || JSON.stringify(data));
  }
  return data;
}

async function getJson(url) {
  const response = await fetch(url);
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.detail || JSON.stringify(data));
  }
  return data;
}

function renderRemoteTrack(track) {
  const container = $("videoStage");
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
    $("connectionState").textContent = "已连接";
  });
  room.on(RoomEvent.Disconnected, () => {
    $("connectionState").textContent = "未连接";
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
    $("answer").textContent = "视频分身能力当前未启用，现阶段请先使用文本问答。相关接口已保留，后续可随时接回。";
    return;
  }
  const startBtn = $("startConsultBtn");
  startBtn.disabled = true;
  startBtn.textContent = "连接中...";
  try {
    const tokenData = await postJson("/api/liveavatar/token", {});
    state.sessionToken = tokenData.data.session_token || "";
    const sessionData = await postJson("/api/liveavatar/session", {
      session_token: state.sessionToken,
    });
    await connectLiveKit(sessionData.data);
    $("connectionState").textContent = "已连接";
  } catch (error) {
    $("connectionState").textContent = "连接失败";
    $("answer").textContent = error.message;
  } finally {
    startBtn.disabled = false;
    startBtn.textContent = "开始视频咨询";
  }
}

async function keepAlive() {
  if (!state.appConfig || !state.appConfig.video_avatar_enabled) {
    return;
  }
  if (!state.sessionToken) {
    return;
  }
  try {
    await postJson("/api/liveavatar/keepalive", {
      session_token: state.sessionToken,
    });
  } catch (error) {
    $("answer").textContent = error.message;
  }
}

async function disconnectRoom() {
  if (state.room) {
    await state.room.disconnect();
    state.room = null;
  }
  $("connectionState").textContent = "未连接";
  if (window.innerWidth <= 720) {
    $("videoStage").innerHTML = `<div class="video-placeholder"><div class="portrait-mobile"><div class="badge">Doctor Profile Visual</div><div class="name">李勇</div><div class="meta">主任医师 / 教授 / 硕士生导师<br />杭州市第一人民医院 耳鼻咽喉科</div></div><div class="note">当前使用医生主视觉卡片代替视频位，先以文字问答和产品主流程为主。后续接回视频分身时，这里会直接切换成实时画面。</div></div>`;
    return;
  }
  $("videoStage").innerHTML = `<div class="portrait-side"><div class="portrait-card"><div class="portrait-placeholder"><div class="portrait-badge">Doctor Profile Visual</div><div class="portrait-name">李勇</div><div class="portrait-title">主任医师 / 教授 / 硕士生导师<br />杭州市第一人民医院 耳鼻咽喉科</div><div class="portrait-note">当前使用医生主视觉卡片代替实时视频位。后续接入分身能力后，可直接替换为真人或虚拟人画面。</div></div></div></div><div class="briefing-side"><div class="briefing-card"><h4>Clinical Briefing</h4><h5>数字分身接口保留，当前先以图文问答为主</h5><p>现阶段重点先完成可上线、可访问、可持续迭代的医生 AI 助手主流程。视频分身接口和会话链路已经保留，后续可以在不推翻现有产品框架的前提下接回。</p><div class="briefing-list"><div class="briefing-item">当前适合做常见问题答疑、专科方向说明、就医建议与内容展示。</div><div class="briefing-item">后续可替换为医生照片、品牌海报，或实时虚拟人视频窗口。</div><div class="briefing-item">若启用视频分身，只需开启后端配置并补齐对应参数。</div></div></div></div>`;
}

async function askQuestion() {
  const message = $("message").value.trim();
  if (!message) {
    return;
  }
  $("answer").textContent = "生成中...";
  try {
    const data = await postJson("/api/chat", {
      message,
      conversation: state.conversation,
    });
    $("answer").textContent = data.answer;
    state.conversation.push({ role: "user", content: message });
    state.conversation.push({ role: "assistant", content: data.answer });
  } catch (error) {
    $("answer").textContent = error.message;
  }
}

function renderList(id, items) {
  const el = $(id);
  el.innerHTML = "";
  (items || []).forEach((item) => {
    const li = document.createElement("li");
    li.textContent = item;
    el.appendChild(li);
  });
}

function renderSources(items) {
  const container = $("officialSources");
  container.innerHTML = "";
  (items || []).forEach((item) => {
    const a = document.createElement("a");
    a.href = item.url;
    a.target = "_blank";
    a.rel = "noreferrer";
    a.textContent = item.title;
    container.appendChild(a);
  });
}

async function loadProfile() {
  const profile = await getJson("/api/doctor-profile");
  state.doctorProfile = profile;
  $("brandSubtitle").textContent = `${profile.hospital} · ${profile.department}`;
  $("heroTitle").textContent = `${profile.name}医生虚拟人`;
  $("heroDescription").textContent = `${profile.public_tagline}。本页面依据公开职业资料构建，用于专科方向说明、常见问题答疑与就医参考。`;
  $("hospitalValue").textContent = profile.hospital || "-";
  $("departmentValue").textContent = profile.department || "-";
  $("doctorState").textContent = profile.name || "-";
  $("deptState").textContent = profile.department || "-";
  $("clinicNote").textContent = `提醒：${profile.clinic_note || "本页面仅供健康科普与就医参考，不替代面诊。"} ${profile.telephone ? `医院电话：${profile.telephone}。` : ""}`;
  $("doctorBio").textContent = [
    `${profile.name || ""}，${profile.title || ""}`,
    `${profile.hospital_alias || profile.hospital || ""}`,
    ...(profile.public_bio || []),
  ].filter(Boolean).join("\n");

  const tagContainer = $("focusTags");
  tagContainer.innerHTML = "";
  (profile.focus_areas || []).slice(0, 6).forEach((item) => {
    const span = document.createElement("span");
    span.className = "chip";
    span.textContent = item;
    tagContainer.appendChild(span);
  });

  renderList("focusList", profile.focus_areas || []);
  renderSources(profile.official_sources || []);
}

async function loadAppConfig() {
  const config = await getJson("/api/app-config");
  state.appConfig = config;
  const enabled = Boolean(config.video_avatar_enabled);
  const startBtn = $("startConsultBtn");
  const keepAliveBtn = $("keepAliveBtn");

  if (!enabled) {
    startBtn.textContent = "视频分身即将开放";
    keepAliveBtn.disabled = true;
    $("connectionState").textContent = "未启用";
    disconnectRoom();
  }
}

function wireUi() {
  $("startConsultBtn").addEventListener("click", startConsultation);
  $("keepAliveBtn").addEventListener("click", keepAlive);
  $("disconnectBtn").addEventListener("click", disconnectRoom);
  $("askBtn").addEventListener("click", askQuestion);
}

wireUi();
loadAppConfig().catch((error) => {
  $("answer").textContent = error.message;
});
loadProfile().catch((error) => {
  $("doctorBio").textContent = error.message;
});
