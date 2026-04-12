from __future__ import annotations

import html as html_lib
from typing import Any, Dict, List, Optional, Tuple


def esc(x: Any) -> str:
    return html_lib.escape(str(x))


def dash(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, str) and x.strip() == "":
        return "—"
    return esc(x)


def fmt_bool(x: Any) -> str:
    if x is True:
        return "Да"
    if x is False:
        return "Нет"
    return "—"


def fmt_policy(policy: Any) -> str:
    if policy is None:
        return "—"
    policy = str(policy)
    if policy == "round_robin":
        return "Очередь свободных (round-robin)"
    if policy == "fastest":
        return "Самый быстрый (fastest)"
    return esc(policy)


def fmt_num(x: Any, digits: int = 6) -> str:
    try:
        if x is None:
            return "—"
        if isinstance(x, bool):
            return fmt_bool(x)
        if isinstance(x, int):
            return str(x)
        v = float(x)
        return f"{v:.{digits}f}"
    except Exception:
        return dash(x)


def to_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        return int(x)
    except Exception:
        return default


def to_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def render_kv_table(rows: List[Tuple[str, Any]]) -> str:
    trs = []
    for k, v in rows:
        val = dash(v) if not isinstance(v, (int, float)) else esc(v)
        trs.append(f"<tr><td class='k'>{esc(k)}</td><td class='v'>{val}</td></tr>")
    return "<table class='compact-table kv-table'><tbody>" + "".join(trs) + "</tbody></table>"


CALC_METRIC_NAMES: Dict[str, str] = {
    "p_served": "Pобс (вероятность обслуживания)",
    "throughput": "A (пропускная способность)",
    "p_refuse": "Pотк (вероятность отказа)",
    "p_busy_1": "P1 (занят 1 канал)",
    "p_busy_2": "P2 (заняты 2 канала)",
    "avg_busy_channels": "Nск (ср. занятых каналов)",
    "p_idle_at_least1": "P*1 (простой ≥1 канала)",
    "p_idle_2": "P*2 (простой 2 каналов)",
    "p_idle_system": "P*c (простой системы)",
    "avg_queue_len": "Nсз (ср. длина очереди)",
    "p_queue_1": "P1з (очередь=1)",
    "p_queue_2": "P2з (очередь=2)",
    "avg_wait_time": "Tож (ср. ожидание)",
    "avg_service_time": "Tобсл (ср. обслуживание)",
    "avg_system_time": "Tсист (ср. в системе)",
    "avg_system_count": "Nсист (ср. заявок в системе)",
}


def format_warmup(warmup: Any) -> str:
    if not isinstance(warmup, dict):
        return "—"
    mode = str(warmup.get("mode", "none"))
    value = warmup.get("value", 0)
    if mode == "none":
        return "Нет"
    if mode == "hours":
        return f"Пропустить первые {value} часов"
    if mode == "arrivals":
        return f"Пропустить первые {value} заявок"
    return f"{mode}={value}"