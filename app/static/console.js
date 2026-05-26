"use strict";

const $ = (id) => document.getElementById(id);

async function getJson(url) {
  const response = await fetch(url, { cache: "no-store" });
  if (!response.ok) throw new Error(`${url} HTTP ${response.status}`);
  return response.json();
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${url} HTTP ${response.status}: ${text}`);
  }
  return response.json();
}

function text(id, value) {
  const el = $(id);
  if (el) el.textContent = value;
}

function statusClass(el, ok) {
  if (!el) return;
  el.classList.toggle("status-ok", ok);
  el.classList.toggle("status-bad", !ok);
}

async function refreshAll() {
  const [config, ops, summary, entries] = await Promise.all([
    getJson("/api/app-config"),
    getJson("/api/ops/overview"),
    getJson("/api/memory/summary"),
    getJson(`/api/memory/entries?q=${encodeURIComponent($("memorySearch")?.value || "")}&limit=200`),
  ]);

  renderConfig(config);
  renderOps(ops);
  renderMemory(summary, entries, config.doctor_memory || {});
}

function renderConfig(config) {
  const realtime = config.doubao_realtime || {};
  const ok = Boolean(realtime.configured);
  text("doubaoStatus", ok ? "已配置" : "未配置");
  statusClass($("doubaoStatus"), ok);
  text(
    "doubaoDetail",
    ok
      ? `${realtime.model || "-"} / ${realtime.speaker || "-"} / ${realtime.websearch_enabled ? "联网开启" : "联网关闭"}`
      : `缺少：${(realtime.missing_fields || []).join("、") || "DOUBAO_REALTIME_API_KEY"}`
  );
  text("runtimeInfo", JSON.stringify({
    runtime: config.runtime,
    doubao_realtime: realtime,
    doctor: config.doctor,
    doctor_memory: config.doctor_memory,
  }, null, 2));
  const memoryBox = $("memoryWriteBox");
  if (memoryBox) memoryBox.style.display = config.doctor_memory?.write_enabled ? "block" : "none";
}

function renderOps(ops) {
  const traffic = ops.traffic || {};
  text("trafficStatus", String(traffic.requests_total ?? 0));
  text("trafficDetail", `错误 ${traffic.request_errors ?? 0} / 活跃 ${traffic.active_users ?? 0} / 平均 ${traffic.avg_latency_ms ?? 0}ms`);
  text("opsSnapshot", JSON.stringify(ops, null, 2));
}

function renderMemory(summary, entries, memoryConfig) {
  text("memoryStatus", String(summary.total ?? 0));
  text("memoryDetail", `${memoryConfig.write_enabled ? "可写" : "只读"} / code ${summary.memory_code || "-"}`);

  const rows = $("memoryRows");
  if (!rows) return;
  rows.innerHTML = "";
  entries.forEach((entry) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${entry.id}</td>
      <td>${escapeHtml(entry.kind)}</td>
      <td>${escapeHtml(entry.title)}</td>
      <td>${escapeHtml(entry.content).slice(0, 420)}</td>
      <td></td>
    `;
    const actionCell = tr.querySelector("td:last-child");
    const del = document.createElement("button");
    del.type = "button";
    del.className = "danger";
    del.textContent = "删除";
    del.disabled = !memoryConfig.write_enabled;
    del.addEventListener("click", async () => {
      if (!window.confirm(`删除资料 #${entry.id}？`)) return;
      await postJson("/api/memory/entries/delete", { entry_ids: [entry.id] });
      await refreshAll();
    });
    actionCell.appendChild(del);
    rows.appendChild(tr);
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function createMemory() {
  await postJson("/api/memory/entries", {
    kind: $("memoryKind").value.trim() || "note",
    title: $("memoryTitle").value.trim(),
    content: $("memoryContent").value.trim(),
    tags: ($("memoryTags").value || "").split(/[,，]/).map((x) => x.trim()).filter(Boolean),
    source: "console",
    importance: 1,
  });
  $("memoryTitle").value = "";
  $("memoryContent").value = "";
  $("memoryTags").value = "";
  await refreshAll();
}

function bind() {
  $("refreshBtn")?.addEventListener("click", refreshAll);
  $("memorySearchBtn")?.addEventListener("click", refreshAll);
  $("memorySearch")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") refreshAll();
  });
  $("memoryCreateBtn")?.addEventListener("click", createMemory);
}

document.addEventListener("DOMContentLoaded", () => {
  bind();
  refreshAll().catch((error) => {
    text("runtimeInfo", error.message || String(error));
  });
});
