from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .formatting import CALC_METRIC_NAMES, dash, esc, fmt_num, fmt_policy, format_warmup
from .templates import render_full_html


CHART_W = 920
CHART_H = 330
PAD_L = 74
PAD_R = 28
PAD_T = 24
PAD_B = 58


def build_parameter_charts_html(
    saved_results: Sequence[Dict[str, Any]],
    source_names: Optional[Sequence[str]] = None,
) -> str:
    experiments = _extract_experiments(saved_results, source_names)
    if not experiments:
        raise ValueError("Нет корректных JSON-файлов с блоком calculations.results")

    metric_keys = _collect_metric_keys(experiments)
    if not metric_keys:
        raise ValueError("В выбранных JSON-файлах нет рассчитанных параметров")

    experiments = sorted(experiments, key=lambda item: (item["x_value"], item["name"]))

    experiments_html = _render_experiments(experiments)
    charts_html = "\n".join(_render_chart(metric_key, experiments) for metric_key in metric_keys)

    body_html = f"""
  <h1>Графики рассчитанных параметров СМО</h1>
  <div class="muted parameter-note">
    Ось X: суммарная пропускная способность каналов обслуживания Σ(μ · количество).
    Для вероятностных показателей шкала Y фиксируется от 0 до 1 с шагом 0.1; остальные показатели масштабируются по максимальному значению.
  </div>

  <div class="section">
    <h2>Параметры экспериментов</h2>
    <div class="experiment-grid">
      {experiments_html}
    </div>
  </div>

  <div class="section charts-section">
    <h2>Графики</h2>
    {charts_html}
  </div>
""".strip()

    return render_full_html(body_html=body_html, meta={})


def _extract_experiments(
    saved_results: Sequence[Dict[str, Any]],
    source_names: Optional[Sequence[str]],
) -> List[Dict[str, Any]]:
    experiments: List[Dict[str, Any]] = []
    for idx, saved in enumerate(saved_results):
        if not isinstance(saved, dict):
            continue

        config = saved.get("config")
        calculations = saved.get("calculations")
        if not isinstance(config, dict) or not isinstance(calculations, dict):
            continue

        results = calculations.get("results")
        if not isinstance(results, dict):
            continue

        name = None
        if source_names and idx < len(source_names):
            name = source_names[idx]
        name = str(name or f"Эксперимент {idx + 1}")

        experiments.append({
            "name": name,
            "config": config,
            "summary": saved.get("summary") if isinstance(saved.get("summary"), dict) else {},
            "calculations": calculations,
            "results": results,
            "selected_metrics": calculations.get("selected_metrics")
            if isinstance(calculations.get("selected_metrics"), list)
            else list(results.keys()),
            "x_value": _total_capacity(config),
        })

    return experiments


def _collect_metric_keys(experiments: Sequence[Dict[str, Any]]) -> List[str]:
    keys: List[str] = []
    seen = set()

    for exp in experiments:
        for key in exp["selected_metrics"]:
            key = str(key)
            if key not in seen and _has_numeric_value(key, experiments):
                keys.append(key)
                seen.add(key)

    for exp in experiments:
        for key in exp["results"].keys():
            key = str(key)
            if key not in seen and _has_numeric_value(key, experiments):
                keys.append(key)
                seen.add(key)

    return keys


def _has_numeric_value(key: str, experiments: Sequence[Dict[str, Any]]) -> bool:
    return any(_to_float(exp["results"].get(key)) is not None for exp in experiments)


def _total_capacity(config: Dict[str, Any]) -> float:
    operators = config.get("operators")
    if not isinstance(operators, list):
        return 0.0

    total = 0.0
    for op in operators:
        if not isinstance(op, dict):
            continue
        mu = _to_float(op.get("mu")) or 0.0
        count = _to_float(op.get("count")) or 1.0
        total += mu * count
    return total


