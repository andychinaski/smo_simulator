from __future__ import annotations

import json
from typing import Optional

from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QPushButton,
    QFileDialog,
    QMessageBox,
)

from visualization.html_generator import build_html_from_saved_result


class VisualizationTab(QWidget):
    """Вкладка 'Визуализация': пока только генерация HTML по сохранённому результату."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel("Визуализация")
        title.setStyleSheet("font-size:14px; font-weight:bold;")
        layout.addWidget(title)

        hint = QLabel(
            "Нажмите «Построить график», выберите сохранённый JSON с результатами симуляции.\n"
            "Далее будет сгенерирован HTML (пока на основе конфига из файла)."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.build_button = QPushButton("Построить график")
        self.build_button.clicked.connect(self.build_graph)
        layout.addWidget(self.build_button)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()

    def set_text(self, text: str):
        """Оставлено для совместимости с main_window (можно убрать позже)."""
        self.status_label.setText(text)

    def build_graph(self):
        # 1) выбрать сохранённый результат (json)
        json_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите сохранённый результат симуляции (JSON)",
            "",
            "JSON (*.json)"
        )
        if not json_path:
            return

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось прочитать JSON:\n{e}")
            return

        # 2) сгенерировать html (логика вне ui)
        try:
            html_text = build_html_from_saved_result(saved)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сгенерировать HTML:\n{e}")
            return

        # 3) выбрать куда сохранить html
        html_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить HTML страницу",
            "visualization.html",
            "HTML (*.html)"
        )
        if not html_path:
            return
        if not html_path.lower().endswith(".html"):
            html_path += ".html"

        try:
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_text)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить HTML:\n{e}")
            return

        self.status_label.setText(f"HTML сохранён: {html_path}")
        QMessageBox.information(self, "Готово", f"HTML сохранён:\n{html_path}")