from __future__ import annotations

from typing import Any, Dict, List

from .blocks import (
    build_calculations_html,
    build_operators_table,
    build_params_table,
    build_summary_table,
)
from .formatting import to_int
from .timeline import render_timeline
from .templates import (
    ZOOM_DEFAULT_IDX,
    ZOOM_MAX,
    ZOOM_MIN,
    ZOOM_STOPS,
    render_full_html,
)


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

    params_table = build_params_table(config)
    operators_table = build_operators_table(config)
    summary_table = build_summary_table(summary)
    calculations_html = build_calculations_html(calculations)

    tl = render_timeline(config, reqs)

    body_html = f"""
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

      <input id="zoomSlider" type="range" min="0" max="{len(ZOOM_STOPS)-1}" step="1" value="{ZOOM_DEFAULT_IDX}" />
      <input id="zoomInput" type="number" min="{ZOOM_MIN}" max="{ZOOM_MAX}" step="0.01" value="1.00" />

      <button id="zoomReset" type="button">Сброс</button>
      <span class="zoom-value">Масштаб: <span id="zoomValue">1.00x</span></span>
    </div>

    <div class="timeline-layout">
      {tl.labels_html}
      <div class="timeline-scroll" id="timelineScroll">
        <div class="timeline-svg-wrap" id="timelineWrap">
          {tl.svg_html}
        </div>
      </div>
    </div>

    <div class="note">
      Примечание: сетка рисуется только в видимой области. Масштабирование — по ширине.
      Если очередь больше {tl.max_queue_slots_draw}, отображаются только первые {tl.max_queue_slots_draw} мест.
    </div>
  </div>
""".strip()

    meta: Dict[str, Any] = {
        "baseWidth": tl.base_w,
        "tMin": tl.t_min,
        "tMax": tl.t_max,
        "chartX0": tl.chart_x0,
        "chartX1": tl.chart_x1,
        "scaleCoordPerHour": tl.scale,
        "svgH": tl.svg_h,
        "zoomStops": ZOOM_STOPS,
        "zoomMin": ZOOM_MIN,
        "zoomMax": ZOOM_MAX,
    }

    return render_full_html(body_html=body_html, meta=meta)