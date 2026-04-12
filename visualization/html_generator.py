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
            # LEAVE
            if rid in req_to_slot:
                slot = req_to_slot.pop(rid)
                t0 = req_to_start.pop(rid)
                segments.append((slot, rid, t0, t))
                heapq.heappush(free_slots, slot)
        else:
            # ENTER
            if t_enter is None:
                continue
            if rid in req_to_slot:
                continue
            if free_slots:
                slot = heapq.heappop(free_slots)
                req_to_slot[rid] = slot
                req_to_start[rid] = t_enter

    # remaining queued -> till fallback_end
    for rid, slot in req_to_slot.items():
        t0 = req_to_start.get(rid, None)
        if t0 is None:
            continue
        segments.append((slot, rid, t0, t_fallback_end))

    segments.sort(key=lambda x: (x[0], x[2], x[3]))
    return segments


# ---------------- SVG primitives ----------------

def _svg_text(x: float, y: float, text: str, size: int = 12, anchor: str = "start", fill: str = "#222") -> str:
    return (
        f'<text x="{x:.2f}" y="{y:.2f}" font-size="{size}" '
        f'text-anchor="{anchor}" fill="{fill}">{_esc(text)}</text>'
    )


def _svg_line(x1: float, y1: float, x2: float, y2: float, stroke: str = "#bbb",
              width: float = 1.0, opacity: float = 1.0) -> str:
    return (
        f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" '
        f'stroke="{stroke}" stroke-width="{width}" opacity="{opacity}"/>'
    )


def _svg_rect(x: float, y: float, w: float, h: float, fill: str, stroke: str = "#333",
              rx: float = 4.0, title: str = "") -> str:
    w = max(1.0, w)
    t = f"<title>{_esc(title)}</title>" if title else ""
    return (
        f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}" height="{h:.2f}" '
        f'rx="{rx}" fill="{fill}" stroke="{stroke}" stroke-width="1">{t}</rect>'
    )


def _svg_circle(cx: float, cy: float, r: float, fill: str, stroke: str = "#333", title: str = "") -> str:
    t = f"<title>{_esc(title)}</title>" if title else ""
    return f'<circle cx="{cx:.2f}" cy="{cy:.2f}" r="{r:.2f}" fill="{fill}" stroke="{stroke}" stroke-width="1">{t}</circle>'


def _svg_polyline(points: List[Tuple[float, float]], stroke: str = "#5b7cff",
                  width: float = 1.0, opacity: float = 0.55) -> str:
    if len(points) < 2:
        return ""
    pts = " ".join(f"{px:.2f},{py:.2f}" for px, py in points)
    return f'<polyline points="{pts}" fill="none" stroke="{stroke}" stroke-width="{width}" opacity="{opacity}"/>'


