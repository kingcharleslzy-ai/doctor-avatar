const state = {
  room: null,
  sessionToken: "",
  startedSession: null,
  conversation: [],
  memorySummary: null,
};

function $(id) {
  return document.getElementById(id);
}

function log(message) {
  const el = $("eventLog");
  const time = new Date().toLocaleTimeString("zh-CN", { hour12: false });
  el.textContent = `[${time}] ${message}\n` + el.textContent;
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

function setBusy(id, busy, text = "处理中...") {
  const btn = $(id);
  btn.disabled = busy;
  if (busy) {
    btn.dataset.originalText = btn.textContent;
    btn.textContent = text;
  } else if (btn.dataset.originalText) {
    btn.textContent = btn.dataset.originalText;
  }
}

function escapeHtml(text) {
  return String(text || "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
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

  room.on(RoomEvent.Connected, () => log("LiveKit 已连接。"));
  room.on(RoomEvent.Disconnected, () => log("LiveKit 已断开。"));
  room.on(RoomEvent.ParticipantConnected, (participant) => {
    log(`远端参与者加入：${participant.identity}`);
  });
  room.on(RoomEvent.ParticipantDisconnected, (participant) => {
    log(`远端参与者离开：${participant.identity}`);
  });
  room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
    log(`订阅远端轨道：${participant.identity} / ${publication.kind}`);
    if (track.kind === Track.Kind.Video) {
      renderRemoteTrack(track);
    }
    if (track.kind === Track.Kind.Audio) {
      track.attach();
    }
  });
  room.on(RoomEvent.TrackUnsubscribed, (track) => {
    log(`取消订阅轨道：${track.kind}`);
  });
  room.on(RoomEvent.DataReceived, (payload, participant, kind, topic) => {
    const text = new TextDecoder().decode(payload);
    log(`数据事件(${topic || "no-topic"})：${text}`);
  });
}

async function connectLiveKit(startData) {
  if (!startData.livekit_url || !startData.livekit_client_token) {
    throw new Error("缺少 livekit_url 或 livekit_client_token，无法连接房间。");
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
  $("connectionState").textContent = "已连接";
  log("已开启麦克风并连入 LiveKit 房间。");
}

async function createToken() {
  setBusy("createTokenBtn", true);
  try {
    const data = await postJson("/api/liveavatar/token", {});

    state.sessionToken = data.data.session_token || "";
    $("sessionToken").value = state.sessionToken;
    $("apiResult").textContent = JSON.stringify(data, null, 2);
    log("已创建 session token。");
  } catch (error) {
    $("apiResult").textContent = error.message;
    log(`创建 token 失败：${error.message}`);
  } finally {
    setBusy("createTokenBtn", false);
  }
}

async function startSession() {
  const sessionToken = $("sessionToken").value.trim();
  if (!sessionToken) {
    log("请先创建或粘贴 session token。");
    return;
  }

  setBusy("startSessionBtn", true);
  try {
    const data = await postJson("/api/liveavatar/session", {
      session_token: sessionToken,
    });
    state.startedSession = data.data;
    $("apiResult").textContent = JSON.stringify(data, null, 2);
    $("sessionInfo").textContent = JSON.stringify(data.data, null, 2);
    log("LiveAvatar session 已启动。");
    await connectLiveKit(data.data);
  } catch (error) {
    $("apiResult").textContent = error.message;
    log(`启动 session 失败：${error.message}`);
  } finally {
    setBusy("startSessionBtn", false);
  }
}

async function keepAlive() {
  const sessionToken = $("sessionToken").value.trim();
  if (!sessionToken) {
    log("没有可续期的 session token。");
    return;
  }

  try {
    const data = await postJson("/api/liveavatar/keepalive", {
      session_token: sessionToken,
    });
    $("apiResult").textContent = JSON.stringify(data, null, 2);
    log("已发送 keep-alive。");
  } catch (error) {
    $("apiResult").textContent = error.message;
    log(`keep-alive 失败：${error.message}`);
  }
}

async function listSessions() {
  try {
    const data = await getJson("/api/liveavatar/sessions");
    $("apiResult").textContent = JSON.stringify(data, null, 2);
    log("已拉取当前 sessions 列表。");
  } catch (error) {
    $("apiResult").textContent = error.message;
    log(`获取 sessions 失败：${error.message}`);
  }
}

async function sendChat() {
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
    $("context").textContent = data.context_snippets.join("\n\n") || "没有命中知识片段。";
    state.conversation.push({ role: "user", content: message });
    state.conversation.push({ role: "assistant", content: data.answer });
    log("已生成一轮问答。");
  } catch (error) {
    $("answer").textContent = error.message;
    log(`问答失败：${error.message}`);
  }
}

