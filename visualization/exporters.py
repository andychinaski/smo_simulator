from __future__ import annotations

import math
import zipfile
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape as xml_escape

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPainterPath, QPen

from .htmlgen.formatting import CALC_METRIC_NAMES, to_float, to_int
from .htmlgen.queue_slots import assign_queue_slots, expand_server_names_from_config


ARRIVAL_LANE = "Поступление заявок"
DONE_LANE = "Завершено обслуживание"
REFUSE_LANE = "Отказ"


@dataclass(frozen=True)
class PngExportOptions:
    image_width: int = 1300
    hours_per_strip: float = 3.0
    tick_step: float = 0.5


def export_timeline_xlsx(saved: Dict[str, Any], path: str) -> None:
    config, requests = _extract_payload(saved)
    lanes = _build_lanes(config, requests)
    request_ids = _sorted_request_ids(requests)
    id_to_req = {to_int(r.get("id"), 0): r for r in requests}
    queue_slot_times = _queue_slot_enter_times(config, requests)

    rows: List[List[Any]] = []
    rows.append([""] + [rid + 1 for rid in request_ids])

    for lane in lanes:
        row: List[Any] = [lane]
        for rid in request_ids:
            req = id_to_req.get(rid, {})
            row.append(_time_for_lane(lane, req, queue_slot_times.get((lane, rid))))
        rows.append(row)

    _write_xlsx(rows, path)


def export_calculation_parameters_xlsx(saved_results: Sequence[Dict[str, Any]], path: str) -> None:
    experiments = _extract_calculation_experiments(saved_results)
    if not experiments:
        raise ValueError("Нет корректных JSON-файлов с блоком calculations.results")

    experiments.sort(key=lambda item: _capacity_sort_value(item[0]))
    metric_keys = _collect_calculation_metric_keys(experiments)
    rows: List[List[Any]] = [[
        "Суммарная пропускная способность каналов",
        *[CALC_METRIC_NAMES.get(key, key) for key in metric_keys],
    ]]

    for config, results in experiments:
        rows.append([
            _total_service_capacity(config),
            *[results.get(key) for key in metric_keys],
        ])

    _write_xlsx(rows, path)


def export_timeline_png(saved: Dict[str, Any], path: str, options: Optional[PngExportOptions] = None) -> None:
    config, requests = _extract_payload(saved)
    opts = options or PngExportOptions()
    image = render_timeline_png(config, requests, opts)
    if not image.save(path, "PNG"):
        raise RuntimeError("Не удалось сохранить PNG")


def render_timeline_png(
    config: Dict[str, Any],
    requests: List[Dict[str, Any]],
    options: PngExportOptions,
) -> QImage:
    lanes = _build_lanes(config, requests)
    t_min, t_max = _time_range(config, requests)
    strip_hours = max(0.25, float(options.hours_per_strip))
    tick_step = max(0.05, float(options.tick_step))
    width = max(900, int(options.image_width))

    label_w = 230
    right_pad = 24
    chart_x0 = label_w
    chart_w = max(300, width - label_w - right_pad)
    scale = chart_w / strip_hours

    lane_h = 24
    lane_gap = 8
    axis_h = 34
    strip_gap = 28
    title_h = 58
    bottom_pad = 26
    strip_h = axis_h + len(lanes) * (lane_h + lane_gap) + 12
    strips = max(1, int(math.ceil((t_max - t_min) / strip_hours)))
    height = int(title_h + strips * strip_h + (strips - 1) * strip_gap + bottom_pad)

    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(QColor("#ffffff"))

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, True)
    try:
        _draw_png_timeline(
            painter,
            config,
            requests,
            lanes,
            t_min,
            t_max,
            strips,
            strip_hours,
            tick_step,
            chart_x0,
            chart_w,
            scale,
            title_h,
            strip_h,
            strip_gap,
            axis_h,
            lane_h,
            lane_gap,
            width,
        )
    finally:
        painter.end()

    return image


