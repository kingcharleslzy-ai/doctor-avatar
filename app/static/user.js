const state = {
  room: null,
  sessionToken: "",
  conversation: [],
  doctorProfile: null,
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
  $("videoStage").innerHTML = `<div class="video-placeholder"><strong>等待接入李勇医生虚拟人</strong>点击“开始视频咨询”后，远端视频会在这里加载。请在浏览器弹出权限时允许麦克风访问。</div>`;
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

function wireUi() {
  $("startConsultBtn").addEventListener("click", startConsultation);
  $("keepAliveBtn").addEventListener("click", keepAlive);
  $("disconnectBtn").addEventListener("click", disconnectRoom);
  $("askBtn").addEventListener("click", askQuestion);
}

wireUi();
loadProfile().catch((error) => {
  $("doctorBio").textContent = error.message;
});
