from __future__ import annotations

from typing import Any, Dict, List, Optional

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


def build_calculations_html(calculations: Optional[Dict[str, Any]]) -> str:
    if not calculations:
        return "<div class='muted'>Нет данных calculations (это нормально, если файл сохранён сразу после симуляции).</div>"

    warm = format_warmup(calculations.get("warmup"))
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
        rows.append((name, fmt_num(v, 6) if isinstance(v, (int, float)) else ("—" if v is None else dash(v))))

    if rows:
        calc_table = "<table class='compact-table'><thead><tr><th>Показатель</th><th>Значение</th></tr></thead><tbody>"
        calc_table += "".join(f"<tr><td>{esc(a)}</td><td>{esc(b)}</td></tr>" for a, b in rows)
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