def _extract_payload(saved: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    if not isinstance(saved, dict):
        raise ValueError("Ожидается JSON-объект с результатами симуляции")
    config = saved.get("config")
    if not isinstance(config, dict):
        raise ValueError("В файле нет корректного поля 'config'")
    requests = saved.get("requests") or []
    if not isinstance(requests, list):
        requests = []
    return config, [r for r in requests if isinstance(r, dict)]


def _extract_calculation_experiments(saved_results: Sequence[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], Dict[str, Any]]]:
    experiments: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
    for saved in saved_results:
        if not isinstance(saved, dict):
            continue
        config = saved.get("config")
        calculations = saved.get("calculations")
        if not isinstance(config, dict) or not isinstance(calculations, dict):
            continue
        results = calculations.get("results")
        if isinstance(results, dict) and results:
            experiments.append((config, results))
    return experiments


def _collect_calculation_metric_keys(experiments: Sequence[Tuple[Dict[str, Any], Dict[str, Any]]]) -> List[str]:
    metric_keys: List[str] = []
    seen = set()
    for _config, results in experiments:
        for key in results:
            key_text = str(key)
            if key_text not in seen:
                seen.add(key_text)
                metric_keys.append(key_text)
    return metric_keys


def _total_service_capacity(config: Dict[str, Any]) -> Optional[float]:
    operators = config.get("operators")
    if isinstance(operators, list):
        total = 0.0
        for op in operators:
            if not isinstance(op, dict):
                continue
            mu = to_float(op.get("mu")) or 0.0
            count = to_float(op.get("count")) or 1.0
            total += mu * count
        return total

    service_rates = config.get("service_rates")
    if isinstance(service_rates, list):
        values = [to_float(value) for value in service_rates]
        return sum(value for value in values if value is not None)

    return None


def _capacity_sort_value(config: Dict[str, Any]) -> float:
    capacity = _total_service_capacity(config)
    return capacity if capacity is not None else float("inf")


def _build_lanes(config: Dict[str, Any], requests: List[Dict[str, Any]]) -> List[str]:
    queue_size = to_int(config.get("queue_size"), 0)
    server_names = expand_server_names_from_config(config)
    observed_servers = sorted({
        str(r.get("server_name") or "Неизвестно")
        for r in requests
        if to_float(r.get("t_service_start")) is not None
    })
    for name in observed_servers:
        if name not in server_names:
            server_names.append(name)

    lanes = [ARRIVAL_LANE]
    lanes.extend(f"Канал: {name}" for name in server_names)
    lanes.extend(f"Очередь — место {i}" for i in range(1, max(0, queue_size) + 1))
    lanes.append(DONE_LANE)
    lanes.append(REFUSE_LANE)
    return lanes


def _sorted_request_ids(requests: List[Dict[str, Any]]) -> List[int]:
    return sorted(to_int(r.get("id"), 0) for r in requests)


def _time_range(config: Dict[str, Any], requests: List[Dict[str, Any]]) -> Tuple[float, float]:
    times = [0.0]
    duration = to_float(config.get("duration"))
    if duration is not None and duration > 0:
        times.append(duration)
    for req in requests:
        for key in ("t_arrival", "t_queue_enter", "t_service_start", "t_service_end", "t_refuse"):
            value = to_float(req.get(key))
            if value is not None:
                times.append(value)
        for entry in req.get("queue_history") or []:
            if isinstance(entry, dict):
                for key in ("t_enter", "t_leave"):
                    value = to_float(entry.get(key))
                    if value is not None:
                        times.append(value)
    t_min = 0.0
    t_max = max(times) if times else 1.0
    if t_max <= t_min:
        t_max = t_min + 1.0
    return t_min, t_max


def _queue_segments(config: Dict[str, Any], requests: List[Dict[str, Any]]) -> List[Tuple[int, int, float, float]]:
    _t_min, t_max = _time_range(config, requests)
    queue_size = to_int(config.get("queue_size"), 0)
    return assign_queue_slots(requests, queue_size, t_max)


def _queue_slot_enter_times(
    config: Dict[str, Any],
    requests: List[Dict[str, Any]],
) -> Dict[Tuple[str, int], float]:
    result: Dict[Tuple[str, int], float] = {}
    for slot, rid, t_enter, _t_leave in _queue_segments(config, requests):
        result[(f"Очередь — место {slot}", rid)] = t_enter
    return result


