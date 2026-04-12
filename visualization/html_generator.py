# visualization/html_generator.py
from __future__ import annotations

import html as html_lib
import heapq
from typing import Any, Dict, List, Tuple, Optional


# ---------------- helpers (text/format) ----------------

def _esc(x: Any) -> str:
    return html_lib.escape(str(x))


def _dash(x: Any) -> str:
    if x is None:
        return "—"
    if isinstance(x, str) and x.strip() == "":
        return "—"
    return _esc(x)


def _fmt_bool(x: Any) -> str:
    if x is True:
        return "Да"
    if x is False:
        return "Нет"
    return "—"


def _fmt_policy(policy: Any) -> str:
    if policy is None:
        return "—"
    policy = str(policy)
    if policy == "round_robin":
        return "Очередь свободных (round-robin)"
    if policy == "fastest":
        return "Самый быстрый (fastest)"
    return _esc(policy)


def _fmt_num(x: Any, digits: int = 6) -> str:
    try:
        if x is None:
            return "—"
        if isinstance(x, bool):
            return _fmt_bool(x)
        if isinstance(x, int):
            return str(x)
        v = float(x)
        return f"{v:.{digits}f}"
    except Exception:
        return _dash(x)


def _to_int(x: Any, default: int = 0) -> int:
    try:
        if x is None:
            return default
        return int(x)
    except Exception:
        return default


def _to_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


def _render_kv_table(rows: List[Tuple[str, Any]]) -> str:
    trs = []
    for k, v in rows:
        trs.append(f"<tr><td class='k'>{_esc(k)}</td><td class='v'>{_dash(v) if not isinstance(v, (int, float)) else _esc(v)}</td></tr>")
    return "<table class='compact-table kv-table'><tbody>" + "".join(trs) + "</tbody></table>"


# short names for calculations keys (same keys as in calculations_tab)
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


def _format_warmup(warmup: Any) -> str:
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


# ---------------- build lanes (servers) ----------------

def _expand_server_names_from_config(config: Dict[str, Any]) -> List[str]:
    ops = config.get("operators") or []
    if not isinstance(ops, list):
        return []

    names: List[str] = []
    for op in ops:
        if not isinstance(op, dict):
            continue
        op_type = str(op.get("type", "Канал"))
        count = _to_int(op.get("count", 1), 1)
        for k in range(max(0, count)):
            names.append(f"{op_type} #{k + 1}")
    return names


# ---------------- queue slot reconstruction ----------------

def _assign_queue_slots(
    requests: List[Dict[str, Any]],
    queue_size: int,
    t_fallback_end: float,
) -> List[Tuple[int, int, float, float]]:
    if queue_size <= 0:
        return []

    events: List[Tuple[float, int, int]] = []
    # (time, priority, req_id) where priority: LEAVE=0, ENTER=1
    for r in requests:
        rid = _to_int(r.get("id", 0), 0)
        t_enter = _to_float(r.get("t_queue_enter"))
        t_leave = _to_float(r.get("t_service_start")) if t_enter is not None else None
        if t_enter is not None:
            events.append((t_enter, 1, rid))
        if t_leave is not None:
            events.append((t_leave, 0, rid))

    events.sort(key=lambda x: (x[0], x[1]))

    free_slots = list(range(1, queue_size + 1))
    heapq.heapify(free_slots)

    req_to_slot: Dict[int, int] = {}
    req_to_start: Dict[int, float] = {}
    segments: List[Tuple[int, int, float, float]] = []

    id_to_req = {_to_int(r.get("id", 0), 0): r for r in requests}

    for t, pr, rid in events:
        req = id_to_req.get(rid, {})
        t_enter = _to_float(req.get("t_queue_enter"))

        if pr == 0:
            if rid in req_to_slot:
                slot = req_to_slot.pop(rid)
                t0 = req_to_start.pop(rid)
                segments.append((slot, rid, t0, t))
                heapq.heappush(free_slots, slot)
        else:
            if t_enter is None:
                continue
            if rid in req_to_slot:
                continue
            if free_slots:
                slot = heapq.heappop(free_slots)
                req_to_slot[rid] = slot
                req_to_start[rid] = t_enter

    for rid, slot in req_to_slot.items():
        t0 = req_to_start.get(rid, None)
        if t0 is None:
            continue
        segments.append((slot, rid, t0, t_fallback_end))

    segments.sort(key=lambda x: (x[0], x[2], x[3]))
    return segments


# ---------------- SVG primitives ----------------

def _svg_text(
    x: float,
    y: float,
    text: str,
    size: int = 12,
    anchor: str = "start",
    fill: str = "#222",
    css_class: str = "",
) -> str:
    cls = f' class="{css_class}"' if css_class else ""
    return (
        f'<text{cls} x="{x:.2f}" y="{y:.2f}" font-size="{size}" '
        f'text-anchor="{anchor}" fill="{fill}">{_esc(text)}</text>'
    )


