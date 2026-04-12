from __future__ import annotations

from typing import Optional, Dict, Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QTextEdit,
    QPushButton,
    QHBoxLayout,
)

from ui.model_params_widget import ModelParamsWidget
from simulation.simulator import simulate, build_servers


class SimulationTab(QWidget):
    """
    Вкладка "Симуляция":
    - отображение параметров модели
    - кнопки "Настройка параметров" и "Запустить симуляцию"
    - запуск симуляции
    - вывод результатов
    """

    open_settings_requested = Signal()
    simulation_finished = Signal(object)   # SimulationResult
    simulation_failed = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._config: Optional[Dict[str, Any]] = None
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

    def clear_results(self):
        self.results_box.clear()

    def set_results_text(self, text: str):
        self.results_box.setPlainText(text)

    # --------------------------

    def run_simulation(self):
        self.clear_results()

        if not self._config:
            self.simulation_failed.emit("Конфиг не загружен")
            return

        try:
            res = simulate(self._config)
            self._last_result = res
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
        lines.append(f"  Доля отказов: {res.stats.get('refuse_rate', 0.0):.4f}")
        lines.append(f"  Среднее ожидание в очереди: {res.stats.get('avg_wait', 0.0):.6f} ч")
        lines.append(f"  Среднее время в системе: {res.stats.get('avg_system_time', 0.0):.6f} ч")
        lines.append("")
        lines.append("Утилизация каналов (на интервале [0, duration]):")

        if servers:
            for s in servers:
                util = res.server_utilization.get(s.id, 0.0)
                lines.append(f"  {s.name} (μ={s.mu}): {util:.4f}")
        else:
            for sid in sorted(res.server_utilization.keys()):
                lines.append(f"  Server #{sid}: {res.server_utilization[sid]:.4f}")

        self.set_results_text("\n".join(lines))
        self.simulation_finished.emit(res)