def _time_for_lane(lane: str, req: Dict[str, Any], queue_time: Optional[float]) -> Optional[float]:
    if lane == ARRIVAL_LANE:
        return to_float(req.get("t_arrival"))
    if lane == DONE_LANE:
        return to_float(req.get("t_service_end"))
    if lane == REFUSE_LANE:
        return to_float(req.get("t_refuse"))
    if lane.startswith("Канал: "):
        server_name = lane[len("Канал: "):]
        if str(req.get("server_name") or "") == server_name:
            return to_float(req.get("t_service_start"))
        return None
    if lane.startswith("Очередь — место "):
        return queue_time
    return None


def _write_xlsx(rows: Sequence[Sequence[Any]], path: str) -> None:
    sheet_xml = _build_sheet_xml(rows)
    workbook_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Экспорт" sheetId="1" r:id="rId1"/></sheets></workbook>"""
    workbook_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>"""
    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>"""
    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills><borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/><xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0"/></cellXfs></styleSheet>"""

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/styles.xml", styles_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def _build_sheet_xml(rows: Sequence[Sequence[Any]]) -> str:
    row_xml: List[str] = []
    for row_idx, row in enumerate(rows, start=1):
        cells = []
        for col_idx, value in enumerate(row, start=1):
            ref = f"{_excel_col(col_idx)}{row_idx}"
            style = ' s="1"' if row_idx == 1 or col_idx == 1 else ""
            if value is None or value == "":
                cells.append(f'<c r="{ref}"{style}/>')
            elif isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"{style}><v>{float(value):.10g}</v></c>')
            else:
                text = xml_escape(str(value))
                cells.append(f'<c r="{ref}" t="inlineStr"{style}><is><t>{text}</t></is></c>')
        row_xml.append(f'<row r="{row_idx}">{"".join(cells)}</row>')

    col_count = max((len(row) for row in rows), default=1)
    cols = ['<col min="1" max="1" width="28" customWidth="1"/>']
    if col_count > 1:
        cols.append(f'<col min="2" max="{col_count}" width="13" customWidth="1"/>')
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<cols>{"".join(cols)}</cols><sheetData>{"".join(row_xml)}</sheetData>'
        '</worksheet>'
    )