def _svg_line(
    x1: float, y1: float, x2: float, y2: float,
    stroke: str = "#bbb", width: float = 1.0, opacity: float = 1.0,
    nss: bool = True,
) -> str:
    ve = ' vector-effect="non-scaling-stroke"' if nss else ""
    return (
        f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
        f'stroke="{stroke}" stroke-width="{width}" opacity="{opacity}"{ve}/>'
    )


def _svg_rect(
    x: float, y: float, w: float, h: float,
    fill: str, stroke: str = "#333", rx: float = 4.0,
    title: str = "", nss: bool = True,
) -> str:
    w = max(1.0, w)
    t = f"<title>{_esc(title)}</title>" if title else ""
    ve = ' vector-effect="non-scaling-stroke"' if nss else ""
    return (
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
        f'rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1"{ve}>{t}</rect>'
    )


def _svg_circle(
    cx: float, cy: float, r: float,
    fill: str, stroke: str = "#333", title: str = "",
    css_class: str = "", nss: bool = True,
) -> str:
    t = f"<title>{_esc(title)}</title>" if title else ""
    cls = f' class="{css_class}"' if css_class else ""
    ve = ' vector-effect="non-scaling-stroke"' if nss else ""
    return f'<circle{cls} cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="1"{ve}>{t}</circle>'


def _svg_polyline(
    points: List[Tuple[float, float]],
    stroke: str = "#5b7cff",
    width: float = 1.0,
    opacity: float = 0.55,
    nss: bool = True,
) -> str:
    if len(points) < 2:
        return ""
    ve = ' vector-effect="non-scaling-stroke"' if nss else ""
    pts = " ".join(f"{px:.2f},{py:.2f}" for px, py in points)
    return f'<polyline points="{pts}" fill="none" stroke="{stroke}" stroke-width="{width}" opacity="{opacity}"{ve}/>'


def _orthogonalize(points: List[Tuple[float, float]], eps: float = 1e-9) -> List[Tuple[float, float]]:
    if not points:
        return points
    out: List[Tuple[float, float]] = [points[0]]

    for x2, y2 in points[1:]:
        x1, y1 = out[-1]
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)

        if dx <= eps and dy <= eps:
            continue

        if dx <= eps or dy <= eps:
            out.append((x2, y2))
            continue

        out.append((x2, y1))
        out.append((x2, y2))

    compact: List[Tuple[float, float]] = []
    for p in out:
        if not compact or (abs(compact[-1][0] - p[0]) > eps or abs(compact[-1][1] - p[1]) > eps):
            compact.append(p)
    return compact


# ---------------- public API ----------------

