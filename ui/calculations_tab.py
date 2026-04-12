from __future__ import annotations

import json
import os
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
)


CALC_CONFIG_PATH = "calc_config.json"


# (key, label, tooltip)
METRICS: List[Tuple[str, str, str]] = [
    ("p_served", "1) Вероятность обслуживания (Pобс.)",
     "Pобс. = Nобс./N"),
    ("throughput", "2) Пропускная способность системы (A)",
     "A = Nобс./Tн [шт/час]"),
    ("p_refuse", "3) Вероятность отказа (Pотк.)",
     "Pотк. = Nотк./N"),
    ("p_busy_1", "4) Вероятность занятости одного канала (P1)",
     "P1 = Tзан(ровно 1 канал)/Tн"),
    ("p_busy_2", "5) Вероятность занятости двух каналов (P2)",
     "P2 = Tзан(2 канала)/Tн"),
    ("avg_busy_channels", "6) Среднее количество занятых каналов (Nск)",
     "Nск = 0·P0 + 1·P1 + 2·P2 + ..."),
    ("p_idle_at_least1", "7) Вероятность простоя хотя бы одного канала (P*1)",
     "P*1 = Tпростоя(хотя бы 1 канал)/Tн"),
    ("p_idle_2", "8) Вероятность простоя двух каналов одновременно (P*2)",
     "P*2 = Tпростоя(оба канала)/Tн"),
    ("p_idle_system", "9) Вероятность простоя всей системы (P*c)",
     "P*c = Tпростоя(система)/Tн"),
    ("avg_queue_len", "10) Среднее количество заявок в очереди (Nсз)",
     "Nсз = 0·P0з + 1·P1з + 2·P2з + ..."),
    ("p_queue_1", "11) Вероятность очереди = 1 заявка (P1з)",
     "P1з = T1з/Tн"),
    ("p_queue_2", "12) Вероятность очереди = 2 заявки (P2з)",
     "P2з = T2з/Tн"),
    ("avg_wait_time", "13) Среднее время ожидания в очереди",
     "Σ(времён ожидания всех заявок) / (кол-во заявок, которые ждали)"),
    ("avg_service_time", "14) Среднее время обслуживания заявки",
     "Σ(времён обслуживания всех заявок) / (кол-во обслуженных заявок)"),
    ("avg_system_time", "15) Среднее время нахождения заявки в системе",
     "Tср(сист) = Tср(ож) + Tср(обсл)"),
    ("avg_system_count", "16) Среднее количество заявок в системе",
     "Будет определено позже (например, по времени пребывания/закону Литтла)."),
]


class CalculationsTab(QWidget):
    """Вкладка 'Расчеты': выбор показателей + сохранение выбора в отдельный конфиг."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel("Расчеты (аналитика)")
        title.setStyleSheet("font-size:14px; font-weight:bold;")
        layout.addWidget(title)

        hint = QLabel(
            "Выберите показатели для расчёта. "
            "Кнопка «Запомнить выбор» сохранит набор галочек в отдельный файл конфигурации расчётов."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # -------- список чекбоксов (скролл) --------
        self.checkboxes: Dict[str, QCheckBox] = {}

        cb_container_layout = QVBoxLayout()
        cb_container_layout.setAlignment(Qt.AlignTop)
        cb_container_layout.setSpacing(6)

        cb_container_widget = QWidget()
        cb_container_widget.setLayout(cb_container_layout)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(cb_container_widget)
        scroll.setMinimumHeight(260)

        for key, label, tooltip in METRICS:
            cb = QCheckBox(label)
            if tooltip:
                cb.setToolTip(tooltip)
            self.checkboxes[key] = cb
            cb_container_layout.addWidget(cb)

        layout.addWidget(scroll)

        # -------- разделитель --------
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        # -------- кнопки --------
        buttons = QHBoxLayout()

        self.save_selection_btn = QPushButton("Запомнить выбор")
        self.save_selection_btn.clicked.connect(self.save_selection)

        self.calculate_btn = QPushButton("Рассчитать")
        self.calculate_btn.clicked.connect(self.calculate)

        buttons.addWidget(self.save_selection_btn)
        buttons.addWidget(self.calculate_btn)

        layout.addLayout(buttons)

        # -------- поле результата --------
        self.box = QTextEdit()
        self.box.setReadOnly(True)
        self.box.setPlaceholderText("Результаты расчётов появятся здесь.")
        layout.addWidget(self.box)

        # первичная загрузка, если файл уже есть
        self.load_selection(silent=True)

    # -------- lifecycle --------

    def showEvent(self, event):
        # при открытии вкладки — подхватываем актуальный calc_config.json (если он появился/изменился)
        super().showEvent(event)
        self.load_selection(silent=True)

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
            if not silent:
                QMessageBox.information(self, "Конфиг расчётов", "Файл calc_config.json не найден. Все галочки сняты.")
            return

        try:
            with open(CALC_CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            self.clear_all()
            if not silent:
                QMessageBox.warning(self, "Конфиг расчётов", f"Не удалось прочитать calc_config.json:\n{e}")
            return

        # поддержка форматов:
        # 1) {"selection": {"p_served": true, ...}}
        # 2) {"p_served": true, ...}  (упрощённый)
        selection = cfg.get("selection") if isinstance(cfg, dict) else None
        if isinstance(selection, dict):
            self.apply_selection_state(selection)
        elif isinstance(cfg, dict):
            self.apply_selection_state(cfg)
        else:
            self.clear_all()

    def save_selection(self) -> None:
        cfg = {
            "version": 1,
            "selection": self.get_selection_state(),
        }

        try:
            with open(CALC_CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(cfg, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "Сохранение", f"Не удалось сохранить {CALC_CONFIG_PATH}:\n{e}")
            return

        QMessageBox.information(self, "Сохранение", f"Выбор сохранён в {CALC_CONFIG_PATH}")

    # -------- calculations (placeholder) --------

    def get_selected_metric_keys(self) -> List[str]:
        return [k for k, cb in self.checkboxes.items() if cb.isChecked()]

    def calculate(self) -> None:
        selected = self.get_selected_metric_keys()
        if not selected:
            self.box.setPlainText("Не выбрано ни одного показателя. Отметьте галочки и нажмите «Рассчитать».")
            return

        # Пока только UI: выводим, что выбрано. Сама математика будет позже.
        name_by_key = {k: lbl for (k, lbl, _tt) in METRICS}
        lines = ["Выбраны показатели для расчёта:"]
        for k in selected:
            lines.append(f"  - {name_by_key.get(k, k)}")
        lines.append("")
        lines.append("Расчёты пока не реализованы (будут добавлены следующим шагом).")

        self.box.setPlainText("\n".join(lines))

    # для совместимости со старым main_window (если где-то ещё вызываете)
    def set_text(self, text: str):
        self.box.setPlainText(text)