function resetMemoryForm() {
  $("memoryKind").value = "";
  $("memorySource").value = "manual:console";
  $("memoryTitle").value = "";
  $("memoryImportance").value = "1.0";
  $("memoryTags").value = "";
  $("memoryContent").value = "";
  $("memorySaveResult").textContent = "表单已清空。";
}

function renderMemorySummary(data) {
  state.memorySummary = data;
  $("memoryCode").textContent = data.memory_code || "-";
  $("memoryTotal").textContent = String(data.total || 0);
  const topKinds = (data.kinds || []).slice(0, 3).map((item) => `${item.kind} (${item.count})`);
  $("memoryTopKinds").textContent = topKinds.join(" / ") || "-";
  $("memoryKindChips").innerHTML = (data.kinds || [])
    .map((item) => `<div class="kind-chip">${escapeHtml(item.kind)}<span>${item.count}</span></div>`)
    .join("");
}

async function loadMemorySummary() {
  try {
    const data = await getJson("/api/memory/summary");
    renderMemorySummary(data);
  } catch (error) {
    $("memoryCode").textContent = "读取失败";
    $("memoryTotal").textContent = "-";
    $("memoryTopKinds").textContent = "-";
    $("memoryKindChips").innerHTML = "";
    log(`读取资料概览失败：${error.message}`);
  }
}

function renderMemoryEntries(rows) {
  const container = $("memoryList");
  const stateEl = $("memoryListState");
  if (!rows.length) {
    container.innerHTML = "";
    stateEl.textContent = "当前筛选条件下没有资料。";
    return;
  }

  stateEl.textContent = `已载入 ${rows.length} 条资料。`;
  container.innerHTML = rows
    .map((row) => {
      const tags = (row.tags || []).map((tag) => `<span class="kind-chip">${escapeHtml(tag)}</span>`).join("");
      return `
        <article class="memory-item">
          <div class="memory-item-head">
            <div>
              <h4>${escapeHtml(row.title)}</h4>
              <div class="memory-meta">
                分类：${escapeHtml(row.kind)}<br />
                来源：${escapeHtml(row.source)}<br />
                重要度：${escapeHtml(row.importance)}<br />
                更新时间：${escapeHtml(row.updated_at)}
              </div>
            </div>
            <div class="memory-item-actions">
              <button class="button-ghost" data-copy-memory="${row.id}">复制</button>
              <button class="button-danger" data-delete-memory="${row.id}">删除</button>
            </div>
          </div>
          ${tags ? `<div class="kind-list">${tags}</div>` : ""}
          <div class="memory-content">${escapeHtml(row.content)}</div>
        </article>
      `;
    })
    .join("");

  container.querySelectorAll("[data-copy-memory]").forEach((button) => {
    button.addEventListener("click", async () => {
      const row = rows.find((item) => String(item.id) === button.dataset.copyMemory);
      if (!row) return;
      await navigator.clipboard.writeText(`${row.title}\n${row.content}`);
      log(`已复制资料：${row.title}`);
    });
  });

  container.querySelectorAll("[data-delete-memory]").forEach((button) => {
    button.addEventListener("click", async () => {
      const row = rows.find((item) => String(item.id) === button.dataset.deleteMemory);
      if (!row) return;
      if (!window.confirm(`确认删除这条资料？\n\n${row.title}`)) {
        return;
      }
      try {
        await postJson("/api/memory/entries/delete", { entry_ids: [row.id] });
        log(`已删除资料：${row.title}`);
        await Promise.all([loadMemorySummary(), loadMemoryList()]);
      } catch (error) {
        log(`删除资料失败：${error.message}`);
      }
    });
  });
}

async function loadMemoryList() {
  const query = $("memoryQuery").value.trim();
  const kind = $("memoryKindFilter").value.trim();
  const limit = $("memoryLimit").value.trim() || "40";
  const params = new URLSearchParams();
  if (query) params.set("q", query);
  if (kind) params.set("kind", kind);
  params.set("limit", limit);
  $("memoryListState").textContent = "读取中...";
  try {
    const rows = await getJson(`/api/memory/entries?${params.toString()}`);
    renderMemoryEntries(rows);
  } catch (error) {
    $("memoryList").innerHTML = "";
    $("memoryListState").textContent = error.message;
    log(`读取资料列表失败：${error.message}`);
  }
}