def build_html_from_saved_result(saved: Dict[str, Any]) -> str:
    if not isinstance(saved, dict):
        raise ValueError("Некорректный формат данных (ожидается JSON-объект)")

    config = saved.get("config")
    if not isinstance(config, dict):
        raise ValueError("В файле нет корректного поля 'config'")

    summary = saved.get("summary") if isinstance(saved.get("summary"), dict) else None
    calculations = saved.get("calculations") if isinstance(saved.get("calculations"), dict) else None

    reqs = saved.get("requests") or []
    if not isinstance(reqs, list):
        reqs = []

    call_flow = config.get("call_flow")
    queue_size = _to_int(config.get("queue_size"), 0)
    duration = config.get("duration")
    free_server_policy = config.get("free_server_policy")
    drain = config.get("drain")
    seed = config.get("seed")
    start_at_zero = config.get("start_at_zero")
    max_arrivals = config.get("max_arrivals")

    operators: List[Dict[str, Any]] = config.get("operators") or []
    if not isinstance(operators, list):
        operators = []

    # compact operators table
    operators_rows = []
    for op in operators:
        if not isinstance(op, dict):
            continue
        operators_rows.append(
            "<tr>"
            f"<td>{_dash(op.get('type'))}</td>"
            f"<td>{_dash(op.get('mu'))}</td>"
            f"<td>{_dash(op.get('count', 1))}</td>"
            "</tr>"
        )
    operators_table = (
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

    # summary block
    if summary:
        summary_table = _render_kv_table([
            ("Пришло заявок", summary.get("arrivals")),
            ("Обслужено", summary.get("served")),
            ("Отказов", summary.get("refused")),
        ])
    else:
        summary_table = "<div class='muted'>Нет данных summary (файл сразу после симуляции может не содержать этот блок).</div>"

    # calculations block (optional)
    if calculations:
        warm = _format_warmup(calculations.get("warmup"))
        selected_metrics = calculations.get("selected_metrics") or []
        results = calculations.get("results") or {}
        if not isinstance(selected_metrics, list):
            selected_metrics = []
        if not isinstance(results, dict):
            results = {}

        rows = []
        for k in selected_metrics:
            name = CALC_METRIC_NAMES.get(str(k), str(k))
            v = results.get(k)
            rows.append((name, _fmt_num(v, 6) if isinstance(v, (int, float)) else ("—" if v is None else _dash(v))))

        if rows:
            calc_table = "<table class='compact-table'><thead><tr><th>Показатель</th><th>Значение</th></tr></thead><tbody>"
            calc_table += "".join(f"<tr><td>{_esc(a)}</td><td>{_esc(b)}</td></tr>" for a, b in rows)
            calc_table += "</tbody></table>"
        else:
            calc_table = "<div class='muted'>Показатели не выбраны или результатов нет.</div>"

        calculations_html = (
            f"<div class='muted' style='margin-bottom:6px;'>Warm-up: <b>{_esc(warm)}</b></div>"
            f"{calc_table}"
        )
    else:
        calculations_html = "<div class='muted'>Нет данных calculations (это нормально, если файл сохранён сразу после симуляции).</div>"

    # model params compact table
    params_table = _render_kv_table([
        ("λ, заявок/час", call_flow),
        ("Размер очереди", queue_size),
        ("Длительность, часов", duration),
        ("Политика канала", _fmt_policy(free_server_policy)),
        ("Drain", _fmt_bool(drain)),
        ("Seed", seed if seed not in (None, "", "None") else "—"),
        ("start_at_zero", _fmt_bool(start_at_zero)),
        ("max_arrivals", max_arrivals if max_arrivals not in (None, "", "None") else "—"),
    ])

    # lanes for chart
    server_names = _expand_server_names_from_config(config)
    observed_servers = sorted({
        str((r.get("server_name") or "Неизвестно"))
        for r in reqs
        if _to_float(r.get("t_service_start")) is not None
    })
    for s in observed_servers:
        if s not in server_names:
            server_names.append(s)

    # ---- time range ----
    times: List[float] = [0.0]
    dur_f = _to_float(duration)
    if dur_f is not None and dur_f > 0:
        times.append(dur_f)

    for r in reqs:
        for k in ("t_arrival", "t_queue_enter", "t_service_start", "t_service_end", "t_refuse"):
            v = _to_float(r.get(k))
            if v is not None:
                times.append(v)

    t_min = 0.0
    t_max = max(times) if times else 1.0
    if t_max <= t_min:
        t_max = t_min + 1.0

    t_range = t_max - t_min
    t_fallback_end = t_max

    # ---- queue segments / slots ----
    MAX_QUEUE_SLOTS_DRAW = 20
    draw_queue_slots = min(queue_size, MAX_QUEUE_SLOTS_DRAW)
    queue_segments = _assign_queue_slots(reqs, draw_queue_slots, t_fallback_end)

    queue_slot_of: Dict[int, int] = {}
    for slot, rid, t0, _t1 in sorted(queue_segments, key=lambda x: (x[1], x[2])):
        queue_slot_of.setdefault(rid, slot)

    # ---- service segments ----
    service_segments: List[Tuple[str, int, float, float]] = []
    for r in reqs:
        rid = _to_int(r.get("id", 0), 0)
        sname = str(r.get("server_name") or "Неизвестно")
        t0 = _to_float(r.get("t_service_start"))
        t1 = _to_float(r.get("t_service_end"))
        if t0 is None:
            continue
        if t1 is None:
            t1 = t_fallback_end
        service_segments.append((sname, rid, t0, t1))

    arrivals = [( _to_int(r.get("id", 0), 0), _to_float(r.get("t_arrival")) ) for r in reqs]
    arrivals = [(rid, t) for rid, t in arrivals if t is not None]

    served = [( _to_int(r.get("id", 0), 0), _to_float(r.get("t_service_end")) ) for r in reqs]
    served = [(rid, t) for rid, t in served if t is not None]

    refused = [( _to_int(r.get("id", 0), 0), _to_float(r.get("t_refuse")) ) for r in reqs]
    refused = [(rid, t) for rid, t in refused if t is not None]

    # ---- chart sizing ----
    PX_PER_HOUR = 35
    BASE_W_MIN = 1200
    base_w = max(BASE_W_MIN, int(t_range * PX_PER_HOUR))

    TOP_MARGIN = 10
    LANE_H = 26
    LANE_GAP = 10
    SEG_H = 14
    BOTTOM_PAD = 40

    LABEL_COL_W = 250

    TIMELINE_COLOR = "#2f6fff"
    TIMELINE_OPACITY = 0.35
    TIMELINE_WIDTH = 1.0

    lanes: List[str] = []
    lanes.append("Поступление заявок")
    for s in server_names:
        lanes.append(f"Канал: {s}")
    if draw_queue_slots > 0:
        for i in range(1, draw_queue_slots + 1):
            lanes.append(f"Очередь — место {i}")
        if queue_size > draw_queue_slots:
            lanes.append(f"Очередь — остальные места (не показаны): {queue_size - draw_queue_slots}")
    lanes.append("Завершено обслуживание")
    lanes.append("Отказ")

    lane_index: Dict[str, int] = {name: i for i, name in enumerate(lanes)}
    svg_h = TOP_MARGIN + len(lanes) * (LANE_H + LANE_GAP) + BOTTOM_PAD

    scale = base_w / t_range
    chart_x0 = 0.0
    chart_x1 = float(base_w)

    def x(t: float) -> float:
        return (t - t_min) * scale

    def lane_y(i: int) -> float:
        return TOP_MARGIN + i * (LANE_H + LANE_GAP)

    def lane_center(i: int) -> float:
        return lane_y(i) + LANE_H / 2

    # ---- left fixed labels ----
    lane_row_h = LANE_H + LANE_GAP
    labels_html = []
    labels_html.append(f'<div class="lane-labels" style="padding-top:{TOP_MARGIN}px;width:{LABEL_COL_W}px;">')
    for lname in lanes:
        labels_html.append(f'<div class="lane-label" style="height:{lane_row_h}px;">{_esc(lname)}</div>')
    labels_html.append('</div>')
    labels_html_str = "\n".join(labels_html)

    # ---- SVG ----
    svg_parts: List[str] = []
    svg_parts.append(
        f'<svg id="timelineSvg" width="{base_w}" height="{svg_h}" '
        f'viewBox="0 0 {base_w} {svg_h}" preserveAspectRatio="none" '
        f'style="overflow: visible" '
        f'xmlns="http://www.w3.org/2000/svg">'
    )
    svg_parts.append(_svg_rect(0, 0, base_w, svg_h, fill="#ffffff", stroke="#ffffff", nss=False))

    svg_parts.append('<g id="gridMinor"></g>')
    svg_parts.append('<g id="gridMajor"></g>')
    svg_parts.append('<g id="gridLabels"></g>')

    for i in range(len(lanes)):
        yc = lane_center(i)
        svg_parts.append(_svg_line(chart_x0, yc, chart_x1, yc,
                                   stroke=TIMELINE_COLOR, width=TIMELINE_WIDTH, opacity=TIMELINE_OPACITY))
        yy = lane_y(i)
        svg_parts.append(_svg_line(0, yy + LANE_H + LANE_GAP / 2, base_w, yy + LANE_H + LANE_GAP / 2,
                                   stroke="#f6f6f6", width=1, opacity=1.0))

    # connectors
    id_to_req = {_to_int(r.get("id", 0), 0): r for r in reqs}

    arr_lane = lane_index["Поступление заявок"]
    done_lane = lane_index["Завершено обслуживание"]
    refuse_lane = lane_index["Отказ"]

    connector_parts: List[str] = []
    for rid, req in id_to_req.items():
        t_arr = _to_float(req.get("t_arrival"))
        if t_arr is None:
            continue

        t_ref = _to_float(req.get("t_refuse"))
        t_q = _to_float(req.get("t_queue_enter"))
        t_s = _to_float(req.get("t_service_start"))
        t_end = _to_float(req.get("t_service_end"))

        event_points: List[Tuple[float, float]] = [(x(t_arr), lane_center(arr_lane))]

        if t_ref is not None:
            event_points.append((x(t_ref), lane_center(refuse_lane)))
            connector_parts.append(_svg_polyline(_orthogonalize(event_points), stroke="#5678ff", width=1.0, opacity=0.45))
            continue

        if t_q is not None:
            slot = queue_slot_of.get(rid)
            if slot is not None:
                lane_name = f"Очередь — место {slot}"
                if lane_name in lane_index:
                    event_points.append((x(t_q), lane_center(lane_index[lane_name])))

        if t_s is not None:
            sname = str(req.get("server_name") or "Неизвестно")
            lane_name = f"Канал: {sname}"
            if lane_name in lane_index:
                event_points.append((x(t_s), lane_center(lane_index[lane_name])))

        if t_end is not None and t_s is not None:
            sname = str(req.get("server_name") or "Неизвестно")
            lane_name = f"Канал: {sname}"
            if lane_name in lane_index:
                event_points.append((x(t_end), lane_center(lane_index[lane_name])))
            event_points.append((x(t_end), lane_center(done_lane)))

        pts = _orthogonalize(event_points)
        if len(pts) >= 2:
            connector_parts.append(_svg_polyline(pts, stroke="#5678ff", width=1.0, opacity=0.45))

    svg_parts.append('<g id="connectors">')
    svg_parts.extend(connector_parts)
    svg_parts.append('</g>')

    yy_arr = lane_center(arr_lane)
    for rid, t in arrivals:
        cx = x(t)
        label = str(rid + 1)
        svg_parts.append(_svg_circle(cx, yy_arr, 5, fill="#8aa8ff", stroke="#2546b8",
                                     title=f"Заявка {label}: поступление t={t:.6f}", css_class="no-xscale"))
        svg_parts.append(_svg_text(cx, yy_arr - 11, label, size=10, anchor="middle", fill="#222", css_class="no-xscale"))

    for sname, rid, t0, t1 in service_segments:
        lane_name = f"Канал: {sname}"
        if lane_name not in lane_index:
            continue
        i = lane_index[lane_name]
        yy0 = lane_y(i) + (LANE_H - SEG_H) / 2
        x0 = x(t0)
        x1 = x(t1)
        label = str(rid + 1)
        svg_parts.append(_svg_rect(x0, yy0, x1 - x0, SEG_H, fill="#b6e3a8", stroke="#3a7a2a", rx=4,
                                   title=f"Заявка {label} — обслуживание на «{sname}»\nstart={t0:.6f}, end={t1:.6f}"))
        svg_parts.append(_svg_text((x0 + x1) / 2, yy0 + SEG_H - 2, label, size=10, anchor="middle",
                                   fill="#0f3b0f", css_class="no-xscale"))

    for slot, rid, t0, t1 in queue_segments:
        lane_name = f"Очередь — место {slot}"
        if lane_name not in lane_index:
            continue
        i = lane_index[lane_name]
        yy0 = lane_y(i) + (LANE_H - SEG_H) / 2
        x0 = x(t0)
        x1 = x(t1)
        label = str(rid + 1)
        svg_parts.append(_svg_rect(x0, yy0, x1 - x0, SEG_H, fill="#ffd08a", stroke="#b06a00", rx=4,
                                   title=f"Заявка {label} — ожидание в очереди (место {slot})\nenter={t0:.6f}, leave={t1:.6f}"))
        svg_parts.append(_svg_text((x0 + x1) / 2, yy0 + SEG_H - 2, label, size=10, anchor="middle",
                                   fill="#5a3300", css_class="no-xscale"))

    yy_done = lane_center(done_lane)
    for rid, t in served:
        cx = x(t)
        label = str(rid + 1)
        svg_parts.append(_svg_circle(cx, yy_done, 5, fill="#2ecc71", stroke="#1c7a44",
                                     title=f"Заявка {label}: выполнено (t={t:.6f})", css_class="no-xscale"))
        svg_parts.append(_svg_text(cx, yy_done - 11, label, size=10, anchor="middle", fill="#145b32", css_class="no-xscale"))

    yy_ref = lane_center(refuse_lane)
    for rid, t in refused:
        cx = x(t)
        label = str(rid + 1)
        svg_parts.append(_svg_circle(cx, yy_ref, 5, fill="#ff6b6b", stroke="#a11919",
                                     title=f"Заявка {label}: отказ t={t:.6f}", css_class="no-xscale"))
        svg_parts.append(_svg_text(cx, yy_ref - 11, label, size=10, anchor="middle", fill="#7a1111", css_class="no-xscale"))

    svg_parts.append(_svg_line(chart_x0, svg_h - 24, chart_x1, svg_h - 24, stroke="#888", width=1.2))
    svg_parts.append(_svg_text(chart_x1, svg_h - 28, "t", size=12, anchor="end", fill="#555", css_class="no-xscale"))

    svg_parts.append("</svg>")
    svg_str = "\n".join(svg_parts)

    # zoom UI
    zoom_stops = [0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0]
    zoom_min = 0.25
    zoom_max = 15.0

    html = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>Визуализация СМО</title>
  <style>
    :root {{
      --zoom: 1;
      --invZoom: 1;
    }}
    body {{
      font-family: Arial, sans-serif;
      margin: 18px 24px;
      color: #222;
    }}
    h1 {{ margin: 0 0 10px 0; }}
    h2 {{ margin: 0 0 8px 0; font-size: 15px; }}
    .muted {{ color:#666; font-size:12px; }}

    /* top info grid */
    .top-grid {{
      display: grid;
      grid-template-columns: 1fr 420px;
      gap: 14px;
      align-items: start;
    }}
    @media (max-width: 1100px) {{
      .top-grid {{ grid-template-columns: 1fr; }}
    }}
    .col {{
      display: flex;
      flex-direction: column;
      gap: 14px;
    }}
    .card {{
      border: 1px solid #ddd;
      background: #fbfbfb;
      padding: 10px;
    }}

    /* compact tables */
    .compact-table {{
      border-collapse: collapse;
      width: 100%;
      font-size: 12px;
      background: #fff;
    }}
    .compact-table th, .compact-table td {{
      border: 1px solid #ddd;
      padding: 4px 6px;
      text-align: left;
      vertical-align: top;
    }}
    .compact-table th {{
      background: #f3f3f3;
      font-weight: 600;
    }}
    .kv-table td.k {{ width: 58%; color:#555; }}
    .kv-table td.v {{ width: 42%; }}

    .section {{
      margin-top: 14px;
    }}

    /* timeline controls + layout */
    .timeline-controls {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin: 10px 0;
      user-select: none;
      flex-wrap: wrap;
    }}
    .timeline-controls button {{
      padding: 6px 10px;
      cursor: pointer;
    }}
    .timeline-controls .zoom-value {{
      font-size: 12px;
      color: #444;
      padding: 0 6px;
    }}
    .timeline-controls input[type="range"] {{
      width: 220px;
    }}
    .timeline-controls input[type="number"] {{
      width: 90px;
      padding: 6px 8px;
    }}

    .timeline-layout {{
      display: flex;
      border: 1px solid #ddd;
      background: #fff;
      max-width: 100%;
    }}
    .lane-labels {{
      flex: 0 0 auto;
      border-right: 1px solid #ddd;
      background: #fff;
    }}
    .lane-label {{
      display: flex;
      align-items: center;
      padding: 0 10px;
      font-size: 12px;
      border-bottom: 1px solid #f6f6f6;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .timeline-scroll {{
      flex: 1 1 auto;
      overflow-x: auto;
      overflow-y: hidden;
    }}

    #timelineSvg .no-xscale {{
      transform: scaleX(var(--invZoom));
      transform-origin: center;
      transform-box: fill-box;
    }}

    .timeline-svg-wrap {{
      padding: 10px 50px;
      display: inline-block;
    }}

    .note {{
      color: #666;
      font-size: 12px;
      margin-top: 6px;
    }}
  </style>
</head>
<body>
  <h1>Визуализация СМО</h1>

  <div class="top-grid">
    <div class="col">
      <div class="card">
        <h2>Параметры модели</h2>
        {params_table}
      </div>

      <div class="card">
        <h2>Каналы обслуживания</h2>
        {operators_table}
      </div>
    </div>

    <div class="col">
      <div class="card">
        <h2>Сводка (summary)</h2>
        {summary_table}
      </div>

      <div class="card">
        <h2>Расчёты (calculations)</h2>
        {calculations_html}
      </div>
    </div>
  </div>

  <div class="section">
    <h2>Временная диаграмма</h2>

    <div class="timeline-controls">
      <strong>Легенда:</strong>
      <span style="display:inline-flex;align-items:center;gap:6px;">
        <span style="display:inline-block;width:18px;height:10px;background:#b6e3a8;border:1px solid #3a7a2a;border-radius:2px;"></span>
        обслуживание
      </span>
      <span style="display:inline-flex;align-items:center;gap:6px;">
        <span style="display:inline-block;width:18px;height:10px;background:#ffd08a;border:1px solid #b06a00;border-radius:2px;"></span>
        ожидание
      </span>
      <span style="display:inline-flex;align-items:center;gap:6px;">
        <span style="display:inline-block;width:10px;height:10px;background:#8aa8ff;border:1px solid #2546b8;border-radius:50%;"></span>
        поступление
      </span>
      <span style="display:inline-flex;align-items:center;gap:6px;">
        <span style="display:inline-block;width:10px;height:10px;background:#2ecc71;border:1px solid #1c7a44;border-radius:50%;"></span>
        выполнено
      </span>
      <span style="display:inline-flex;align-items:center;gap:6px;">
        <span style="display:inline-block;width:10px;height:10px;background:#ff6b6b;border:1px solid #a11919;border-radius:50%;"></span>
        отказ
      </span>

      <span style="flex:1 1 auto;"></span>

      <button id="zoomOut" type="button">−</button>
      <button id="zoomIn" type="button">+</button>

      <input id="zoomSlider" type="range" min="0" max="{len(zoom_stops)-1}" step="1" value="5" />
      <input id="zoomInput" type="number" min="{zoom_min}" max="{zoom_max}" step="0.01" value="1.00" />

      <button id="zoomReset" type="button">Сброс</button>
      <span class="zoom-value">Масштаб: <span id="zoomValue">1.00x</span></span>
    </div>

    <div class="timeline-layout">
      {labels_html_str}
      <div class="timeline-scroll" id="timelineScroll">
        <div class="timeline-svg-wrap" id="timelineWrap">
          {svg_str}
        </div>
      </div>
    </div>

    <div class="note">
      Примечание: сетка рисуется только в видимой области. Масштабирование — по ширине.
      Если очередь больше {MAX_QUEUE_SLOTS_DRAW}, отображаются только первые {MAX_QUEUE_SLOTS_DRAW} мест.
    </div>
  </div>

  <script>
    (function() {{
      const baseWidth = {base_w};
      const tMin = {t_min};
      const tMax = {t_max};
      const chartX0 = {chart_x0};
      const chartX1 = {chart_x1};
      const scaleCoordPerHour = {scale};
      const svgH = {svg_h};

      const ZOOM_MIN = {zoom_min};
      const ZOOM_MAX = {zoom_max};
      const ZOOM_STOPS = {zoom_stops};

      let zoom = 1.0;

      const svg = document.getElementById('timelineSvg');
      const scroll = document.getElementById('timelineScroll');

      const zoomValue = document.getElementById('zoomValue');
      const zoomSlider = document.getElementById('zoomSlider');
      const zoomInput  = document.getElementById('zoomInput');

      const btnIn = document.getElementById('zoomIn');
      const btnOut = document.getElementById('zoomOut');
      const btnReset = document.getElementById('zoomReset');

      const gMinor = document.getElementById('gridMinor');
      const gMajor = document.getElementById('gridMajor');
      const gLabels = document.getElementById('gridLabels');

      const WRAP_PAD_X = 50;

      function clamp(v, lo, hi) {{ return Math.max(lo, Math.min(hi, v)); }}
      function round2(v) {{ return Math.round(v * 100) / 100; }}

      function snapZoom(v) {{
        v = clamp(v, ZOOM_MIN, ZOOM_MAX);
        return round2(v);
      }}

      function nearestStopIndex(z) {{
        let bestI = 0;
        let bestD = Infinity;
        for (let i = 0; i < ZOOM_STOPS.length; i++) {{
          const d = Math.abs(ZOOM_STOPS[i] - z);
          if (d < bestD) {{ bestD = d; bestI = i; }}
        }}
        return bestI;
      }}

      function nextStop(z) {{
        for (let i = 0; i < ZOOM_STOPS.length; i++) {{
          if (ZOOM_STOPS[i] > z + 1e-9) return ZOOM_STOPS[i];
        }}
        return ZOOM_STOPS[ZOOM_STOPS.length - 1];
      }}

      function prevStop(z) {{
        for (let i = ZOOM_STOPS.length - 1; i >= 0; i--) {{
          if (ZOOM_STOPS[i] < z - 1e-9) return ZOOM_STOPS[i];
        }}
        return ZOOM_STOPS[0];
      }}

      function clear(node) {{
        while (node.firstChild) node.removeChild(node.firstChild);
      }}

      const NICE_MINUTES = [
        1,2,5,10,15,30,
        60,120,180,240,360,480,720,1440,
        2880,4320,5760,7200
      ];

      function chooseStepHours(targetPx, pxPerHour) {{
        const targetHours = targetPx / Math.max(1e-9, pxPerHour);
        const targetMinutes = targetHours * 60.0;
        for (const m of NICE_MINUTES) {{
          if (m >= targetMinutes - 1e-9) return m / 60.0;
        }}
        return NICE_MINUTES[NICE_MINUTES.length - 1] / 60.0;
      }}

      function fmtTimeHM(hours) {{
        const totalMin = Math.round(hours * 60);
        const h = Math.floor(totalMin / 60);
        const m = Math.abs(totalMin % 60);
        return String(h) + ":" + String(m).padStart(2, "0");
      }}

      function timeToXCoord(t) {{
        return chartX0 + (t - tMin) * scaleCoordPerHour;
      }}

      function xCoordToTime(x) {{
        return tMin + (x - chartX0) / scaleCoordPerHour;
      }}

      function createVLine(x, stroke, width, opacity) {{
        const ln = document.createElementNS("http://www.w3.org/2000/svg", "line");
        ln.setAttribute("x1", x);
        ln.setAttribute("x2", x);
        ln.setAttribute("y1", 0);
        ln.setAttribute("y2", (svgH - 20).toString());
        ln.setAttribute("stroke", stroke);
        ln.setAttribute("stroke-width", width.toString());
        ln.setAttribute("opacity", opacity.toString());
        ln.setAttribute("vector-effect", "non-scaling-stroke");
        return ln;
      }}

      function createText(x, y, text) {{
        const tx = document.createElementNS("http://www.w3.org/2000/svg", "text");
        tx.setAttribute("x", x);
        tx.setAttribute("y", y);
        tx.setAttribute("text-anchor", "middle");
        tx.setAttribute("fill", "#555");
        tx.setAttribute("font-size", "11");
        tx.setAttribute("class", "no-xscale");
        tx.textContent = text;
        return tx;
      }}

      function niceCeil(v, step) {{
        return Math.ceil((v - 1e-9) / step) * step;
      }}

      function getDisplayedSvgWidth() {{
        return parseFloat(svg.getAttribute('width')) || baseWidth;
      }}

      function getVisibleViewBoxRange() {{
        const dispW = getDisplayedSvgWidth();

        let px0 = scroll.scrollLeft - WRAP_PAD_X;
        let px1 = scroll.scrollLeft + scroll.clientWidth - WRAP_PAD_X;

        px0 = Math.max(0, px0);
        px1 = Math.min(dispW, px1);

        const vx0 = (px0 / dispW) * baseWidth;
        const vx1 = (px1 / dispW) * baseWidth;

        const cx0 = Math.max(chartX0, vx0);
        const cx1 = Math.min(chartX1, vx1);

        return [cx0, cx1];
      }}

      function updateGridVisible() {{
        clear(gMinor);
        clear(gMajor);
        clear(gLabels);

        const dispW = getDisplayedSvgWidth();
        const pxPerHour = scaleCoordPerHour * (dispW / baseWidth);

        const [vx0, vx1] = getVisibleViewBoxRange();
        if (vx1 <= vx0 + 1e-9) return;

        let t0 = xCoordToTime(vx0);
        let t1 = xCoordToTime(vx1);

        const majorTargetPx = 160;
        const minorTargetPx = 40;

        let majorStep = chooseStepHours(majorTargetPx, pxPerHour);
        let minorStep = chooseStepHours(minorTargetPx, pxPerHour);

        if (minorStep >= majorStep) {{
          majorStep = chooseStepHours(majorTargetPx * 2, pxPerHour);
        }}

        const pad = majorStep * 2;
        t0 = Math.max(tMin, t0 - pad);
        t1 = Math.min(tMax, t1 + pad);

        const eps = 1e-8;

        let tm = niceCeil(t0, minorStep);
        for (let guard = 0; guard < 200000; guard++) {{
          if (tm > t1 + eps) break;
          const xx = timeToXCoord(tm);
          if (xx >= chartX0 - 1 && xx <= chartX1 + 1) {{
            const k = tm / majorStep;
            const isMajor = Math.abs(k - Math.round(k)) < 1e-6;
            if (!isMajor) {{
              gMinor.appendChild(createVLine(xx, "#f2f2f2", 1, 1.0));
            }}
          }}
          tm += minorStep;
        }}

        let tM = niceCeil(t0, majorStep);
        for (let guard = 0; guard < 200000; guard++) {{
          if (tM > t1 + eps) break;
          const xx = timeToXCoord(tM);
          if (xx >= chartX0 - 1 && xx <= chartX1 + 1) {{
            gMajor.appendChild(createVLine(xx, "#dcdcdc", 1, 1.0));
            gLabels.appendChild(createText(xx, (svgH - 8).toString(), fmtTimeHM(tM)));
          }}
          tM += majorStep;
        }}
      }}

      let rafPending = false;
      function scheduleGridUpdate() {{
        if (rafPending) return;
        rafPending = true;
        requestAnimationFrame(() => {{
          rafPending = false;
          updateGridVisible();
        }});
      }}

      function setUiFromZoom() {{
        zoomValue.textContent = zoom.toFixed(2) + 'x';
        zoomInput.value = zoom.toFixed(2);
        zoomSlider.value = String(nearestStopIndex(zoom));
      }}

      function applyZoom(newZoom, keepCenter=true) {{
        newZoom = snapZoom(newZoom);

        const oldZoom = zoom;
        const oldWidth = baseWidth * oldZoom;
        const newWidth = baseWidth * newZoom;

        let centerFrac = 0.0;
        if (keepCenter) {{
          const centerPx = (scroll.scrollLeft - WRAP_PAD_X) + scroll.clientWidth / 2;
          centerFrac = oldWidth > 0 ? (centerPx / oldWidth) : 0.0;
        }}

        zoom = newZoom;

        document.documentElement.style.setProperty('--zoom', zoom.toString());
        document.documentElement.style.setProperty('--invZoom', (1/zoom).toString());

        svg.setAttribute('width', Math.round(newWidth).toString());

        if (keepCenter) {{
          const newCenterPx = centerFrac * newWidth;
          scroll.scrollLeft = Math.max(0, (newCenterPx - scroll.clientWidth / 2) + WRAP_PAD_X);
        }}

        setUiFromZoom();
        scheduleGridUpdate();
      }}

      btnIn.addEventListener('click', () => applyZoom(nextStop(zoom), true));
      btnOut.addEventListener('click', () => applyZoom(prevStop(zoom), true));
      btnReset.addEventListener('click', () => applyZoom(1.0, false));

      zoomSlider.addEventListener('input', () => {{
        const idx = parseInt(zoomSlider.value, 10) || 0;
        applyZoom(ZOOM_STOPS[Math.max(0, Math.min(ZOOM_STOPS.length-1, idx))], true);
      }});

      function applyFromInput() {{
        const v = parseFloat(zoomInput.value);
        if (!isFinite(v)) {{
          setUiFromZoom();
          return;
        }}
        applyZoom(v, true);
      }}
      zoomInput.addEventListener('change', applyFromInput);
      zoomInput.addEventListener('keydown', (e) => {{
        if (e.key === 'Enter') {{
          zoomInput.blur();
          applyFromInput();
        }}
      }});

      scroll.addEventListener('scroll', scheduleGridUpdate, {{ passive: true }});
      window.addEventListener('resize', scheduleGridUpdate);

      applyZoom(1.0, false);
    }})();
  </script>
</body>
</html>
"""
    return html