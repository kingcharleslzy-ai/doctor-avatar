from __future__ import annotations

import os
import shutil
import threading
import time
import ctypes
from collections import Counter
from pathlib import Path
from typing import Any


_STARTED_AT = time.time()
_LOCK = threading.Lock()
_REQUESTS_TOTAL = 0
_REQUEST_ERRORS = 0
_REQUEST_TIME_MS = 0.0
_PATH_COUNTS: Counter[str] = Counter()
_OPENAI_CALLS = 0
_OPENAI_ERRORS = 0
_OPENAI_INPUT_TOKENS = 0
_OPENAI_OUTPUT_TOKENS = 0
_OPENAI_TOTAL_TOKENS = 0
_OPENAI_LAST_MODEL = ""
_PRESENCE: dict[str, dict[str, Any]] = {}


def record_request(path: str, status_code: int, duration_ms: float) -> None:
    global _REQUESTS_TOTAL, _REQUEST_ERRORS, _REQUEST_TIME_MS
    normalized_path = path or "/"
    with _LOCK:
        _REQUESTS_TOTAL += 1
        if status_code >= 400:
            _REQUEST_ERRORS += 1
        _REQUEST_TIME_MS += duration_ms
        _PATH_COUNTS[normalized_path] += 1


def record_openai_usage(model: str, usage: Any) -> None:
    global _OPENAI_CALLS, _OPENAI_INPUT_TOKENS, _OPENAI_OUTPUT_TOKENS, _OPENAI_TOTAL_TOKENS, _OPENAI_LAST_MODEL
    input_tokens = _usage_value(usage, "input_tokens")
    output_tokens = _usage_value(usage, "output_tokens")
    total_tokens = _usage_value(usage, "total_tokens")
    with _LOCK:
        _OPENAI_CALLS += 1
        _OPENAI_INPUT_TOKENS += input_tokens
        _OPENAI_OUTPUT_TOKENS += output_tokens
        _OPENAI_TOTAL_TOKENS += total_tokens
        _OPENAI_LAST_MODEL = model


def record_openai_error() -> None:
    global _OPENAI_ERRORS
    with _LOCK:
        _OPENAI_ERRORS += 1


def record_presence(session_id: str, user_agent: str | None = None) -> None:
    now = time.time()
    with _LOCK:
        _PRESENCE[session_id] = {"last_seen": now, "user_agent": user_agent or ""}
        _prune_presence_locked(now)


def monitor_snapshot(db_path: Path) -> dict[str, Any]:
    now = time.time()
    with _LOCK:
        _prune_presence_locked(now)
        requests_total = _REQUESTS_TOTAL
        request_errors = _REQUEST_ERRORS
        request_time_ms = _REQUEST_TIME_MS
        path_counts = _PATH_COUNTS.most_common(6)
        openai_calls = _OPENAI_CALLS
        openai_errors = _OPENAI_ERRORS
        openai_input_tokens = _OPENAI_INPUT_TOKENS
        openai_output_tokens = _OPENAI_OUTPUT_TOKENS
        openai_total_tokens = _OPENAI_TOTAL_TOKENS
        openai_last_model = _OPENAI_LAST_MODEL
        active_users = len(_PRESENCE)

    uptime_seconds = max(0, int(now - _STARTED_AT))
    avg_latency_ms = round(request_time_ms / requests_total, 2) if requests_total else 0.0

    return {
        "uptime_seconds": uptime_seconds,
        "server": {
            "cpu": _cpu_snapshot(),
            "memory": _memory_snapshot(),
            "disk": _disk_snapshot(db_path),
            "network": _network_snapshot(),
        },
        "traffic": {
            "active_users": active_users,
            "requests_total": requests_total,
            "request_errors": request_errors,
            "avg_latency_ms": avg_latency_ms,
            "top_paths": [{"path": path, "count": count} for path, count in path_counts],
        },
        "api_usage": {
            "openai_calls": openai_calls,
            "openai_errors": openai_errors,
            "openai_input_tokens": openai_input_tokens,
            "openai_output_tokens": openai_output_tokens,
            "openai_total_tokens": openai_total_tokens,
            "openai_last_model": openai_last_model or None,
        },
    }