async function saveMemory() {
  const kind = $("memoryKind").value.trim();
  const title = $("memoryTitle").value.trim();
  const content = $("memoryContent").value.trim();
  if (!kind || !title || !content) {
    $("memorySaveResult").textContent = "请至少填写分类、标题和正文。";
    return;
  }

  setBusy("saveMemoryBtn", true, "保存中...");
  try {
    const payload = {
      kind,
      title,
      content,
      source: $("memorySource").value.trim() || "manual:console",
      importance: Number($("memoryImportance").value.trim() || "1.0"),
      tags: $("memoryTags").value.split(",").map((item) => item.trim()).filter(Boolean),
    };
    const row = await postJson("/api/memory/entries", payload);
    $("memorySaveResult").textContent = `已保存：${row.title}`;
    log(`已新增资料：${row.title}`);
    resetMemoryForm();
    $("memorySaveResult").textContent = `已保存：${row.title}`;
    await Promise.all([loadMemorySummary(), loadMemoryList()]);
  } catch (error) {
    $("memorySaveResult").textContent = error.message;
    log(`保存资料失败：${error.message}`);
  } finally {
    setBusy("saveMemoryBtn", false);
  }
}

async function disconnectRoom() {
  if (state.room) {
    await state.room.disconnect();
    state.room = null;
  }
  $("connectionState").textContent = "未连接";
  $("videoStage").innerHTML = "<div class=\"placeholder\"><strong>等待视频会话启动</strong>完成会话令牌创建与实时会话启动后，李勇医生虚拟人的远端视频将显示在此区域。</div>";
  log("已断开 LiveKit 房间。");
}

async function loadAppConfig() {
  try {
    const data = await getJson("/api/app-config");
    const liveavatar = data.liveavatar || {};
    const doctor = data.doctor || {};
    const runtime = data.runtime || {};
    $("runtimeInfo").textContent = [
      `应用版本：${runtime.version || "-"}`,
      `线上提交：${runtime.git_short_sha || "-"}`,
      `完整 SHA：${runtime.git_sha || "-"}`,
      `部署分支：${runtime.ref_name || "-"}`,
      `部署时间：${runtime.deployed_at || "-"}`,
      `部署来源：${runtime.source || "-"}`,
    ].join("\n");
    $("backendConfig").textContent = [
      `医生：${doctor.name || "-"} ${doctor.title ? ` / ${doctor.title}` : ""}`,
      `医院：${doctor.hospital || "-"}`,
      `科室：${doctor.department || "-"}`,
      `资料库暗号：${(data.doctor_memory && data.doctor_memory.memory_code) || "-"}`,
      `OpenAI 已配置：${data.openai_configured ? "是" : "否"}`,
      `HeyGen 已配置：${data.heygen_configured ? "是" : "否"}`,
      `模式：${liveavatar.mode || "-"}`,
      `语言：${liveavatar.language || "-"}`,
      `Sandbox：${liveavatar.sandbox ? "开启" : "关闭"}`,
      `Push-to-Talk：${liveavatar.push_to_talk ? "开启" : "关闭"}`,
      `Avatar 已配置：${liveavatar.avatar_configured ? "是" : "否"}`,
      `Voice 已配置：${liveavatar.voice_configured ? "是" : "否"}`,
      `Context 已配置：${liveavatar.context_configured ? "是" : "否"}`,
    ].join("\n");
  } catch (error) {
    $("backendConfig").textContent = error.message;
    $("runtimeInfo").textContent = error.message;
    log(`读取后端配置失败：${error.message}`);
  }
}

function wireUi() {
  $("createTokenBtn").addEventListener("click", createToken);
  $("startSessionBtn").addEventListener("click", startSession);
  $("keepAliveBtn").addEventListener("click", keepAlive);
  $("listSessionsBtn").addEventListener("click", listSessions);
  $("disconnectBtn").addEventListener("click", disconnectRoom);
  $("sendBtn").addEventListener("click", sendChat);
  $("saveMemoryBtn").addEventListener("click", saveMemory);
  $("resetMemoryBtn").addEventListener("click", resetMemoryForm);
  $("refreshMemoryBtn").addEventListener("click", loadMemoryList);
  $("clearMemoryFiltersBtn").addEventListener("click", () => {
    $("memoryQuery").value = "";
    $("memoryKindFilter").value = "";
    $("memoryLimit").value = "40";
    loadMemoryList();
  });
}

wireUi();
loadAppConfig();
resetMemoryForm();
loadMemorySummary();
loadMemoryList();
