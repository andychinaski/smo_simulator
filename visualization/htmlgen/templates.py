from __future__ import annotations

import json
from typing import Any, Dict, List


ZOOM_STOPS: List[float] = [
    0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5,
    3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0,
]
ZOOM_MIN: float = 0.25
ZOOM_MAX: float = 30.0
ZOOM_DEFAULT: float = 1.0
ZOOM_DEFAULT_IDX: int = 5  # индекс 1.0 в списке


# ВАЖНО:
# CSS_TEXT должен содержать ТОЛЬКО CSS (без <style>...</style>),
# потому что render_full_html сам оборачивает его в <style>.
CSS_TEXT = """
:root {
  --zoom: 1;
  --invZoom: 1;
}

body {
  font-family: Arial, sans-serif;
  margin: 18px 24px;
  color: #222;
}

h1 { margin: 0 0 10px 0; }
h2 { margin: 0 0 8px 0; font-size: 15px; }
.muted { color:#666; font-size:12px; }

/* top info grid */
.top-grid {
  display: grid;
  gap: 14px;
  align-items: start;

  /* Было: 1fr 420px -> слева всё растягивалось на всю ширину.
     Теперь: левую колонку держим узкой/фиксированной, правую отдаём расчётам. */
  grid-template-columns: minmax(420px, 560px) 1fr;
}

@media (max-width: 1100px) {
  .top-grid { grid-template-columns: 1fr; }
}

.col {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.card {
  border: 1px solid #ddd;
  background: #fbfbfb;
  padding: 10px;
}

/* compact tables */
.compact-table {
  border-collapse: collapse;
  width: 100%;
  font-size: 12px;
  background: #fff;

  /* чтобы таблицы не раздували колонки и лучше переносили длинные значения */
  table-layout: fixed;
}

.compact-table th,
.compact-table td {
  border: 1px solid #ddd;
  padding: 4px 6px;
  text-align: left;
  vertical-align: top;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.compact-table th {
  background: #f3f3f3;
  font-weight: 600;
}

.kv-table td.k { width: 52%; color:#555; }
.kv-table td.v { width: 48%; }

.section {
  margin-top: 14px;
}

/* timeline controls + layout */
.timeline-controls {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 10px 0;
  user-select: none;
  flex-wrap: wrap;
}

.timeline-controls button {
  padding: 6px 10px;
  cursor: pointer;
}

.timeline-controls .zoom-value {
  font-size: 12px;
  color: #444;
  padding: 0 6px;
}

.timeline-controls input[type="range"] {
  width: 220px;
}

.timeline-controls input[type="number"] {
  width: 90px;
  padding: 6px 8px;
}

.timeline-layout {
  display: flex;
  border: 1px solid #ddd;
  background: #fff;
  max-width: 100%;
}

.lane-labels {
  flex: 0 0 auto;
  border-right: 1px solid #ddd;
  background: #fff;
}

.lane-label {
  display: flex;
  align-items: center;
  padding: 0 10px;
  font-size: 12px;
  border-bottom: 1px solid #f6f6f6;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.timeline-scroll {
  flex: 1 1 auto;
  overflow-x: auto;
  overflow-y: hidden;
}

#timelineSvg .no-xscale {
  transform: scaleX(var(--invZoom));
  transform-origin: center;
  transform-box: fill-box;
}

.timeline-svg-wrap {
  padding: 10px 50px;
  display: inline-block;
}

.note {
  color: #666;
  font-size: 12px;
  margin-top: 6px;
}

.parameter-note {
  margin: 0 0 14px 0;
  max-width: 1100px;
}

.experiment-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: 12px;
}

.experiment-card h3,
.chart-card h3 {
  margin: 0 0 8px 0;
  font-size: 14px;
}

.experiment-table {
  margin-bottom: 8px;
}

.operators-title {
  color: #555;
  font-size: 12px;
  font-weight: 600;
  margin: 8px 0 4px;
}

.mini-table th,
.mini-table td {
  font-size: 11px;
}

.charts-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chart-card {
  overflow-x: auto;
}

.parameter-chart {
  display: block;
  width: min(100%, 920px);
  min-width: 720px;
  height: auto;
  background: #fff;
}

.chart-plot-bg {
  fill: #fff;
}

.chart-grid {
  stroke: #e6e6e6;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.chart-grid-x {
  stroke: #f0f0f0;
}

.chart-axis {
  stroke: #444;
  stroke-width: 1.2;
  vector-effect: non-scaling-stroke;
}

.chart-line {
  fill: none;
  stroke: #2563eb;
  stroke-width: 2.2;
  vector-effect: non-scaling-stroke;
}

.chart-point {
  fill: #fff;
  stroke: #1d4ed8;
  stroke-width: 2;
  vector-effect: non-scaling-stroke;
}

.chart-axis-label,
.chart-caption,
.chart-point-label {
  fill: #555;
  font-size: 11px;
}

.chart-caption {
  font-weight: 600;
}

.chart-point-label {
  fill: #222;
  font-size: 10px;
}
""".strip()


