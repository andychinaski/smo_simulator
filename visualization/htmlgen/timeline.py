from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

from .formatting import to_float, to_int, esc
from .queue_slots import assign_queue_slots, expand_server_names_from_config
from .svg_primitives import (
    svg_circle,
    svg_line,
    svg_polyline,
    svg_rect,
    svg_text,
    orthogonalize,
)


@dataclass(frozen=True)
class TimelineRender:
    labels_html: str
    svg_html: str
    base_w: int
    svg_h: float
    t_min: float
    t_max: float
    chart_x0: float
    chart_x1: float
    scale: float
    max_queue_slots_draw: int


def render_timeline(config: Dict[str, Any], reqs: List[Dict[str, Any]]) -> TimelineRender:
    queue_size = to_int(config.get("queue_size"), 0)

    # lanes for chart
    server_names = expand_server_names_from_config(config)
    observed_servers = sorted({
        str((r.get("server_name") or "Неизвестно"))
        for r in reqs
        if to_float(r.get("t_service_start")) is not None
    })
    for s in observed_servers:
        if s not in server_names:
            server_names.append(s)

    # ---- time range ----
    times: List[float] = [0.0]
    dur_f = to_float(config.get("duration"))
    if dur_f is not None and dur_f > 0:
        times.append(dur_f)

    for r in reqs:
        for k in ("t_arrival", "t_queue_enter", "t_service_start", "t_service_end", "t_refuse"):
            v = to_float(r.get(k))
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
    queue_segments = assign_queue_slots(reqs, draw_queue_slots, t_fallback_end)

    queue_slot_of: Dict[int, int] = {}
    for slot, rid, t0, _t1 in sorted(queue_segments, key=lambda x: (x[1], x[2])):
        queue_slot_of.setdefault(rid, slot)

    # ---- service segments ----
    service_segments: List[Tuple[str, int, float, float]] = []
    for r in reqs:
        rid = to_int(r.get("id", 0), 0)
        sname = str(r.get("server_name") or "Неизвестно")
        t0 = to_float(r.get("t_service_start"))
        t1 = to_float(r.get("t_service_end"))
        if t0 is None:
            continue
        if t1 is None:
            t1 = t_fallback_end
        service_segments.append((sname, rid, t0, t1))

    arrivals = [(to_int(r.get("id", 0), 0), to_float(r.get("t_arrival"))) for r in reqs]
    arrivals = [(rid, t) for rid, t in arrivals if t is not None]

    served = [(to_int(r.get("id", 0), 0), to_float(r.get("t_service_end"))) for r in reqs]
    served = [(rid, t) for rid, t in served if t is not None]

    refused = [(to_int(r.get("id", 0), 0), to_float(r.get("t_refuse"))) for r in reqs]
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
        labels_html.append(f'<div class="lane-label" style="height:{lane_row_h}px;">{esc(lname)}</div>')
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
    svg_parts.append(svg_rect(0, 0, base_w, svg_h, fill="#ffffff", stroke="#ffffff", nss=False))

    svg_parts.append('<g id="gridMinor"></g>')
    svg_parts.append('<g id="gridMajor"></g>')
    svg_parts.append('<g id="gridLabels"></g>')

    for i in range(len(lanes)):
        yc = lane_center(i)
        svg_parts.append(svg_line(chart_x0, yc, chart_x1, yc,
                                  stroke=TIMELINE_COLOR, width=TIMELINE_WIDTH, opacity=TIMELINE_OPACITY))
        yy = lane_y(i)
        svg_parts.append(svg_line(0, yy + LANE_H + LANE_GAP / 2, base_w, yy + LANE_H + LANE_GAP / 2,
                                  stroke="#f6f6f6", width=1, opacity=1.0))

    # connectors
    id_to_req = {to_int(r.get("id", 0), 0): r for r in reqs}

    arr_lane = lane_index["Поступление заявок"]
    done_lane = lane_index["Завершено обслуживание"]
    refuse_lane = lane_index["Отказ"]

    connector_parts: List[str] = []
    for rid, req in id_to_req.items():
        t_arr = to_float(req.get("t_arrival"))
        if t_arr is None:
            continue

        t_ref = to_float(req.get("t_refuse"))
        t_q = to_float(req.get("t_queue_enter"))
        t_s = to_float(req.get("t_service_start"))
        t_end = to_float(req.get("t_service_end"))

        event_points: List[Tuple[float, float]] = [(x(t_arr), lane_center(arr_lane))]

        if t_ref is not None:
            event_points.append((x(t_ref), lane_center(refuse_lane)))
            connector_parts.append(svg_polyline(orthogonalize(event_points), stroke="#5678ff", width=1.0, opacity=0.45))
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

        pts = orthogonalize(event_points)
        if len(pts) >= 2:
            connector_parts.append(svg_polyline(pts, stroke="#5678ff", width=1.0, opacity=0.45))

    svg_parts.append('<g id="connectors">')
    svg_parts.extend(connector_parts)
    svg_parts.append('</g>')

    yy_arr = lane_center(arr_lane)
    for rid, t in arrivals:
        cx = x(t)
        label = str(rid + 1)
        svg_parts.append(svg_circle(cx, yy_arr, 5, fill="#8aa8ff", stroke="#2546b8",
                                    title=f"Заявка {label}: поступление t={t:.6f}", css_class="no-xscale"))
        svg_parts.append(svg_text(cx, yy_arr - 11, label, size=10, anchor="middle", fill="#222", css_class="no-xscale"))

    for sname, rid, t0, t1 in service_segments:
        lane_name = f"Канал: {sname}"
        if lane_name not in lane_index:
            continue
        i = lane_index[lane_name]
        yy0 = lane_y(i) + (LANE_H - SEG_H) / 2
        x0 = x(t0)
        x1 = x(t1)
        label = str(rid + 1)
        svg_parts.append(svg_rect(x0, yy0, x1 - x0, SEG_H, fill="#b6e3a8", stroke="#3a7a2a", rx=4,
                                  title=f"Заявка {label} — обслуживание на «{sname}»\nstart={t0:.6f}, end={t1:.6f}"))
        svg_parts.append(svg_text((x0 + x1) / 2, yy0 + SEG_H - 2, label, size=10, anchor="middle",
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
        svg_parts.append(svg_rect(x0, yy0, x1 - x0, SEG_H, fill="#ffd08a", stroke="#b06a00", rx=4,
                                  title=f"Заявка {label} — ожидание в очереди (место {slot})\nenter={t0:.6f}, leave={t1:.6f}"))
        svg_parts.append(svg_text((x0 + x1) / 2, yy0 + SEG_H - 2, label, size=10, anchor="middle",
                                  fill="#5a3300", css_class="no-xscale"))

    yy_done = lane_center(done_lane)
    for rid, t in served:
        cx = x(t)
        label = str(rid + 1)
        svg_parts.append(svg_circle(cx, yy_done, 5, fill="#2ecc71", stroke="#1c7a44",
                                    title=f"Заявка {label}: выполнено (t={t:.6f})", css_class="no-xscale"))
        svg_parts.append(svg_text(cx, yy_done - 11, label, size=10, anchor="middle", fill="#145b32", css_class="no-xscale"))

    yy_ref = lane_center(refuse_lane)
    for rid, t in refused:
        cx = x(t)
        label = str(rid + 1)
        svg_parts.append(svg_circle(cx, yy_ref, 5, fill="#ff6b6b", stroke="#a11919",
                                    title=f"Заявка {label}: отказ t={t:.6f}", css_class="no-xscale"))
        svg_parts.append(svg_text(cx, yy_ref - 11, label, size=10, anchor="middle", fill="#7a1111", css_class="no-xscale"))

    svg_parts.append(svg_line(chart_x0, svg_h - 24, chart_x1, svg_h - 24, stroke="#888", width=1.2))
    svg_parts.append(svg_text(chart_x1, svg_h - 28, "t", size=12, anchor="end", fill="#555", css_class="no-xscale"))

    svg_parts.append("</svg>")
    svg_str = "\n".join(svg_parts)

    return TimelineRender(
        labels_html=labels_html_str,
        svg_html=svg_str,
        base_w=base_w,
        svg_h=svg_h,
        t_min=t_min,
        t_max=t_max,
        chart_x0=chart_x0,
        chart_x1=chart_x1,
        scale=scale,
        max_queue_slots_draw=MAX_QUEUE_SLOTS_DRAW,
    )