from __future__ import annotations

import json

from PySide6.QtWidgets import QWidget, QVBoxLayout, QMessageBox, QTabWidget

from ui.settings_window import SettingsWindow
from ui.simulation_tab import SimulationTab
from ui.calculations_tab import CalculationsTab
from ui.visualization_tab import VisualizationTab


CONFIG_PATH = "config.json"

DEFAULT_CONFIG = {
    "call_flow": 0,
    "operators": [],
    "queue_size": 0,
    "duration": 1,
    "free_server_policy": "round_robin",  # "round_robin" | "fastest"
    "seed": None,
    "drain": True,
    "start_at_zero": True,
    "max_arrivals": None,
}


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("СМО – симулятор")
        self.setFixedSize(720, 680)

        self.setStyleSheet("""
            QLabel { font-size: 12px; }
            QPushButton { padding: 6px 12px; }
        """)

        self.config: dict = {}
        self.last_simulation_result = None

        main_layout = QVBoxLayout(self)

        # Tabs
        self.tabs = QTabWidget()

        self.sim_tab = SimulationTab()
        self.calc_tab = CalculationsTab()
        self.viz_tab = VisualizationTab()

        self.tabs.addTab(self.sim_tab, "Симуляция")
        self.tabs.addTab(self.calc_tab, "Расчеты")
        self.tabs.addTab(self.viz_tab, "Визуализация")

        main_layout.addWidget(self.tabs)

        # signals from SimulationTab
        self.sim_tab.open_settings_requested.connect(self.open_settings)
        self.sim_tab.simulation_finished.connect(self.on_simulation_finished)
        self.sim_tab.simulation_failed.connect(self.on_simulation_failed)

        self.load_config()

    # --------------------------

    def load_config(self):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                self.config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.config = DEFAULT_CONFIG.copy()

        for k, v in DEFAULT_CONFIG.items():
            self.config.setdefault(k, v)

        # config нужен только вкладке симуляции (пока)
        self.sim_tab.set_config(self.config)

    # --------------------------

    def open_settings(self):
        w = SettingsWindow(self.config)
        if w.exec():
            self.load_config()

    # --------------------------

    def on_simulation_failed(self, message: str):
        QMessageBox.critical(self, "Ошибка симуляции", message)

    # --------------------------

    def on_simulation_finished(self, result_obj):
        """
        result_obj — это SimulationResult (python object).
        Здесь можно:
        - сохранить результат
        - дернуть другие вкладки, чтобы они обновились
        """
        self.last_simulation_result = result_obj

        self.calc_tab.set_text("Симуляция выполнена. Здесь позже появятся аналитические расчеты.")
        self.viz_tab.set_text("Симуляция выполнена. Здесь позже появится визуализация (графики/диаграммы).")