# JS_TEXT — тоже без <script>...</script>, он будет вставлен внутрь <script> в render_full_html.
# Косяк, который был: если meta отсутствует/��итый — код падал.
# Здесь добавлены fallback значения и ранние проверки DOM.
JS_TEXT = """
(function() {
  const meta = window.__SMO_META__ || {};

  const FALLBACK_ZOOM_STOPS = [
    0.25, 0.33, 0.5, 0.67, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5,
    3.0, 4.0, 5.0, 6.0, 8.0, 10.0, 12.0, 15.0, 20.0, 25.0, 30.0
  ];

  const baseWidth = Number(meta.baseWidth || 0);
  const tMin = Number.isFinite(meta.tMin) ? Number(meta.tMin) : 0.0;
  const tMax = Number.isFinite(meta.tMax) ? Number(meta.tMax) : 1.0;
  const chartX0 = Number.isFinite(meta.chartX0) ? Number(meta.chartX0) : 0.0;
  const chartX1 = Number.isFinite(meta.chartX1) ? Number(meta.chartX1) : (baseWidth || 1200);
  const scaleCoordPerHour = Number.isFinite(meta.scaleCoordPerHour) ? Number(meta.scaleCoordPerHour) : 1.0;
  const svgH = Number.isFinite(meta.svgH) ? Number(meta.svgH) : 400.0;

  const ZOOM_MIN = Number.isFinite(meta.zoomMin) ? Number(meta.zoomMin) : 0.25;
  const ZOOM_MAX = Number.isFinite(meta.zoomMax) ? Number(meta.zoomMax) : 30.0;
  const ZOOM_STOPS = Array.isArray(meta.zoomStops) && meta.zoomStops.length ? meta.zoomStops : FALLBACK_ZOOM_STOPS;

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

  if (!svg || !scroll || !zoomValue || !zoomSlider || !zoomInput || !btnIn || !btnOut || !btnReset || !gMinor || !gMajor || !gLabels) {
    // если HTML частично изменится или чего-то не будет — просто не падаем
    return;
  }

  const BW = baseWidth > 0 ? baseWidth : (parseFloat(svg.getAttribute('width')) || 1200);
  const WRAP_PAD_X = 50;

  function clamp(v, lo, hi) { return Math.max(lo, Math.min(hi, v)); }
  function round2(v) { return Math.round(v * 100) / 100; }

  function snapZoom(v) {
    v = clamp(v, ZOOM_MIN, ZOOM_MAX);
    return round2(v);
  }

  function nearestStopIndex(z) {
    let bestI = 0;
    let bestD = Infinity;
    for (let i = 0; i < ZOOM_STOPS.length; i++) {
      const d = Math.abs(ZOOM_STOPS[i] - z);
      if (d < bestD) { bestD = d; bestI = i; }
    }
    return bestI;
  }

  function nextStop(z) {
    for (let i = 0; i < ZOOM_STOPS.length; i++) {
      if (ZOOM_STOPS[i] > z + 1e-9) return ZOOM_STOPS[i];
    }
    return ZOOM_STOPS[ZOOM_STOPS.length - 1];
  }

  function prevStop(z) {
    for (let i = ZOOM_STOPS.length - 1; i >= 0; i--) {
      if (ZOOM_STOPS[i] < z - 1e-9) return ZOOM_STOPS[i];
    }
    return ZOOM_STOPS[0];
  }

  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }

  const NICE_MINUTES = [
    1,2,5,10,15,30,
    60,120,180,240,360,480,720,1440,
    2880,4320,5760,7200
  ];

  function chooseStepHours(targetPx, pxPerHour) {
    const targetHours = targetPx / Math.max(1e-9, pxPerHour);
    const targetMinutes = targetHours * 60.0;
    for (const m of NICE_MINUTES) {
      if (m >= targetMinutes - 1e-9) return m / 60.0;
    }
    return NICE_MINUTES[NICE_MINUTES.length - 1] / 60.0;
  }

  function fmtTimeHM(hours) {
    const totalMin = Math.round(hours * 60);
    const h = Math.floor(totalMin / 60);
    const m = Math.abs(totalMin % 60);
    return String(h) + ":" + String(m).padStart(2, "0");
  }

  function timeToXCoord(t) {
    return chartX0 + (t - tMin) * scaleCoordPerHour;
  }

  function xCoordToTime(x) {
    return tMin + (x - chartX0) / scaleCoordPerHour;
  }

  function createVLine(x, stroke, width, opacity) {
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
  }

  function createText(x, y, text) {
    const tx = document.createElementNS("http://www.w3.org/2000/svg", "text");
    tx.setAttribute("x", x);
    tx.setAttribute("y", y);
    tx.setAttribute("text-anchor", "middle");
    tx.setAttribute("fill", "#555");
    tx.setAttribute("font-size", "11");
    tx.setAttribute("class", "no-xscale");
    tx.textContent = text;
    return tx;
  }

  function niceCeil(v, step) {
    return Math.ceil((v - 1e-9) / step) * step;
  }

  function getDisplayedSvgWidth() {
    return parseFloat(svg.getAttribute('width')) || BW;
  }

  function getVisibleViewBoxRange() {
    const dispW = getDisplayedSvgWidth();

    let px0 = scroll.scrollLeft - WRAP_PAD_X;
    let px1 = scroll.scrollLeft + scroll.clientWidth - WRAP_PAD_X;

    px0 = Math.max(0, px0);
    px1 = Math.min(dispW, px1);

    const vx0 = (px0 / dispW) * BW;
    const vx1 = (px1 / dispW) * BW;

    const cx0 = Math.max(chartX0, vx0);
    const cx1 = Math.min(chartX1, vx1);

    return [cx0, cx1];
  }

  function updateGridVisible() {
    clear(gMinor);
    clear(gMajor);
    clear(gLabels);

    const dispW = getDisplayedSvgWidth();
    const pxPerHour = scaleCoordPerHour * (dispW / BW);

    const [vx0, vx1] = getVisibleViewBoxRange();
    if (vx1 <= vx0 + 1e-9) return;

    let t0 = xCoordToTime(vx0);
    let t1 = xCoordToTime(vx1);

    const majorTargetPx = 160;
    const minorTargetPx = 40;

    let majorStep = chooseStepHours(majorTargetPx, pxPerHour);
    let minorStep = chooseStepHours(minorTargetPx, pxPerHour);

    if (minorStep >= majorStep) {
      majorStep = chooseStepHours(majorTargetPx * 2, pxPerHour);
    }

    const pad = majorStep * 2;
    t0 = Math.max(tMin, t0 - pad);
    t1 = Math.min(tMax, t1 + pad);

    const eps = 1e-8;

    let tm = niceCeil(t0, minorStep);
    for (let guard = 0; guard < 200000; guard++) {
      if (tm > t1 + eps) break;
      const xx = timeToXCoord(tm);
      if (xx >= chartX0 - 1 && xx <= chartX1 + 1) {
        const k = tm / majorStep;
        const isMajor = Math.abs(k - Math.round(k)) < 1e-6;
        if (!isMajor) {
          gMinor.appendChild(createVLine(xx, "#f2f2f2", 1, 1.0));
        }
      }
      tm += minorStep;
    }

    let tM = niceCeil(t0, majorStep);
    for (let guard = 0; guard < 200000; guard++) {
      if (tM > t1 + eps) break;
      const xx = timeToXCoord(tM);
      if (xx >= chartX0 - 1 && xx <= chartX1 + 1) {
        gMajor.appendChild(createVLine(xx, "#dcdcdc", 1, 1.0));
        gLabels.appendChild(createText(xx, (svgH - 8).toString(), fmtTimeHM(tM)));
      }
      tM += majorStep;
    }
  }

  let rafPending = false;
  function scheduleGridUpdate() {
    if (rafPending) return;
    rafPending = true;
    requestAnimationFrame(() => {
      rafPending = false;
      updateGridVisible();
    });
  }

  function setUiFromZoom() {
    zoomValue.textContent = zoom.toFixed(2) + 'x';
    zoomInput.value = zoom.toFixed(2);
    zoomSlider.value = String(nearestStopIndex(zoom));
  }

  function applyZoom(newZoom, keepCenter=true) {
    newZoom = snapZoom(newZoom);

    const oldZoom = zoom;
    const oldWidth = BW * oldZoom;
    const newWidth = BW * newZoom;

    let centerFrac = 0.0;
    if (keepCenter) {
      const centerPx = (scroll.scrollLeft - WRAP_PAD_X) + scroll.clientWidth / 2;
      centerFrac = oldWidth > 0 ? (centerPx / oldWidth) : 0.0;
    }

    zoom = newZoom;

    document.documentElement.style.setProperty('--zoom', zoom.toString());
    document.documentElement.style.setProperty('--invZoom', (1/zoom).toString());

    svg.setAttribute('width', Math.round(newWidth).toString());

    if (keepCenter) {
      const newCenterPx = centerFrac * newWidth;
      scroll.scrollLeft = Math.max(0, (newCenterPx - scroll.clientWidth / 2) + WRAP_PAD_X);
    }

    setUiFromZoom();
    scheduleGridUpdate();
  }

  btnIn.addEventListener('click', () => applyZoom(nextStop(zoom), true));
  btnOut.addEventListener('click', () => applyZoom(prevStop(zoom), true));
  btnReset.addEventListener('click', () => applyZoom(1.0, false));

  zoomSlider.addEventListener('input', () => {
    const idx = parseInt(zoomSlider.value, 10) || 0;
    applyZoom(ZOOM_STOPS[Math.max(0, Math.min(ZOOM_STOPS.length-1, idx))], true);
  });

  function applyFromInput() {
    const v = parseFloat(zoomInput.value);
    if (!isFinite(v)) {
      setUiFromZoom();
      return;
    }
    applyZoom(v, true);
  }

  zoomInput.addEventListener('change', applyFromInput);
  zoomInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      zoomInput.blur();
      applyFromInput();
    }
  });

  scroll.addEventListener('scroll', scheduleGridUpdate, { passive: true });
  window.addEventListener('resize', scheduleGridUpdate);

  applyZoom(1.0, false);
})();
""".strip()


def render_full_html(*, body_html: str, meta: Dict[str, Any]) -> str:
    # Чуть компактнее json, но без потери читаемости (при желании убери separators)
    meta_js = "window.__SMO_META__ = " + json.dumps(meta, ensure_ascii=False, separators=(",", ":")) + ";"

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <title>Визуализация СМО</title>
  <style>
{CSS_TEXT}
  </style>
</head>
<body>
{body_html}

  <script>
{meta_js}
  </script>
  <script>
{JS_TEXT}
  </script>
</body>
</html>
"""
