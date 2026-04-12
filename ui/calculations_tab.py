from __future__ import annotations

from typing import Optional
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QTextEdit


class CalculationsTab(QWidget):
    """Вкладка "Расчеты" (пока без параметров модели)."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel("Расчеты (аналитика)")
        title.setStyleSheet("font-size:14px; font-weight:bold;")
        layout.addWidget(title)

        self.box = QTextEdit()
        self.box.setReadOnly(True)
        self.box.setPlaceholderText(
            "Раздел в разработке. Тут будут аналитические расчеты.\n"
            "Параметры модели здесь пока не отображаются."
        )
        layout.addWidget(self.box)

    def set_text(self, text: str):
        self.box.setPlainText(text)