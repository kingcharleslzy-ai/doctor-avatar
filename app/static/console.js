const state = {
  room: null,
  sessionToken: "",
  startedSession: null,
  conversation: [],
  memorySummary: null,
  opsSnapshot: null,
  networkBaseline: null,
  opsTimer: null,
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

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(2)} GB`;
  if (value >= 1024 ** 2) return `${(value / 1024 ** 2).toFixed(1)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} B`;
}

function formatSpeed(bytesPerSec) {
  const value = Number(bytesPerSec || 0);
  if (value <= 0) return "0 B/s";
  return `${formatBytes(value)}/s`;
}

function formatUptime(seconds) {
  const total = Number(seconds || 0);
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days}天 ${hours}小时 ${minutes}分钟`;
  if (hours > 0) return `${hours}小时 ${minutes}分钟`;
  return `${minutes}分钟`;
}

function stagePlaceholderMarkup() {
  return `
    <div class="placeholder">
      <div class="placeholder-visual">
        <div class="scanline"></div>
      </div>
      <strong>等待视频会话启动</strong>
      令牌创建、会话启动、房间接入完成后，远端数字分身会直接落在这里。
    </div>
  `;
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
  if (!message) return;
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

function renderMemorySummary(data) {
  state.memorySummary = data;
  $("memoryCode").textContent = data.memory_code || "-";
  if ($("memoryCodeHero")) $("memoryCodeHero").textContent = data.memory_code || "-";
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
  const total = state.memorySummary?.total || rows.length;
  if (!rows.length) {
    container.innerHTML = "";
    stateEl.textContent = "当前筛选条件下没有资料。";
    return;
  }

  stateEl.textContent = `当前显示 ${rows.length} / ${total} 条资料。`;
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
                更新时间：${escapeHtml(row.updated_at)}
              </div>
            </div>
            <div class="memory-item-actions">
              <button class="button-ghost" data-copy-memory="${row.id}">复制</button>
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
}

async function loadMemoryList() {
  const query = $("memoryQuery").value.trim();
  const kind = $("memoryKindFilter").value.trim();
  const limit = $("memoryLimit").value.trim() || "100";
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

function renderOpsOverview(data) {
  state.opsSnapshot = data;
  const cpu = data.server?.cpu || {};
  const memory = data.server?.memory || {};
  const disk = data.server?.disk || {};
  const network = data.server?.network || {};
  const traffic = data.traffic || {};
  const apiUsage = data.api_usage || {};
  const doctorMemory = data.doctor_memory || {};

  $("cpuUsage").textContent = `${cpu.load_percent ?? 0}%`;
  $("memoryUsage").textContent = `${memory.used_percent ?? 0}%`;
  $("diskUsage").textContent = `${disk.used_percent ?? 0}%`;
  $("activeUsers").textContent = String(traffic.active_users ?? 0);
  if ($("activeUsersMini")) $("activeUsersMini").textContent = String(traffic.active_users ?? 0);
  $("requestTotal").textContent = String(traffic.requests_total ?? 0);
  $("openaiCalls").textContent = String(apiUsage.openai_calls ?? 0);
  if ($("openaiCallsMini")) $("openaiCallsMini").textContent = String(apiUsage.openai_calls ?? 0);
  $("avgLatency").textContent = `${traffic.avg_latency_ms ?? 0} ms`;
  $("requestErrors").textContent = String(traffic.request_errors ?? 0);
  $("uptimeValue").textContent = formatUptime(data.uptime_seconds ?? 0);
  $("writeMode").textContent = doctorMemory.write_enabled ? "已开启（危险）" : "只读模式";
  if ($("writeModeChip")) $("writeModeChip").textContent = doctorMemory.write_enabled ? "可写" : "只读";
  $("apiTokenInfo").textContent = [
    `OpenAI 调用：${apiUsage.openai_calls ?? 0}`,
    `OpenAI 错误：${apiUsage.openai_errors ?? 0}`,
    `输入 tokens：${apiUsage.openai_input_tokens ?? 0}`,
    `输出 tokens：${apiUsage.openai_output_tokens ?? 0}`,
    `总 tokens：${apiUsage.openai_total_tokens ?? 0}`,
    `最近模型：${apiUsage.openai_last_model || "-"}`
  ].join("\n");
  $("resourceInfo").textContent = [
    `CPU：${cpu.cpu_count ?? "-"} 核 / 1m 负载 ${cpu.load_1m ?? "-"}`,
    `内存：已用 ${memory.used_mb ?? "-"} MB / ${memory.total_mb ?? "-"} MB`,
    `磁盘：已用 ${disk.used_gb ?? "-"} GB / ${disk.total_gb ?? "-"} GB`,
    `路径：${disk.path || "-"}`
  ].join("\n");
  $("topPaths").textContent = (traffic.top_paths || [])
    .map((item) => `${item.path} · ${item.count}`)
    .join("\n") || "暂无数据。";

  updateNetworkSpeed(network.rx_bytes || 0, network.tx_bytes || 0);
}

function updateNetworkSpeed(rxBytes, txBytes) {
  const now = Date.now();
  if (state.networkBaseline) {
    const seconds = Math.max(1, (now - state.networkBaseline.at) / 1000);
    const rxRate = (rxBytes - state.networkBaseline.rx) / seconds;
    const txRate = (txBytes - state.networkBaseline.tx) / seconds;
    $("networkRx").textContent = `${formatBytes(rxBytes)} / ${formatSpeed(rxRate)}`;
    $("networkTx").textContent = `${formatBytes(txBytes)} / ${formatSpeed(txRate)}`;
  } else {
    $("networkRx").textContent = `${formatBytes(rxBytes)} / 计算中`;
    $("networkTx").textContent = `${formatBytes(txBytes)} / 计算中`;
  }
  state.networkBaseline = { rx: rxBytes, tx: txBytes, at: now };
}

async function loadOpsOverview() {
  try {
    const data = await getJson("/api/ops/overview");
    renderOpsOverview(data);
  } catch (error) {
    $("cpuUsage").textContent = "读取失败";
    $("memoryUsage").textContent = "读取失败";
    $("diskUsage").textContent = "读取失败";
    $("activeUsers").textContent = "-";
    $("requestTotal").textContent = "-";
    $("openaiCalls").textContent = "-";
    $("avgLatency").textContent = "-";
    $("requestErrors").textContent = "-";
    $("uptimeValue").textContent = "-";
    $("writeMode").textContent = "-";
    $("networkRx").textContent = "-";
    $("networkTx").textContent = "-";
    $("apiTokenInfo").textContent = error.message;
    $("resourceInfo").textContent = error.message;
    $("topPaths").textContent = error.message;
    log(`读取系统监控失败：${error.message}`);
  }
}

async function disconnectRoom() {
  if (state.room) {
    await state.room.disconnect();
    state.room = null;
  }
  $("connectionState").textContent = "未连接";
  $("videoStage").innerHTML = stagePlaceholderMarkup();
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
    if ($("runtimeShortSha")) $("runtimeShortSha").textContent = runtime.git_short_sha || "-";
    $("backendConfig").textContent = [
      `医生：${doctor.name || "-"} ${doctor.title ? ` / ${doctor.title}` : ""}`,
      `医院：${doctor.hospital || "-"}`,
      `科室：${doctor.department || "-"}`,
      `资料库暗号：${(data.doctor_memory && data.doctor_memory.memory_code) || "-"}`,
      `资料写入：${data.doctor_memory?.write_enabled ? "已开启（危险）" : "只读模式"}`,
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
    if ($("modeBadge")) $("modeBadge").textContent = liveavatar.mode || "-";
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
  $("refreshMemoryBtn").addEventListener("click", loadMemoryList);
  $("refreshOpsBtn").addEventListener("click", async () => {
    await Promise.all([loadOpsOverview(), loadMemorySummary(), loadMemoryList()]);
  });
  $("clearMemoryFiltersBtn").addEventListener("click", () => {
    $("memoryQuery").value = "";
    $("memoryKindFilter").value = "";
    $("memoryLimit").value = "100";
    loadMemoryList();
  });
}

function startPolling() {
  if (state.opsTimer) clearInterval(state.opsTimer);
  state.opsTimer = setInterval(() => {
    loadOpsOverview();
  }, 10000);
}

wireUi();
loadAppConfig();
loadMemorySummary();
loadMemoryList();
loadOpsOverview();
startPolling();