def _usage_value(usage: Any, key: str) -> int:
    if usage is None:
        return 0
    candidate_keys = [key]
    if key == "input_tokens":
        candidate_keys.extend(["prompt_tokens", "promptTokens"])
    elif key == "output_tokens":
        candidate_keys.extend(["completion_tokens", "completionTokens"])
    elif key == "total_tokens":
        candidate_keys.extend(["totalTokens"])

    value = None
    for candidate in candidate_keys:
        value = getattr(usage, candidate, None)
        if value is None and isinstance(usage, dict):
            value = usage.get(candidate)
        if value is not None:
            break
    return int(value or 0)


def _prune_presence_locked(now: float) -> None:
    stale_ids = [session_id for session_id, row in _PRESENCE.items() if now - float(row.get("last_seen", 0)) > 150]
    for session_id in stale_ids:
        _PRESENCE.pop(session_id, None)


def _cpu_snapshot() -> dict[str, Any]:
    cpu_count = os.cpu_count() or 1
    try:
        load1, load5, load15 = os.getloadavg()
    except (AttributeError, OSError):
        load1 = load5 = load15 = 0.0
    load_percent = min(100.0, round((load1 / cpu_count) * 100, 2))
    return {
        "cpu_count": cpu_count,
        "load_1m": round(load1, 2),
        "load_5m": round(load5, 2),
        "load_15m": round(load15, 2),
        "load_percent": load_percent,
    }


def _memory_snapshot() -> dict[str, Any]:
    meminfo = Path("/proc/meminfo")
    total_kb = 0
    available_kb = 0
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8").splitlines():
            if line.startswith("MemTotal:"):
                total_kb = int(line.split()[1])
            elif line.startswith("MemAvailable:"):
                available_kb = int(line.split()[1])
    elif os.name == "nt":
        total_kb, available_kb = _windows_memory_kb()
    used_kb = max(0, total_kb - available_kb)
    used_percent = round((used_kb / total_kb) * 100, 2) if total_kb else 0.0
    return {
        "total_mb": round(total_kb / 1024, 1),
        "used_mb": round(used_kb / 1024, 1),
        "available_mb": round(available_kb / 1024, 1),
        "used_percent": used_percent,
    }


def _disk_snapshot(db_path: Path) -> dict[str, Any]:
    target = db_path.parent if db_path.parent.exists() else Path("/")
    usage = shutil.disk_usage(target)
    used = usage.total - usage.free
    used_percent = round((used / usage.total) * 100, 2) if usage.total else 0.0
    return {
        "path": str(target),
        "total_gb": round(usage.total / (1024 ** 3), 2),
        "used_gb": round(used / (1024 ** 3), 2),
        "free_gb": round(usage.free / (1024 ** 3), 2),
        "used_percent": used_percent,
    }


def _network_snapshot() -> dict[str, Any]:
    rx_bytes = 0
    tx_bytes = 0
    netdev = Path("/proc/net/dev")
    if netdev.exists():
        for line in netdev.read_text(encoding="utf-8").splitlines()[2:]:
            if ":" not in line:
                continue
            iface, payload = line.split(":", 1)
            iface = iface.strip()
            if iface == "lo":
                continue
            fields = payload.split()
            if len(fields) >= 16:
                rx_bytes += int(fields[0])
                tx_bytes += int(fields[8])
    return {
        "rx_bytes": rx_bytes,
        "tx_bytes": tx_bytes,
    }


def _windows_memory_kb() -> tuple[int, int]:
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("sullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
        return 0, 0
    return int(stat.ullTotalPhys / 1024), int(stat.ullAvailPhys / 1024)
