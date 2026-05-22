from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from .formatting import (
    CALC_METRIC_NAMES,
    dash,
    esc,
    fmt_bool,
    fmt_num,
    fmt_policy,
    format_warmup,
    render_kv_table,
)


def _safe_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _safe_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        return int(x)
    except Exception:
        return default


def _total_channels(config: Dict[str, Any], requests: List[Dict[str, Any]]) -> int:
    operators = config.get("operators")
    if isinstance(operators, list):
        total = 0
        for op in operators:
            if isinstance(op, dict):
                total += max(0, _safe_int(op.get("count"), 1))
        if total > 0:
            return total

    max_server_id = -1
    for request in requests:
        if isinstance(request, dict):
            max_server_id = max(max_server_id, _safe_int(request.get("server_id"), -1))
    return max_server_id + 1 if max_server_id >= 0 else 0


def _state_time_by_level(intervals: List[Tuple[float, float]], t0: float, t1: float) -> Dict[int, float]:
    events: List[Tuple[float, int]] = []
    for start, end in intervals:
        a = max(t0, float(start))
        b = min(t1, float(end))
        if b > a:
            events.append((a, 1))
            events.append((b, -1))

    if t1 <= t0:
        return {}

    events.sort(key=lambda item: (item[0], -item[1]))
    times: Dict[int, float] = {}
    level = 0
    prev = t0
    i = 0

    while i < len(events):
        t = min(max(events[i][0], t0), t1)
        if t > prev:
            times[level] = times.get(level, 0.0) + (t - prev)
            prev = t

        event_t = events[i][0]
        while i < len(events) and events[i][0] == event_t:
            level += events[i][1]
            i += 1

    if prev < t1:
        times[level] = times.get(level, 0.0) + (t1 - prev)

    return times


def _warmup_cut_time(warmup: Any, requests: List[Dict[str, Any]], duration: float) -> float:
    if not isinstance(warmup, dict):
        return 0.0

    mode = str(warmup.get("mode", "none"))
    n = _safe_int(warmup.get("value"), 0)
    if mode == "none" or n <= 0:
        return 0.0
    if mode == "hours":
        return float(min(max(0, n), int(duration)))
    if mode == "arrivals":
        if n >= len(requests):
            return float(duration)
        t = _safe_float(requests[n].get("t_arrival")) if isinstance(requests[n], dict) else None
        return float(t) if t is not None else 0.0
    return 0.0


def _sum_product_text(times: Dict[int, float]) -> str:
    if not times:
        return "0"
    return " + ".join(f"{level}*{fmt_num(value, 6)}" for level, value in sorted(times.items()))


def _levels_text(prefix: str, times: Dict[int, float]) -> str:
    if not times:
        return f"{prefix}: нет интервалов"
    return "; ".join(f"{prefix}({level})={fmt_num(value, 6)} ч" for level, value in sorted(times.items()))


