# ui/calculations_tab.py
from __future__ import annotations

import json
import os
import copy
from typing import Optional, Dict, Any, List, Tuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QTextEdit,
    QCheckBox,
    QPushButton,
    QHBoxLayout,
    QScrollArea,
    QMessageBox,
    QFrame,
    QFileDialog,
    QComboBox,
    QSpinBox,
    QFormLayout,
    QGroupBox,
)


CALC_CONFIG_PATH = "calc_config.json"

# (key, label, tooltip)
METRICS: List[Tuple[str, str, str]] = [
    ("p_served", "1) Вероятность обслуживания (Pобс.)", "Pобс. = Nобс./N"),
    ("throughput", "2) Пропускная способность системы (A)", "A = Nобс./Tн [шт/час]"),
    ("p_refuse", "3) Вероятность отказа (Pотк.)", "Pотк. = Nотк./N"),
    ("p_busy_1", "4) Вероятность занятости одного канала (P1)", "P1 = Tзан(ровно 1 канал)/Tн"),
    ("p_busy_2", "5) Вероятность занятости двух каналов (P2)", "P2 = Tзан(2 канала)/Tн"),
    ("avg_busy_channels", "6) Среднее количество занятых каналов (Nск)", "Nск = 0·P0 + 1·P1 + 2·P2 + ..."),
    ("p_idle_at_least1", "7) Вероятность простоя хотя бы одного канала (P*1)", "P*1 = Tпростоя(>=1 канал)/Tн"),
    ("p_idle_2", "8) Вероятность простоя двух каналов одновременно (P*2)", "P*2 = Tпростоя(2 канала)/Tн"),
    ("p_idle_system", "9) Вероятность простоя всей системы (P*c)", "P*c = Tпростоя(сист.)/Tн"),
    ("avg_queue_len", "10) Среднее количество заявок в очереди (Nсз)", "Nсз = Σ k·Pkз"),
    ("p_queue_1", "11) Вероятность очереди = 1 заявка (P1з)", "P1з = T1з/Tн"),
    ("p_queue_2", "12) Вероятность очереди = 2 заявки (P2з)", "P2з = T2з/Tн"),
    ("avg_wait_time", "13) Среднее время ожидания в очереди", "Σ(wait) / count(wait>0)"),
    ("avg_service_time", "14) Среднее время обслуживания заявки", "Σ(service) / served_count"),
    ("avg_system_time", "15) Среднее время в системе", "Tср(сист) = Tср(ож) + Tср(обсл)"),
    ("avg_system_count", "16) Среднее количество заявок в системе", "Будет определено позже."),
]


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


