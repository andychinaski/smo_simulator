# ui/simulation_tab.py
from __future__ import annotations

import copy
import json
from typing import Optional, Dict, Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QTextEdit,
    QPushButton,
    QHBoxLayout,
    QFileDialog,
    QMessageBox,
)

from ui.model_params_widget import ModelParamsWidget
from simulation import simulate, build_servers


class SimulationTab(QWidget):
    """
    Вкладка "Симуляция":
    - отображение параметров модели
    - кнопки "Настройка параметров" и "Запустить симуляцию"
    - запуск симуляции
    - вывод результатов
    - сохранение результатов симуляции в JSON (появляется кнопка после запуска)

    Формат сохранения:
    {
      "config": {...},
      "summary": {
        "arrivals": 7620,
        "served": 5735,
        "refused": 1885
      },
      "requests": [...]
    }
    """

    open_settings_requested = Signal()
    simulation_finished = Signal(object)   # SimulationResult
    simulation_failed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._config: Optional[Dict[str, Any]] = None
        self._last_config_snapshot: Optional[Dict[str, Any]] = None
        self._last_result = None

        layout = QVBoxLayout(self)

        self.params = ModelParamsWidget()
        layout.addWidget(self.params)

        results_title = QLabel("Результаты симуляции")
        results_title.setStyleSheet("font-size:14px; font-weight:bold;")
        layout.addWidget(results_title)

        self.results_box = QTextEdit()
        self.results_box.setReadOnly(True)
        self.results_box.setPlaceholderText("Нажмите «Запустить симуляцию»")
        layout.addWidget(self.results_box)

        layout.addStretch()

        self.save_button = QPushButton("Сохранить результаты")
        self.save_button.clicked.connect(self.save_results_as)
        self.save_button.setVisible(False)  # появляется только после успешной симуляции
        layout.addWidget(self.save_button)

        buttons_layout = QHBoxLayout()

        self.settings_button = QPushButton("Настройка параметров")
        self.settings_button.clicked.connect(self.open_settings_requested.emit)

        self.run_button = QPushButton("Запустить симуляцию")
        self.run_button.clicked.connect(self.run_simulation)

        buttons_layout.addWidget(self.settings_button)
        buttons_layout.addWidget(self.run_button)

        layout.addLayout(buttons_layout)

    # --------------------------

    def set_config(self, config: Dict[str, Any]):
        self._config = config
        self.params.update_view(config)

        # если конфиг изменился — старые результаты считаем неактуальными
        self._last_result = None
        self._last_config_snapshot = None
        self.save_button.setVisible(False)

    def clear_results(self):
        self.results_box.clear()

    def set_results_text(self, text: str):
        self.results_box.setPlainText(text)

    # --------------------------

    def run_simulation(self):
        self.clear_results()
        self.save_button.setVisible(False)

        if not self._config:
            self.simulation_failed.emit("Конфиг не загружен")
            return

        try:
            res = simulate(self._config)
            self._last_result = res
            self._last_config_snapshot = copy.deepcopy(self._config)  # фиксируем конфиг на момент запуска
        except Exception as e:
            self.simulation_failed.emit(str(e))
            return

        # Для красивого вывода утилизации по именам серверов
        try:
            servers = build_servers(self._config.get("operators", []))
        except Exception:
            servers = []

        lines = []
        lines.append("Сводка:")
        lines.append(f"  Пришло заявок: {int(res.stats.get('total_arrivals', 0))}")
        lines.append(f"  Обслужено: {int(res.stats.get('served', 0))}")
        lines.append(f"  Отказов: {int(res.stats.get('refused', 0))}")

        self.set_results_text("\n".join(lines))

        self.save_button.setVisible(True)
        self.simulation_finished.emit(res)

    # --------------------------

    def _build_export_payload(self) -> Dict[str, Any]:
        if self._last_result is None or self._last_config_snapshot is None:
            raise RuntimeError("Нет результатов симуляции для сохранения")

        # summary только из 3 полей (как вы хотите)
        summary = {
            "arrivals": int(self._last_result.stats.get("total_arrivals", 0)),
            "served": int(self._last_result.stats.get("served", 0)),
            "refused": int(self._last_result.stats.get("refused", 0)),
        }

        reqs = []
        for r in self._last_result.requests:
            reqs.append({
                "id": r.id,
                "t_arrival": r.t_arrival,
                "t_queue_enter": r.t_queue_enter,
                "t_service_start": r.t_service_start,
                "server_id": r.server_id,
                "server_name": r.server_name,
                "t_service_end": r.t_service_end,
                "t_refuse": r.t_refuse,
            })

        return {
            "config": self._last_config_snapshot,
            "summary": summary,
            "requests": reqs,
        }

    def save_results_as(self):
        if self._last_result is None:
            QMessageBox.warning(self, "Сохранение", "Сначала запустите симуляцию.")
            return

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить результаты симуляции",
            "simulation_results.json",
            "JSON (*.json)"
        )
        if not path:
            return

        if not path.lower().endswith(".json"):
            path += ".json"

        try:
            payload = self._build_export_payload()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка сохранения", str(e))
            return

        QMessageBox.information(self, "Сохранено", f"Результаты сохранены в:\n{path}")