def _build_calculation_context(
    config: Optional[Dict[str, Any]],
    requests: Optional[List[Dict[str, Any]]],
    calculations: Dict[str, Any],
) -> Dict[str, Any]:
    if not isinstance(config, dict) or not isinstance(requests, list):
        return {}

    duration = _safe_float(config.get("duration"))
    if duration is None or duration <= 0:
        return {}

    t0 = _warmup_cut_time(calculations.get("warmup"), requests, duration)
    t1 = float(duration)
    tn = max(0.0, t1 - t0)

    def in_interval(t: Optional[float]) -> bool:
        return t is not None and (t0 <= t <= t1)

    observed_served: List[Dict[str, Any]] = []
    observed_refused: List[Dict[str, Any]] = []

    for request in requests:
        if not isinstance(request, dict):
            continue
        t_arr = _safe_float(request.get("t_arrival"))
        if not in_interval(t_arr):
            continue

        t_ref = _safe_float(request.get("t_refuse"))
        if in_interval(t_ref):
            observed_refused.append(request)
            continue

        t_start = _safe_float(request.get("t_service_start"))
        t_end = _safe_float(request.get("t_service_end"))
        if in_interval(t_start) and in_interval(t_end):
            observed_served.append(request)

    waits: List[float] = []
    service_times: List[float] = []
    busy_intervals: List[Tuple[float, float]] = []
    queue_intervals: List[Tuple[float, float]] = []
    system_intervals: List[Tuple[float, float]] = []

    for request in observed_served:
        t_arr = _safe_float(request.get("t_arrival"))
        t_start = _safe_float(request.get("t_service_start"))
        t_end = _safe_float(request.get("t_service_end"))
        if t_arr is None or t_start is None or t_end is None:
            continue

        wait = max(0.0, t_start - t_arr)
        if wait > 0:
            waits.append(wait)
        service_times.append(max(0.0, t_end - t_start))

        busy_intervals.append((t_start, t_end))
        system_intervals.append((t_arr, t_end))

        queue_history = request.get("queue_history")
        if isinstance(queue_history, list) and queue_history:
            for entry in queue_history:
                if not isinstance(entry, dict):
                    continue
                q_enter = _safe_float(entry.get("t_enter"))
                q_leave = _safe_float(entry.get("t_leave"))
                if q_enter is not None and q_leave is not None and q_leave > q_enter:
                    queue_intervals.append((q_enter, q_leave))
        else:
            t_queue_enter = _safe_float(request.get("t_queue_enter"))
            if t_queue_enter is not None and t_start > t_queue_enter:
                queue_intervals.append((t_queue_enter, t_start))

    busy_time_by_count = _state_time_by_level(busy_intervals, t0, t1)
    queue_time_by_count = _state_time_by_level(queue_intervals, t0, t1)
    system_time_by_count = _state_time_by_level(system_intervals, t0, t1)
    channels_count = _total_channels(config, requests)

    idle_at_least1 = None
    idle_2 = None
    if channels_count > 0:
        idle_at_least1 = sum(t for busy_count, t in busy_time_by_count.items() if busy_count < channels_count)
        idle_2 = sum(t for busy_count, t in busy_time_by_count.items() if channels_count - busy_count == 2)

    return {
        "t0": t0,
        "t1": t1,
        "tn": tn,
        "n_serv": len(observed_served),
        "n_ref": len(observed_refused),
        "n": len(observed_served) + len(observed_refused),
        "channels_count": channels_count,
        "busy_time_by_count": busy_time_by_count,
        "queue_time_by_count": queue_time_by_count,
        "system_time_by_count": system_time_by_count,
        "idle_at_least1": idle_at_least1,
        "idle_2": idle_2,
        "sum_waits": sum(waits),
        "wait_count": len(waits),
        "sum_service_times": sum(service_times),
        "service_count": len(service_times),
    }