class CalculationsTab(QWidget):
    """
    Вкладка 'Расчеты':
    - выбор показателей (чекбоксы)
    - warm-up (нет / N часов / N заявок) [целое]
    - выбрать файл результатов симуляции (JSON)
    - запомнить выбор -> calc_config.json
    - рассчитать -> вывод текста
    - сохранить результат в txt / json (пока кнопки неактивны до расчёта)
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self.sim_results_path: Optional[str] = None
        self._loaded_sim_json: Optional[Dict[str, Any]] = None
        self._last_calc_text: Optional[str] = None
        self._last_calc_payload: Optional[Dict[str, Any]] = None  # enriched json to save

        layout = QVBoxLayout(self)

        title = QLabel("Расчеты (аналитика)")
        title.setStyleSheet("font-size:14px; font-weight:bold;")
        layout.addWidget(title)

        # -------- source file group --------
        src_group = QGroupBox("Источник данных")
        src_form = QFormLayout(src_group)

        self.pick_sim_json_btn = QPushButton("Выбрать JSON результатов симуляции…")
        self.pick_sim_json_btn.clicked.connect(self.pick_simulation_json)

        self.sim_json_label = QLabel("Файл не выбран")
        self.sim_json_label.setWordWrap(True)

        src_form.addRow(self.pick_sim_json_btn, self.sim_json_label)
        layout.addWidget(src_group)

        # -------- warmup group --------
        warm_group = QGroupBox("Период прогрева (warm-up)")
        warm_form = QFormLayout(warm_group)

        self.warm_mode = QComboBox()
        self.warm_mode.addItem("Нет", "none")
        self.warm_mode.addItem("Пропустить первые N часов", "hours")
        self.warm_mode.addItem("Пропустить первые N заявок", "arrivals")
        self.warm_mode.currentIndexChanged.connect(self._update_warmup_ui_state)

        self.warm_value = QSpinBox()
        self.warm_value.setRange(0, 10_000_000)
        self.warm_value.setValue(0)

        warm_form.addRow("Режим:", self.warm_mode)
        warm_form.addRow("N:", self.warm_value)
        layout.addWidget(warm_group)

        # -------- checklist (scroll) --------
        hint = QLabel(
            "Выберите показатели для расчёта. "
            "Кнопка «Запомнить выбор» сохранит набор галочек и параметры прогрева в calc_config.json."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.checkboxes: Dict[str, QCheckBox] = {}

        cb_container_layout = QVBoxLayout()
        cb_container_layout.setAlignment(Qt.AlignTop)
        cb_container_layout.setSpacing(6)

        cb_container_widget = QWidget()
        cb_container_widget.setLayout(cb_container_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(cb_container_widget)
        scroll.setMaximumHeight(240)  # <- уменьшили высоту блока выбора параметров
        layout.addWidget(scroll)

        for key, label, tooltip in METRICS:
            cb = QCheckBox(label)
            if tooltip:
                cb.setToolTip(tooltip)
            self.checkboxes[key] = cb
            cb_container_layout.addWidget(cb)

        # -------- separator --------
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        # -------- main buttons --------
        buttons = QHBoxLayout()

        self.save_selection_btn = QPushButton("Запомнить выбор")
        self.save_selection_btn.clicked.connect(self.save_selection)

        self.calculate_btn = QPushButton("Рассчитать")
        self.calculate_btn.clicked.connect(self.calculate)

        buttons.addWidget(self.save_selection_btn)
        buttons.addWidget(self.calculate_btn)

        layout.addLayout(buttons)

        # -------- result box --------
        self.box = QTextEdit()
        self.box.setReadOnly(True)
        self.box.setPlaceholderText("Результаты расчётов появятся здесь.")
        layout.addWidget(self.box)

        # -------- export buttons (disabled initially) --------
        export_buttons = QHBoxLayout()

        self.save_txt_btn = QPushButton("Сохранить в TXT")
        self.save_txt_btn.setEnabled(False)
        self.save_txt_btn.clicked.connect(self.save_report_txt)

        self.save_json_btn = QPushButton("Сохранить в JSON")
        self.save_json_btn.setEnabled(False)
        self.save_json_btn.clicked.connect(self.save_report_json)

        export_buttons.addWidget(self.save_txt_btn)
        export_buttons.addWidget(self.save_json_btn)

        layout.addLayout(export_buttons)

        # initial state
        self._update_warmup_ui_state()
        self.load_selection(silent=True)

    # -------- lifecycle --------

    def showEvent(self, event):
        super().showEvent(event)
        self.load_selection(silent=True)

    # -------- warmup --------

    def _update_warmup_ui_state(self):
        mode = self.warm_mode.currentData()
        self.warm_value.setEnabled(mode != "none")
        if mode == "none":
            self.warm_value.setValue(0)

    def get_warmup(self) -> Dict[str, Any]:
        mode = str(self.warm_mode.currentData())
        value = int(self.warm_value.value())
        if mode == "none":
            value = 0
        return {"mode": mode, "value": value}

    def apply_warmup(self, warmup: Dict[str, Any]) -> None:
        mode = str(warmup.get("mode", "none"))
        value = int(warmup.get("value", 0) or 0)

        idx = self.warm_mode.findData(mode)
        if idx == -1:
            idx = 0
        self.warm_mode.setCurrentIndex(idx)

        self.warm_value.setValue(max(0, value))
        self._update_warmup_ui_state()

    # -------- selection config --------

    def get_selection_state(self) -> Dict[str, bool]:
        return {key: cb.isChecked() for key, cb in self.checkboxes.items()}

    def apply_selection_state(self, state: Dict[str, Any]) -> None:
        for key, cb in self.checkboxes.items():
            cb.setChecked(bool(state.get(key, False)))

    def clear_all(self) -> None:
        for cb in self.checkboxes.values():
            cb.setChecked(False)

    def load_selection(self, silent: bool = False) -> None:
        if not os.path.exists(CALC_CONFIG_PATH):
            self.clear_all()
            self.apply_warmup({"mode": "none", "value": 0})
            if not silent:
                QMessageBox.information(self, "Конфиг расчётов", "Файл calc_config.json не найден. Все галочки сняты.")
            return

        try:
            with open(CALC_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            self.clear_all()
            self.apply_warmup({"mode": "none", "value": 0})
            if not silent:
                QMessageBox.warning(self, "Конфиг расчётов", f"Не удалось прочитать calc_config.json:\n{e}")
            return

        if not isinstance(cfg, dict):
            self.clear_all()
            self.apply_warmup({"mode": "none", "value": 0})
            return

        selection = cfg.get("selection")
        if isinstance(selection, dict):
            self.apply_selection_state(selection)
        else:
            # fallback: если в файле лежали напрямую ключи
            self.apply_selection_state(cfg)

        warmup = cfg.get("warmup")
        if isinstance(warmup, dict):
            self.apply_warmup(warmup)
        else:
            self.apply_warmup({"mode": "none", "value": 0})

    def save_selection(self) -> None:
        cfg = {
            "version": 1,
            "selection": self.get_selection_state(),
            "warmup": self.get_warmup(),
        }

        try:
            with open(CALC_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "Сохранение", f"Не удалось сохранить {CALC_CONFIG_PATH}:\n{e}")
            return

        QMessageBox.information(self, "Сохранение", f"Выбор сохранён в {CALC_CONFIG_PATH}")

    # -------- source selection --------

    def pick_simulation_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите результаты симуляции (JSON)",
            "",
            "JSON (*.json)"
        )
        if not path:
            return
        self.set_simulation_json_path(path)

    def set_simulation_json_path(self, path: str) -> None:
        self.sim_results_path = path
        self.sim_json_label.setText(path)

        # сбрасываем результаты расчёта (теперь источник другой)
        self._loaded_sim_json = None
        self._last_calc_text = None
        self._last_calc_payload = None
        self.save_txt_btn.setEnabled(False)
        self.save_json_btn.setEnabled(False)

    def _load_simulation_json(self) -> Dict[str, Any]:
        if not self.sim_results_path:
            raise RuntimeError("Не выбран файл результатов симуляции (JSON).")

        try:
            with open(self.sim_results_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise RuntimeError(f"Не удалось прочитать JSON:\n{e}")

        if not isinstance(data, dict):
            raise RuntimeError("Некорректный JSON: ожидается объект.")

        if "config" not in data or "requests" not in data:
            raise RuntimeError("Некорректный JSON: ожидаются поля 'config' и 'requests'.")

        if not isinstance(data.get("requests"), list):
            raise RuntimeError("Некорректный JSON: поле 'requests' должно быть списком.")

        return data

    # -------- calculations (partially implemented) --------

    def get_selected_metric_keys(self) -> List[str]:
        return [k for k, cb in self.checkboxes.items() if cb.isChecked()]

    def _warmup_cut_time(self, requests: List[Dict[str, Any]], duration: float) -> float:
        warm = self.get_warmup()
        mode = warm["mode"]
        n = int(warm["value"])

        if mode == "none" or n <= 0:
            return 0.0

        if mode == "hours":
            return float(min(max(0, n), int(duration)))

        if mode == "arrivals":
            if n >= len(requests):
                return float(duration)
            t = _safe_float(requests[n].get("t_arrival"))
            return float(t) if t is not None else 0.0

        return 0.0

    def calculate(self) -> None:
        selected = self.get_selected_metric_keys()
        if not selected:
            self.box.setPlainText("Не выбрано ни одного показателя. Отметьте галочки и нажмите «Рассчитать».")
            return

        try:
            data = self._load_simulation_json()
        except Exception as e:
            QMessageBox.critical(self, "Расчёт", str(e))
            return

        self._loaded_sim_json = data

        config = data.get("config", {})
        requests = data.get("requests", [])
        summary = data.get("summary", {})

        duration = _safe_float(config.get("duration"))
        if duration is None or duration <= 0:
            QMessageBox.critical(self, "Расчёт", "В JSON нет корректного config.duration (часов).")
            return

        t_warm = self._warmup_cut_time(requests, duration)
        t0 = float(t_warm)
        t1 = float(duration)
        Tn = max(0.0, t1 - t0)

        # counts in observation interval [t0, t1]
        def in_interval(t: Optional[float]) -> bool:
            return t is not None and (t0 <= t <= t1)

        N = 0
        N_ref = 0
        N_serv = 0

        for r in requests:
            t_arr = _safe_float(r.get("t_arrival"))
            if in_interval(t_arr):
                N += 1

            t_ref = _safe_float(r.get("t_refuse"))
            if in_interval(t_ref):
                N_ref += 1

            t_end = _safe_float(r.get("t_service_end"))
            if in_interval(t_end):
                N_serv += 1

        # compute implemented metrics
        results: Dict[str, Any] = {}
        if N > 0:
            results["p_served"] = N_serv / N
            results["p_refuse"] = N_ref / N
        else:
            results["p_served"] = None
            results["p_refuse"] = None

        if Tn > 0:
            results["throughput"] = N_serv / Tn
        else:
            results["throughput"] = None

        # placeholders for non-implemented selected metrics
        for k in selected:
            results.setdefault(k, None)

        # render text report
        name_by_key = {k: lbl for (k, lbl, _tt) in METRICS}

        lines = []
        lines.append("Источник данных:")
        lines.append(f"  Файл: {self.sim_results_path}")
        if isinstance(summary, dict) and summary:
            lines.append("  Сводка (из файла):")
            lines.append(f"    arrivals: {summary.get('arrivals', '—')}")
            lines.append(f"    served:   {summary.get('served', '—')}")
            lines.append(f"    refused:  {summary.get('refused', '—')}")
        lines.append("")
        lines.append("Окно наблюдения для расчётов:")
        lines.append(f"  warm-up t0 = {t0} ч")
        lines.append(f"  t1 = {t1} ч")
        lines.append(f"  Tн = {Tn} ч")
        lines.append(f"  N (пришло в окне): {N}")
        lines.append(f"  Nобс (завершено в окне): {N_serv}")
        lines.append(f"  Nотк (отказов в окне): {N_ref}")
        lines.append("")

        lines.append("Результаты (часть метрик пока заглушки):")
        for k in selected:
            v = results.get(k)
            if isinstance(v, float):
                lines.append(f"  - {name_by_key.get(k, k)} = {v:.6f}")
            else:
                lines.append(f"  - {name_by_key.get(k, k)} = —")

        lines.append("")
        lines.append("Примечание: сейчас реально считаются только метрики 1–3; остальные будут реализованы следующим шагом.")

        report_text = "\n".join(lines)
        self.box.setPlainText(report_text)

        # build enriched json payload (save-as new file)
        warmup_block = self.get_warmup()
        payload = copy.deepcopy(data)
        payload["calculations"] = {
            "warmup": warmup_block,
            "selected_metrics": selected,
            "results": {k: results.get(k) for k in selected},
        }

        self._last_calc_text = report_text
        self._last_calc_payload = payload

        # enable export buttons
        self.save_txt_btn.setEnabled(True)
        self.save_json_btn.setEnabled(True)

    # -------- exports --------

    def save_report_txt(self) -> None:
        if not self._last_calc_text:
            QMessageBox.warning(self, "Сохранение", "Сначала выполните расчёт.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить отчёт в TXT",
            "calculations_report.txt",
            "Text (*.txt)"
        )
        if not path:
            return
        if not path.lower().endswith(".txt"):
            path += ".txt"

        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._last_calc_text)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить TXT:\n{e}")
            return

        QMessageBox.information(self, "Сохранено", f"Отчёт сохранён:\n{path}")

    def save_report_json(self) -> None:
        if not self._last_calc_payload:
            QMessageBox.warning(self, "Сохранение", "Сначала выполните расчёт.")
            return
        if not self.sim_results_path:
            QMessageBox.warning(self, "Сохранение", "Не выбран исходный JSON симуляции.")
            return

        default_name = "simulation_results_with_calculations.json"
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить обогащённый JSON",
            default_name,
            "JSON (*.json)"
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._last_calc_payload, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить JSON:\n{e}")
            return

        QMessageBox.information(self, "Сохранено", f"JSON сохранён:\n{path}")

    # совместимость со старым main_window
    def set_text(self, text: str):
        self.box.setPlainText(text)