def _render_experiments(experiments: Sequence[Dict[str, Any]]) -> str:
    cards = []
    for idx, exp in enumerate(experiments, 1):
        config = exp["config"]
        summary = exp["summary"]
        calculations = exp["calculations"]

        rows = [
            ("Файл", exp["name"]),
            ("Поток заявок λ", config.get("call_flow")),
            ("Размер очереди", config.get("queue_size")),
            ("Длительность", config.get("duration")),
            ("Σ пропускная способность", fmt_num(exp["x_value"], 6)),
            ("Политика канала", fmt_policy(config.get("free_server_policy"))),
            ("Warm-up", format_warmup(calculations.get("warmup"))),
            ("Поступило", summary.get("arrivals")),
            ("Обслужено", summary.get("served")),
            ("Отказов", summary.get("refused")),
        ]

        operators_html = _render_operators(config)
        cards.append(
            "<div class='card experiment-card'>"
            f"<h3>Эксперимент {idx}</h3>"
            f"{_render_rows(rows)}"
            "<div class='operators-title'>Каналы обслуживания</div>"
            f"{operators_html}"
            "</div>"
        )
    return "\n".join(cards)


def _render_operators(config: Dict[str, Any]) -> str:
    operators = config.get("operators")
    if not isinstance(operators, list) or not operators:
        return "<div class='muted'>Нет данных</div>"

    rows = []
    for op in operators:
        if not isinstance(op, dict):
            continue
        capacity = (_to_float(op.get("mu")) or 0.0) * (_to_float(op.get("count")) or 1.0)
        rows.append(
            "<tr>"
            f"<td>{dash(op.get('type'))}</td>"
            f"<td>{dash(op.get('mu'))}</td>"
            f"<td>{dash(op.get('count', 1))}</td>"
            f"<td>{fmt_num(capacity, 6)}</td>"
            "</tr>"
        )

    if not rows:
        return "<div class='muted'>Нет данных</div>"

    return (
        "<table class='compact-table mini-table'>"
        "<thead><tr><th>Тип</th><th>μ</th><th>Кол-во</th><th>Σ</th></tr></thead>"
        "<tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def _render_rows(rows: Sequence[Tuple[str, Any]]) -> str:
    body = "".join(
        f"<tr><td class='k'>{esc(key)}</td><td class='v'>{dash(value)}</td></tr>"
        for key, value in rows
    )
    return f"<table class='compact-table kv-table experiment-table'><tbody>{body}</tbody></table>"


def _render_chart(metric_key: str, experiments: Sequence[Dict[str, Any]]) -> str:
    points: List[Tuple[float, float, str]] = []
    for exp in experiments:
        y = _to_float(exp["results"].get(metric_key))
        if y is None:
            continue
        points.append((float(exp["x_value"]), y, exp["name"]))

    if not points:
        return ""

    y_min, y_max, y_step = _y_scale(metric_key, [p[1] for p in points])
    x_min, x_max = _x_bounds([p[0] for p in points])

    plot_w = CHART_W - PAD_L - PAD_R
    plot_h = CHART_H - PAD_T - PAD_B

    def x_to_px(x: float) -> float:
        if math.isclose(x_min, x_max):
            return PAD_L + plot_w / 2
        return PAD_L + ((x - x_min) / (x_max - x_min)) * plot_w

    def y_to_px(y: float) -> float:
        y = max(y_min, min(y_max, y))
        return PAD_T + (1.0 - ((y - y_min) / (y_max - y_min))) * plot_h

    grid_lines = []
    labels = []
    tick = y_min
    guard = 0
    while tick <= y_max + 1e-9 and guard < 100:
        y = y_to_px(tick)
        grid_lines.append(
            f"<line x1='{PAD_L}' y1='{_f(y)}' x2='{CHART_W - PAD_R}' y2='{_f(y)}' class='chart-grid' />"
        )
        labels.append(
            f"<text x='{PAD_L - 10}' y='{_f(y + 4)}' text-anchor='end' class='chart-axis-label'>{_format_tick(tick)}</text>"
        )
        tick += y_step
        guard += 1

    x_ticks = _x_ticks(points)
    x_tick_html = []
    for x_value in x_ticks:
        x = x_to_px(x_value)
        x_tick_html.append(
            f"<line x1='{_f(x)}' y1='{PAD_T}' x2='{_f(x)}' y2='{CHART_H - PAD_B}' class='chart-grid chart-grid-x' />"
            f"<text x='{_f(x)}' y='{CHART_H - 24}' text-anchor='middle' class='chart-axis-label'>{esc(_format_tick(x_value))}</text>"
        )

    line_points = " ".join(f"{_f(x_to_px(x))},{_f(y_to_px(y))}" for x, y, _name in points)
    point_html = []
    for x, y, name in points:
        px = x_to_px(x)
        py = y_to_px(y)
        label_y = py - 10 if py > PAD_T + 18 else py + 20
        point_html.append(
            f"<circle cx='{_f(px)}' cy='{_f(py)}' r='4.5' class='chart-point'>"
            f"<title>{esc(name)}: X={_format_tick(x)}, Y={fmt_num(y, 6)}</title>"
            "</circle>"
            f"<text x='{_f(px)}' y='{_f(label_y)}' text-anchor='middle' class='chart-point-label'>{fmt_num(y, 4)}</text>"
        )

    title = CALC_METRIC_NAMES.get(metric_key, metric_key)
    y_caption = "Значение показателя"
    if _is_probability_metric(metric_key, [p[1] for p in points]):
        y_caption = "Вероятность"

    return f"""
    <div class="card chart-card">
      <h3>{esc(title)}</h3>
      <svg class="parameter-chart" viewBox="0 0 {CHART_W} {CHART_H}" role="img" aria-label="{esc(title)}">
        <rect x="{PAD_L}" y="{PAD_T}" width="{plot_w}" height="{plot_h}" class="chart-plot-bg" />
        {''.join(grid_lines)}
        {''.join(x_tick_html)}
        <line x1="{PAD_L}" y1="{PAD_T}" x2="{PAD_L}" y2="{CHART_H - PAD_B}" class="chart-axis" />
        <line x1="{PAD_L}" y1="{CHART_H - PAD_B}" x2="{CHART_W - PAD_R}" y2="{CHART_H - PAD_B}" class="chart-axis" />
        {''.join(labels)}
        <polyline points="{line_points}" class="chart-line" />
        {''.join(point_html)}
        <text x="{(PAD_L + CHART_W - PAD_R) / 2}" y="{CHART_H - 6}" text-anchor="middle" class="chart-caption">Σ пропускная способность каналов</text>
        <text x="18" y="{(PAD_T + CHART_H - PAD_B) / 2}" text-anchor="middle" class="chart-caption" transform="rotate(-90 18 {(PAD_T + CHART_H - PAD_B) / 2})">{esc(y_caption)}</text>
      </svg>
    </div>
""".strip()


def _x_bounds(values: Sequence[float]) -> Tuple[float, float]:
    x_min = min(values)
    x_max = max(values)
    if math.isclose(x_min, x_max):
        pad = max(1.0, abs(x_min) * 0.1)
        return x_min - pad, x_max + pad
    pad = (x_max - x_min) * 0.08
    return x_min - pad, x_max + pad


def _x_ticks(points: Sequence[Tuple[float, float, str]]) -> List[float]:
    ticks: List[float] = []
    seen = set()
    for x, _y, _name in points:
        rounded = round(x, 10)
        if rounded not in seen:
            ticks.append(x)
            seen.add(rounded)
    return ticks


def _y_scale(metric_key: str, values: Sequence[float]) -> Tuple[float, float, float]:
    if _is_probability_metric(metric_key, values):
        return 0.0, 1.0, 0.1

    max_value = max([0.0, *values])
    if max_value <= 1.0:
        return 0.0, 1.0, 0.1

    step = _nice_step(max_value / 10.0)
    y_max = max(step, math.ceil(max_value / step) * step)
    return 0.0, y_max, step


def _is_probability_metric(metric_key: str, values: Sequence[float]) -> bool:
    if metric_key.startswith("p_"):
        return True
    return bool(values) and all(0.0 <= value <= 1.0 for value in values)


def _nice_step(raw_step: float) -> float:
    if raw_step <= 0:
        return 0.1
    power = 10 ** math.floor(math.log10(raw_step))
    normalized = raw_step / power
    if normalized <= 1:
        nice = 1
    elif normalized <= 2:
        nice = 2
    elif normalized <= 5:
        nice = 5
    else:
        nice = 10
    return nice * power


def _to_float(value: Any) -> Optional[float]:
    try:
        if value is None or isinstance(value, bool):
            return None
        result = float(value)
        if not math.isfinite(result):
            return None
        return result
    except Exception:
        return None


def _format_tick(value: float) -> str:
    if abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _f(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")