def _calculation_formula(metric_key: str, ctx: Dict[str, Any], value: Any) -> Tuple[str, str]:
    if not ctx:
        return ("—", "Нет исходных данных для подстановки")

    tn = ctx["tn"]
    n_serv = ctx["n_serv"]
    n_ref = ctx["n_ref"]
    n = ctx["n"]
    channels_count = ctx["channels_count"]
    busy = ctx["busy_time_by_count"]
    queue = ctx["queue_time_by_count"]
    system = ctx["system_time_by_count"]
    result_text = fmt_num(value, 6) if isinstance(value, (int, float)) else "—"

    formulas: Dict[str, Tuple[str, str]] = {
        "p_served": (
            "Pобс = Nобс / N",
            f"Nобс={n_serv}; N={n}. Pобс = {n_serv} / {n} = {result_text}",
        ),
        "throughput": (
            "A = Nобс / Tн",
            f"Nобс={n_serv}; Tн={fmt_num(tn, 6)} ч. A = {n_serv} / {fmt_num(tn, 6)} = {result_text}",
        ),
        "p_refuse": (
            "Pотк = Nотк / N",
            f"Nотк={n_ref}; N={n}. Pотк = {n_ref} / {n} = {result_text}",
        ),
        "p_busy_1": (
            "P1 = Tзан(1 канал) / Tн",
            f"Tзан(1 канал)={fmt_num(busy.get(1, 0.0), 6)} ч; Tн={fmt_num(tn, 6)} ч. P1 = {fmt_num(busy.get(1, 0.0), 6)} / {fmt_num(tn, 6)} = {result_text}",
        ),
        "p_busy_2": (
            "P2 = Tзан(2 канала) / Tн",
            f"Tзан(2 канала)={fmt_num(busy.get(2, 0.0), 6)} ч; Tн={fmt_num(tn, 6)} ч. P2 = {fmt_num(busy.get(2, 0.0), 6)} / {fmt_num(tn, 6)} = {result_text}",
        ),
        "avg_busy_channels": (
            "Nск = Σ k*Tзан(k) / Tн",
            f"{_levels_text('Tзан', busy)}; Tн={fmt_num(tn, 6)} ч. Nск = ({_sum_product_text(busy)}) / {fmt_num(tn, 6)} = {result_text}",
        ),
        "p_idle_at_least1": (
            "P*1 = Tпростоя(>=1 канал) / Tн",
            f"Всего каналов={channels_count}; Tпростоя(>=1 канал)={fmt_num(ctx['idle_at_least1'], 6)} ч; Tн={fmt_num(tn, 6)} ч. P*1 = {fmt_num(ctx['idle_at_least1'], 6)} / {fmt_num(tn, 6)} = {result_text}",
        ),
        "p_idle_2": (
            "P*2 = Tпростоя(2 канала) / Tн",
            f"Всего каналов={channels_count}; Tпростоя(2 канала)={fmt_num(ctx['idle_2'], 6)} ч; Tн={fmt_num(tn, 6)} ч. P*2 = {fmt_num(ctx['idle_2'], 6)} / {fmt_num(tn, 6)} = {result_text}",
        ),
        "p_idle_system": (
            "P*c = Tзан(0 каналов) / Tн",
            f"Tзан(0 каналов)={fmt_num(busy.get(0, 0.0), 6)} ч; Tн={fmt_num(tn, 6)} ч. P*c = {fmt_num(busy.get(0, 0.0), 6)} / {fmt_num(tn, 6)} = {result_text}",
        ),
        "avg_queue_len": (
            "Nсз = Σ k*Tоч(k) / Tн",
            f"{_levels_text('Tоч', queue)}; Tн={fmt_num(tn, 6)} ч. Nсз = ({_sum_product_text(queue)}) / {fmt_num(tn, 6)} = {result_text}",
        ),
        "p_queue_1": (
            "P1з = Tоч(1 заявка) / Tн",
            f"Tоч(1 заявка)={fmt_num(queue.get(1, 0.0), 6)} ч; Tн={fmt_num(tn, 6)} ч. P1з = {fmt_num(queue.get(1, 0.0), 6)} / {fmt_num(tn, 6)} = {result_text}",
        ),
        "p_queue_2": (
            "P2з = Tоч(2 заявки) / Tн",
            f"Tоч(2 заявки)={fmt_num(queue.get(2, 0.0), 6)} ч; Tн={fmt_num(tn, 6)} ч. P2з = {fmt_num(queue.get(2, 0.0), 6)} / {fmt_num(tn, 6)} = {result_text}",
        ),
        "avg_wait_time": (
            "Tож = Σ tож / nож",
            f"Σtож={fmt_num(ctx['sum_waits'], 6)} ч; nож={ctx['wait_count']}. Tож = {fmt_num(ctx['sum_waits'], 6)} / {ctx['wait_count']} = {result_text}",
        ),
        "avg_service_time": (
            "Tобсл = Σ tобсл / Nобс",
            f"Σtобсл={fmt_num(ctx['sum_service_times'], 6)} ч; Nобс={ctx['service_count']}. Tобсл = {fmt_num(ctx['sum_service_times'], 6)} / {ctx['service_count']} = {result_text}",
        ),
        "avg_system_count": (
            "Nсист = Σ k*Tсист(k) / Tн",
            f"{_levels_text('Tсист', system)}; Tн={fmt_num(tn, 6)} ч. Nсист = ({_sum_product_text(system)}) / {fmt_num(tn, 6)} = {result_text}",
        ),
    }

    if metric_key == "avg_system_time":
        avg_wait = ctx["sum_waits"] / ctx["wait_count"] if ctx["wait_count"] else 0.0
        avg_service = ctx["sum_service_times"] / ctx["service_count"] if ctx["service_count"] else None
        return (
            "Tсист = Tож + Tобсл",
            f"Tож={fmt_num(avg_wait, 6)} ч; Tобсл={fmt_num(avg_service, 6)} ч. Tсист = {fmt_num(avg_wait, 6)} + {fmt_num(avg_service, 6)} = {result_text}",
        )

    return formulas.get(metric_key, ("—", "Для показателя нет описания формулы"))