def _excel_col(index: int) -> str:
    letters = ""
    while index:
        index, rem = divmod(index - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _draw_png_timeline(
    painter: QPainter,
    config: Dict[str, Any],
    requests: List[Dict[str, Any]],
    lanes: List[str],
    t_min: float,
    t_max: float,
    strips: int,
    strip_hours: float,
    tick_step: float,
    chart_x0: int,
    chart_w: int,
    scale: float,
    title_h: int,
    strip_h: int,
    strip_gap: int,
    axis_h: int,
    lane_h: int,
    lane_gap: int,
    width: int,
) -> None:
    painter.setFont(QFont("Arial", 14, QFont.Bold))
    painter.setPen(QColor("#1d2433"))
    painter.drawText(QRectF(20, 16, width - 40, 24), Qt.AlignLeft | Qt.AlignVCenter, "Временная диаграмма СМО")

    painter.setFont(QFont("Arial", 9))
    painter.setPen(QColor("#4d5566"))
    painter.drawText(
        QRectF(20, 38, width - 40, 18),
        Qt.AlignLeft | Qt.AlignVCenter,
        f"Ширина: {width}px, интервал строки: {strip_hours:g} ч, шаг сетки: {tick_step:g} ч",
    )

    queue_segments = _queue_segments(config, requests)
    lane_index = {lane: idx for idx, lane in enumerate(lanes)}
    req_by_id = {to_int(r.get("id"), 0): r for r in requests}

    for strip in range(strips):
        strip_t0 = t_min + strip * strip_hours
        strip_t1 = min(t_max, strip_t0 + strip_hours)
        y0 = title_h + strip * (strip_h + strip_gap)
        _draw_strip_grid(
            painter, lanes, strip_t0, strip_t1, tick_step, chart_x0, chart_w, scale,
            y0, axis_h, lane_h, lane_gap
        )
        _draw_strip_events(
            painter, req_by_id, queue_segments, lane_index, strip_t0, strip_t1, chart_x0, scale,
            y0, axis_h, lane_h, lane_gap
        )


def _draw_strip_grid(
    painter: QPainter,
    lanes: List[str],
    strip_t0: float,
    strip_t1: float,
    tick_step: float,
    chart_x0: int,
    chart_w: int,
    scale: float,
    y0: int,
    axis_h: int,
    lane_h: int,
    lane_gap: int,
) -> None:
    painter.setFont(QFont("Arial", 8))
    painter.setPen(QPen(QColor("#d7dce5"), 1))
    painter.drawRect(QRectF(chart_x0, y0 + axis_h - 10, chart_w, len(lanes) * (lane_h + lane_gap)))

    first_tick = math.ceil(strip_t0 / tick_step) * tick_step
    tick = first_tick
    while tick <= strip_t1 + 1e-9:
        x = chart_x0 + (tick - strip_t0) * scale
        major = abs(tick - round(tick)) < 1e-7
        painter.setPen(QPen(QColor("#c5ccd8" if major else "#ebedf2"), 1))
        painter.drawLine(QPointF(x, y0 + axis_h - 10), QPointF(x, y0 + axis_h - 10 + len(lanes) * (lane_h + lane_gap)))
        painter.setPen(QColor("#5d6574"))
        painter.drawText(QRectF(x - 28, y0 + 4, 56, 18), Qt.AlignCenter, f"{tick:g}")
        tick += tick_step

    painter.setFont(QFont("Arial", 9))
    for idx, lane in enumerate(lanes):
        ly = y0 + axis_h + idx * (lane_h + lane_gap)
        cy = ly + lane_h / 2
        painter.setPen(QColor("#263044"))
        painter.drawText(QRectF(10, ly - 2, chart_x0 - 18, lane_h + 4), Qt.AlignRight | Qt.AlignVCenter, lane)
        painter.setPen(QPen(QColor("#5678ff"), 1))
        painter.setOpacity(0.35)
        painter.drawLine(QPointF(chart_x0, cy), QPointF(chart_x0 + chart_w, cy))
        painter.setOpacity(1.0)
        painter.setPen(QPen(QColor("#f0f2f6"), 1))
        painter.drawLine(QPointF(0, ly + lane_h + lane_gap / 2), QPointF(chart_x0 + chart_w, ly + lane_h + lane_gap / 2))


def _draw_strip_events(
    painter: QPainter,
    req_by_id: Dict[int, Dict[str, Any]],
    queue_segments: List[Tuple[int, int, float, float]],
    lane_index: Dict[str, int],
    strip_t0: float,
    strip_t1: float,
    chart_x0: int,
    scale: float,
    y0: int,
    axis_h: int,
    lane_h: int,
    lane_gap: int,
) -> None:
    def x(time_value: float) -> float:
        return chart_x0 + (time_value - strip_t0) * scale

    def lane_center(lane: str) -> float:
        idx = lane_index[lane]
        return y0 + axis_h + idx * (lane_h + lane_gap) + lane_h / 2

    def clip_x(time_value: float) -> float:
        return x(min(max(time_value, strip_t0), strip_t1))

    chart_clip = QRectF(chart_x0, y0 + axis_h - 10, scale * (strip_t1 - strip_t0), len(lane_index) * (lane_h + lane_gap) + 10)
    painter.save()
    painter.setClipRect(chart_clip)

    painter.setPen(QPen(QColor(86, 120, 255, 115), 1))
    for rid, req in req_by_id.items():
        points = _request_points(req, queue_segments, lane_index)
        if len(points) < 2:
            continue
        path = QPainterPath()
        started = False
        for time_value, lane in points:
            px = x(time_value)
            py = lane_center(lane)
            if not started:
                path.moveTo(px, py)
                started = True
            else:
                current = path.currentPosition()
                path.lineTo(px, current.y())
                path.lineTo(px, py)
        painter.drawPath(path)

    painter.setFont(QFont("Arial", 8))
    for rid, req in req_by_id.items():
        label = str(rid + 1)
        _draw_marker_if_visible(painter, x, lane_center, strip_t0, strip_t1, to_float(req.get("t_arrival")), ARRIVAL_LANE, label, "#8aa8ff", "#2546b8")
        _draw_marker_if_visible(painter, x, lane_center, strip_t0, strip_t1, to_float(req.get("t_service_end")), DONE_LANE, label, "#2ecc71", "#1c7a44")
        _draw_marker_if_visible(painter, x, lane_center, strip_t0, strip_t1, to_float(req.get("t_refuse")), REFUSE_LANE, label, "#ff6b6b", "#a11919")

        service_start = to_float(req.get("t_service_start"))
        service_end = to_float(req.get("t_service_end"))
        server_name = str(req.get("server_name") or "")
        service_lane = f"Канал: {server_name}"
        if service_start is not None and service_lane in lane_index:
            _draw_segment_if_visible(
                painter, clip_x, lane_center, strip_t0, strip_t1, service_start,
                service_end if service_end is not None else strip_t1, service_lane, label,
                "#b6e3a8", "#3a7a2a", "#0f3b0f"
            )

    for slot, rid, t_enter, t_leave in queue_segments:
        lane = f"Очередь — место {slot}"
        if lane in lane_index:
            _draw_segment_if_visible(
                painter, clip_x, lane_center, strip_t0, strip_t1, t_enter, t_leave, lane, str(rid + 1),
                "#ffd08a", "#b06a00", "#5a3300"
            )

    painter.restore()


def _request_points(
    req: Dict[str, Any],
    queue_segments: List[Tuple[int, int, float, float]],
    lane_index: Dict[str, int],
) -> List[Tuple[float, str]]:
    rid = to_int(req.get("id"), 0)
    t_arr = to_float(req.get("t_arrival"))
    if t_arr is None:
        return []
    points: List[Tuple[float, str]] = [(t_arr, ARRIVAL_LANE)]
    t_ref = to_float(req.get("t_refuse"))
    if t_ref is not None:
        points.append((t_ref, REFUSE_LANE))
        return points

    queue_for_req = [seg for seg in queue_segments if seg[1] == rid]
    for slot, _rid, t_enter, _t_leave in sorted(queue_for_req, key=lambda item: item[2]):
        lane = f"Очередь — место {slot}"
        if lane in lane_index:
            points.append((t_enter, lane))

    t_start = to_float(req.get("t_service_start"))
    server_lane = f"Канал: {req.get('server_name') or ''}"
    if t_start is not None and server_lane in lane_index:
        points.append((t_start, server_lane))

    t_end = to_float(req.get("t_service_end"))
    if t_end is not None:
        if server_lane in lane_index:
            points.append((t_end, server_lane))
        points.append((t_end, DONE_LANE))
    return points


def _draw_marker_if_visible(
    painter: QPainter,
    x_func: Any,
    lane_center_func: Any,
    strip_t0: float,
    strip_t1: float,
    time_value: Optional[float],
    lane: str,
    label: str,
    fill: str,
    stroke: str,
) -> None:
    if time_value is None or time_value < strip_t0 or time_value > strip_t1:
        return
    cx = x_func(time_value)
    cy = lane_center_func(lane)
    painter.setBrush(QColor(fill))
    painter.setPen(QPen(QColor(stroke), 1))
    painter.drawEllipse(QPointF(cx, cy), 5, 5)
    painter.setPen(QColor("#202636"))
    painter.drawText(QRectF(cx - 14, cy - 22, 28, 14), Qt.AlignCenter, label)


def _draw_segment_if_visible(
    painter: QPainter,
    clip_x_func: Any,
    lane_center_func: Any,
    strip_t0: float,
    strip_t1: float,
    t0: float,
    t1: float,
    lane: str,
    label: str,
    fill: str,
    stroke: str,
    text_color: str,
) -> None:
    if t1 < strip_t0 or t0 > strip_t1:
        return
    x0 = clip_x_func(t0)
    x1 = clip_x_func(t1)
    cy = lane_center_func(lane)
    rect = QRectF(min(x0, x1), cy - 7, max(2.0, abs(x1 - x0)), 14)
    painter.setBrush(QColor(fill))
    painter.setPen(QPen(QColor(stroke), 1))
    painter.drawRoundedRect(rect, 4, 4)
    if rect.width() >= 16:
        painter.setPen(QColor(text_color))
        painter.drawText(rect, Qt.AlignCenter, label)