def _nice_ticks(t_min: float, t_max: float, target: int = 10) -> List[float]:
    rng = max(1e-9, t_max - t_min)
    raw = rng / max(1, target)
    import math
    k = math.floor(math.log10(raw))
    base = raw / (10 ** k)
    if base <= 1:
        step = 1
    elif base <= 2:
        step = 2
    elif base <= 5:
        step = 5
    else:
        step = 10
    step *= (10 ** k)
    start = math.floor(t_min / step) * step
    end = math.ceil(t_max / step) * step
    ticks = []
    v = start
    for _ in range(10_000):
        if v > end + 1e-12:
            break
        if v >= t_min - 1e-12 and v <= t_max + 1e-12:
            ticks.append(v)
        v += step
    return ticks


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

        if dx <= eps:
            out.append((x2, y2))
            continue

        if dy <= eps:
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

    reqs = saved.get("requests") or []
    if not isinstance(reqs, list):
        reqs = []

    # ---- config fields ----
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

    # ---- operators table ----
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
        "<table>"
        "<thead><tr>"
        "<th>Тип канала</th>"
        "<th>Скорость обслуживания μ (заявок/час)</th>"
        "<th>Количество</th>"
        "</tr></thead>"
        "<tbody>"
        + ("".join(operators_rows) if operators_rows else "<tr><td colspan='3'>—</td></tr>")
        + "</tbody></table>"
    )

    # ---- servers (lanes) ----
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

    # ---- markers ----
    arrivals = [( _to_int(r.get("id", 0), 0), _to_float(r.get("t_arrival")) ) for r in reqs]
    arrivals = [(rid, t) for rid, t in arrivals if t is not None]

    served = [( _to_int(r.get("id", 0), 0), _to_float(r.get("t_service_end")) ) for r in reqs]
    served = [(rid, t) for rid, t in served if t is not None]

    refused = [( _to_int(r.get("id", 0), 0), _to_float(r.get("t_refuse")) ) for r in reqs]
    refused = [(rid, t) for rid, t in refused if t is not None]

    # ---- SVG layout ----
    SVG_WIDTH = 1100
    LEFT_MARGIN = 260
    RIGHT_MARGIN = 30

    HEADER_H = 44
    TOP_MARGIN = HEADER_H + 18

    LANE_H = 26
    LANE_GAP = 10
    SEG_H = 14

    # Цвет "таймлайна" (тонкая синяя линия для каждой строки)
    TIMELINE_COLOR = "#2f6fff"
    TIMELINE_OPACITY = 0.5
    TIMELINE_WIDTH = 2.0

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

    svg_h = TOP_MARGIN + len(lanes) * (LANE_H + LANE_GAP) + 50
    scale = (SVG_WIDTH - LEFT_MARGIN - RIGHT_MARGIN) / (t_max - t_min)

    def x(t: float) -> float:
        return LEFT_MARGIN + (t - t_min) * scale

    def lane_y(i: int) -> float:
        return TOP_MARGIN + i * (LANE_H + LANE_GAP)

    def lane_center(i: int) -> float:
        return lane_y(i) + LANE_H / 2

    chart_x0 = LEFT_MARGIN
    chart_x1 = SVG_WIDTH - RIGHT_MARGIN

    # ---- SVG content ----
    svg_parts: List[str] = []
    svg_parts.append(
        f'<svg width="{SVG_WIDTH}" height="{svg_h}" viewBox="0 0 {SVG_WIDTH} {svg_h}" '
        f'xmlns="http://www.w3.org/2000/svg">'
    )
    svg_parts.append(_svg_rect(0, 0, SVG_WIDTH, svg_h, fill="#ffffff", stroke="#ffffff"))

    # legend
    legend_y = 30
    legend_x = LEFT_MARGIN
    svg_parts.append(_svg_text(legend_x, legend_y - 3, "Легенда:", size=12, fill="#333"))

    lx = legend_x + 70
    svg_parts.append(_svg_rect(lx, legend_y - 12, 18, 10, fill="#b6e3a8", stroke="#3a7a2a", rx=2, title="Обслуживание"))
    svg_parts.append(_svg_text(lx + 26, legend_y - 3, "обслуживание", size=11, fill="#333"))

    lx += 130
    svg_parts.append(_svg_rect(lx, legend_y - 12, 18, 10, fill="#ffd08a", stroke="#b06a00", rx=2, title="Ожидание в очереди"))
    svg_parts.append(_svg_text(lx + 26, legend_y - 3, "ожидание", size=11, fill="#333"))

    lx += 110
    svg_parts.append(_svg_circle(lx + 8, legend_y - 7, 5, fill="#8aa8ff", stroke="#2546b8", title="Поступление"))
    svg_parts.append(_svg_text(lx + 20, legend_y - 3, "поступление", size=11, fill="#333"))

    lx += 125
    svg_parts.append(_svg_circle(lx + 8, legend_y - 7, 5, fill="#2ecc71", stroke="#1c7a44", title="Выполнено"))
    svg_parts.append(_svg_text(lx + 20, legend_y - 3, "выполнено", size=11, fill="#333"))

    lx += 110
    svg_parts.append(_svg_circle(lx + 8, legend_y - 7, 5, fill="#ff6b6b", stroke="#a11919", title="Отказ"))
    svg_parts.append(_svg_text(lx + 20, legend_y - 3, "отказ", size=11, fill="#333"))

    # vertical grid (ticks)
    ticks = _nice_ticks(t_min, t_max, target=10)
    for tv in ticks:
        xx = x(tv)
        svg_parts.append(_svg_line(xx, TOP_MARGIN - 6, xx, svg_h - 20, stroke="#e6e6e6", width=1))
        svg_parts.append(_svg_text(xx, svg_h - 6, f"{tv:.2f}", size=11, anchor="middle", fill="#555"))

    # lane labels + thin blue timeline for each lane
    for i, lname in enumerate(lanes):
        yy = lane_y(i)
        svg_parts.append(_svg_text(10, yy + LANE_H / 2 + 4, lname, size=12, anchor="start", fill="#333"))

        yc = yy + LANE_H / 2

        # ТОНКАЯ СИНЯЯ ЛИНИЯ (таймлайн) на всю ширину графика для каждой строки
        svg_parts.append(_svg_line(
            chart_x0, yc, chart_x1, yc,
            stroke=TIMELINE_COLOR, width=TIMELINE_WIDTH, opacity=TIMELINE_OPACITY
        ))

        # very light separator at bottom of lane
        svg_parts.append(_svg_line(
            10, yy + LANE_H + LANE_GAP / 2, SVG_WIDTH - 10, yy + LANE_H + LANE_GAP / 2,
            stroke="#f6f6f6", width=1
        ))

    # ---- connectors (orthogonal; end->done vertical) ----
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

        event_points: List[Tuple[float, float]] = []
        event_points.append((x(t_arr), lane_center(arr_lane)))

        if t_ref is not None:
            event_points.append((x(t_ref), lane_center(refuse_lane)))
            event_points = _orthogonalize(event_points)
            connector_parts.append(_svg_polyline(event_points, stroke="#5678ff", width=1.0, opacity=0.55))
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

        event_points = _orthogonalize(event_points)
        if len(event_points) >= 2:
            connector_parts.append(_svg_polyline(event_points, stroke="#5678ff", width=1.0, opacity=0.55))

    svg_parts.append('<g id="connectors">')
    svg_parts.extend(connector_parts)
    svg_parts.append('</g>')

    # ---- draw arrival markers ----
    yy = lane_center(arr_lane)
    for rid, t in arrivals:
        cx = x(t)
        label = str(rid + 1)
        svg_parts.append(_svg_circle(cx, yy, 5, fill="#8aa8ff", stroke="#2546b8",
                                     title=f"Заявка {label}: поступление t={t:.6f}"))
        svg_parts.append(_svg_text(cx, yy - 11, label, size=10, anchor="middle", fill="#222"))

    # ---- draw service segments ----
    for sname, rid, t0, t1 in service_segments:
        lane_name = f"Канал: {sname}"
        if lane_name not in lane_index:
            continue
        i = lane_index[lane_name]
        yy0 = lane_y(i) + (LANE_H - SEG_H) / 2
        x0 = x(t0)
        x1 = x(t1)
        label = str(rid + 1)
        svg_parts.append(_svg_rect(
            x0, yy0, x1 - x0, SEG_H,
            fill="#b6e3a8", stroke="#3a7a2a", rx=4,
            title=f"Заявка {label} — обслуживание на «{sname}»\nstart={t0:.6f}, end={t1:.6f}"
        ))
        svg_parts.append(_svg_text((x0 + x1) / 2, yy0 + SEG_H - 2, label, size=10, anchor="middle", fill="#0f3b0f"))

    # ---- draw queue segments ----
    for slot, rid, t0, t1 in queue_segments:
        lane_name = f"Очередь — место {slot}"
        if lane_name not in lane_index:
            continue
        i = lane_index[lane_name]
        yy0 = lane_y(i) + (LANE_H - SEG_H) / 2
        x0 = x(t0)
        x1 = x(t1)
        label = str(rid + 1)
        svg_parts.append(_svg_rect(
            x0, yy0, x1 - x0, SEG_H,
            fill="#ffd08a", stroke="#b06a00", rx=4,
            title=f"Заявка {label} — ожидание в очереди (место {slot})\nenter={t0:.6f}, leave={t1:.6f}"
        ))
        svg_parts.append(_svg_text((x0 + x1) / 2, yy0 + SEG_H - 2, label, size=10, anchor="middle", fill="#5a3300"))

    # ---- done markers ----
    yy = lane_center(done_lane)
    for rid, t in served:
        cx = x(t)
        label = str(rid + 1)
        svg_parts.append(_svg_circle(cx, yy, 5, fill="#2ecc71", stroke="#1c7a44",
                                     title=f"Заявка {label}: выполнено (t={t:.6f})"))
        svg_parts.append(_svg_text(cx, yy - 11, label, size=10, anchor="middle", fill="#145b32"))

    # ---- refused markers ----
    yy = lane_center(refuse_lane)
    for rid, t in refused:
        cx = x(t)
        label = str(rid + 1)
        svg_parts.append(_svg_circle(cx, yy, 5, fill="#ff6b6b", stroke="#a11919",
                                     title=f"Заявка {label}: отказ t={t:.6f}"))
        svg_parts.append(_svg_text(cx, yy - 11, label, size=10, anchor="middle", fill="#7a1111"))

    # x-axis
    svg_parts.append(_svg_line(chart_x0, svg_h - 24, chart_x1, svg_h - 24, stroke="#888", width=1.2))
    svg_parts.append(_svg_text(chart_x1, svg_h - 28, "t", size=12, anchor="end", fill="#555"))

    svg_parts.append("</svg>")
    svg = "\n".join(svg_parts)

    # ---- final HTML ----
    html = f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>Визуализация СМО</title>
  <style>
    body {{
      font-family: Arial, sans-serif;
      margin: 24px;
      color: #222;
    }}
    h1 {{ margin: 0 0 12px 0; }}
    .section {{ margin-top: 18px; }}
    table {{
      border-collapse: collapse;
      width: 100%;
      max-width: 1000px;
    }}
    th, td {{
      border: 1px solid #ccc;
      padding: 8px 10px;
      text-align: left;
      vertical-align: top;
    }}
    th {{ background: #f3f3f3; }}
    .kv {{
      max-width: 1000px;
      padding: 12px;
      border: 1px solid #ddd;
      background: #fbfbfb;
    }}
    .kv div {{ margin: 6px 0; }}
    .k {{
      display: inline-block;
      min-width: 360px;
      color: #555;
    }}
    .note {{
      color: #666;
      font-size: 12px;
      margin-top: 6px;
    }}
    .svg-wrap {{
      border: 1px solid #ddd;
      background: white;
      padding: 10px;
      overflow-x: auto;
      max-width: 100%;
    }}
  </style>
</head>
<body>
  <h1>Визуализация СМО</h1>

  <div class="section">
    <h2>Параметры модели</h2>
    <div class="kv">
      <div><span class="k">Интенсивность потока заявок (λ), заявок/час:</span> {_dash(call_flow)}</div>
      <div><span class="k">Размер очереди (макс. заявок в ожидании):</span> {_dash(queue_size)}</div>
      <div><span class="k">Длительность моделирования, часов:</span> {_dash(duration)}</div>
      <div><span class="k">Политика выбора свободного канала:</span> {_fmt_policy(free_server_policy)}</div>
      <div><span class="k">Доработать хвост после duration (drain):</span> {_fmt_bool(drain)}</div>
      <div><span class="k">Seed (воспроизводимость):</span> {_dash(seed)}</div>
      <div><span class="k">Первая заявка в момент t = 0 (start_at_zero):</span> {_fmt_bool(start_at_zero)}</div>
      <div><span class="k">Ограничение числа заявок (max_arrivals):</span> {_dash(max_arrivals)}</div>
    </div>
  </div>

  <div class="section">
    <h2>Каналы обслуживания</h2>
    {operators_table}
  </div>

  <div class="section">
    <h2>Временная диаграмма</h2>
    <div class="svg-wrap">
      {svg}
    </div>
    <div class="note">
      Примечание: времена указаны в часах. Переходы заявок соединены линиями без диагоналей.
      Места очереди восстанавливаются по событиям «вход в очередь» и «старт обслуживания».
      Если очередь больше {MAX_QUEUE_SLOTS_DRAW}, отображаются только первые {MAX_QUEUE_SLOTS_DRAW} мест.
    </div>
  </div>

</body>
</html>
"""
    return html