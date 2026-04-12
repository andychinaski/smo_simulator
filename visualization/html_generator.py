# visualization/html_generator.py
from __future__ import annotations

import html as html_lib
from typing import Any, Dict, List, Optional


def _esc(x: Any) -> str:
    return html_lib.escape(str(x))


def _dash_if_none(x: Any) -> str:
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


def build_html_from_saved_result(saved: Dict[str, Any]) -> str:
    """
    saved ожидается в формате:
    {
      "config": {...},
      "requests": [...]
    }

    Пока формируем HTML только по config (без сырых дампов).
    """
    if not isinstance(saved, dict):
        raise ValueError("Некорректный формат данных (ожидается JSON-объект)")

    config = saved.get("config")
    if not isinstance(config, dict):
        raise ValueError("В файле нет корректного поля 'config'")

    operators: List[Dict[str, Any]] = config.get("operators") or []
    if not isinstance(operators, list):
        operators = []

    # основные поля (возможны None/отсутствие)
    call_flow = config.get("call_flow")
    queue_size = config.get("queue_size")
    duration = config.get("duration")
    free_server_policy = config.get("free_server_policy")
    drain = config.get("drain")
    seed = config.get("seed")
    start_at_zero = config.get("start_at_zero")
    max_arrivals = config.get("max_arrivals")

    # таблица операторов
    operators_rows = []
    for op in operators:
        if not isinstance(op, dict):
            continue
        operators_rows.append(
            "<tr>"
            f"<td>{_dash_if_none(op.get('type'))}</td>"
            f"<td>{_dash_if_none(op.get('mu'))}</td>"
            f"<td>{_dash_if_none(op.get('count', 1))}</td>"
            "</tr>"
        )

    operators_table = (
        "<table>"
        "<thead>"
        "<tr>"
        "<th>Тип канала</th>"
        "<th>Скорость обслуживания μ (заявок/час)</th>"
        "<th>Количество</th>"
        "</tr>"
        "</thead>"
        "<tbody>"
        + ("".join(operators_rows) if operators_rows else "<tr><td colspan='3'>—</td></tr>")
        + "</tbody></table>"
    )

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
      min-width: 320px;
      color: #555;
    }}
  </style>
</head>
<body>
  <h1>Визуализация СМО</h1>

  <div class="section">
    <h2>Параметры модели</h2>
    <div class="kv">
      <div><span class="k">Интенсивность потока заявок (λ), заявок/час:</span> {_dash_if_none(call_flow)}</div>
      <div><span class="k">Размер очереди (макс. заявок в ожидании):</span> {_dash_if_none(queue_size)}</div>
      <div><span class="k">Длительность моделирования, часов:</span> {_dash_if_none(duration)}</div>
      <div><span class="k">Политика выбора свободного канала:</span> {_fmt_policy(free_server_policy)}</div>
      <div><span class="k">Доработать хвост после duration (drain):</span> {_fmt_bool(drain)}</div>
      <div><span class="k">Seed (воспроизводимость):</span> {_dash_if_none(seed)}</div>
      <div><span class="k">Первая заявка в момент t = 0 (start_at_zero):</span> {_fmt_bool(start_at_zero)}</div>
      <div><span class="k">Ограничение числа заявок (max_arrivals):</span> {_dash_if_none(max_arrivals)}</div>
    </div>
  </div>

  <div class="section">
    <h2>Каналы обслуживания</h2>
    {operators_table}
  </div>

  <div class="section">
    <h2>График</h2>
    <p>Пока не реализован. Логику добавим позже.</p>
  </div>

</body>
</html>
"""
    return html