def build_operators_table(config: Dict[str, Any]) -> str:
    operators: List[Dict[str, Any]] = config.get("operators") or []
    if not isinstance(operators, list):
        operators = []

    operators_rows = []
    for op in operators:
        if not isinstance(op, dict):
            continue
        operators_rows.append(
            "<tr>"
            f"<td>{dash(op.get('type'))}</td>"
            f"<td>{dash(op.get('mu'))}</td>"
            f"<td>{dash(op.get('count', 1))}</td>"
            "</tr>"
        )

    return (
        "<table class='compact-table'>"
        "<thead><tr>"
        "<th>Тип</th>"
        "<th>μ (заявок/час)</th>"
        "<th>Кол-во</th>"
        "</tr></thead>"
        "<tbody>"
        + ("".join(operators_rows) if operators_rows else "<tr><td colspan='3'>—</td></tr>")
        + "</tbody></table>"
    )


def build_summary_table(summary: Optional[Dict[str, Any]]) -> str:
    if summary:
        return render_kv_table([
            ("Пришло заявок", summary.get("arrivals")),
            ("Обслужено", summary.get("served")),
            ("Отказов", summary.get("refused")),
        ])
    return "<div class='muted'>Нет данных summary (файл сразу после симуляции может не содержать этот блок).</div>"


def build_calculations_html(
    calculations: Optional[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
    requests: Optional[List[Dict[str, Any]]] = None,
) -> str:
    if not calculations:
        return "<div class='muted'>Нет данных calculations (это нормально, если файл сохранён сразу после симуляции).</div>"

    warm = format_warmup(calculations.get("warmup"))
    selected_metrics = calculations.get("selected_metrics") or []
    results = calculations.get("results") or {}
    if not isinstance(selected_metrics, list):
        selected_metrics = []
    if not isinstance(results, dict):
        results = {}

    context = _build_calculation_context(config, requests, calculations)
    rows = []
    for k in selected_metrics:
        name = CALC_METRIC_NAMES.get(str(k), str(k))
        v = results.get(k)
        formula, substitution = _calculation_formula(str(k), context, v)
        rows.append((
            name,
            fmt_num(v, 6) if isinstance(v, (int, float)) else ("—" if v is None else dash(v)),
            formula,
            substitution,
        ))

    if rows:
        calc_table = (
            "<table class='compact-table calc-table'><thead><tr>"
            "<th>Показатель</th><th>Значение</th><th>Формула</th><th>Подстановка значений</th>"
            "</tr></thead><tbody>"
        )
        calc_table += "".join(
            f"<tr><td>{esc(name)}</td><td>{esc(value)}</td><td>{esc(formula)}</td><td>{esc(substitution)}</td></tr>"
            for name, value, formula, substitution in rows
        )
        calc_table += "</tbody></table>"
    else:
        calc_table = "<div class='muted'>Показатели не выбраны или результатов нет.</div>"

    return (
        f"<div class='muted' style='margin-bottom:6px;'>Warm-up: <b>{esc(warm)}</b></div>"
        f"{calc_table}"
    )


def build_params_table(config: Dict[str, Any]) -> str:
    return render_kv_table([
        ("λ, заявок/час", config.get("call_flow")),
        ("Размер очереди", config.get("queue_size")),
        ("Длительность, часов", config.get("duration")),
        ("Политика канала", fmt_policy(config.get("free_server_policy"))),
        ("Drain", fmt_bool(config.get("drain"))),
        ("Seed", config.get("seed") if config.get("seed") not in (None, "", "None") else "—"),
        ("start_at_zero", fmt_bool(config.get("start_at_zero"))),
        ("max_arrivals", config.get("max_arrivals") if config.get("max_arrivals") not in (None, "", "None") else "—"),
    ])
