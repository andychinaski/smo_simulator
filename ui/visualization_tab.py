# visualization_tab.py
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QDialog,
    QDialogButtonBox,
    QSpinBox,
    QDoubleSpinBox,
)

from visualization.html_generator import (
    build_html_from_saved_result,
    build_parameter_charts_html,
)
from visualization.exporters import (
    PngExportOptions,
    export_timeline_png,
    export_timeline_xlsx,
)


class VisualizationTab(QWidget):
    """Вкладка визуализации: HTML по одной симуляции и графики по пачке расчетов."""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel("Визуализация")
        title.setStyleSheet("font-size:14px; font-weight:bold;")
        layout.addWidget(title)

        hint = QLabel(
            "Кнопка «Построить временную диаграмму» строит HTML-страницу по одному JSON-файлу.\n"
            "Кнопка «Построить графики параметров» принимает несколько JSON-файлов с блоком calculations "
            "и строит графики рассчитанных показателей по экспериментам."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.build_button = QPushButton("Построить временную диаграмму")
        self.build_button.clicked.connect(self.build_graph)
        layout.addWidget(self.build_button)

        self.build_parameter_charts_button = QPushButton("Построить графики параметров")
        self.build_parameter_charts_button.clicked.connect(self.build_parameter_charts)
        layout.addWidget(self.build_parameter_charts_button)

        export_layout = QHBoxLayout()

        self.export_xlsx_button = QPushButton("Экспорт данных в XLSX")
        self.export_xlsx_button.clicked.connect(self.export_xlsx)
        export_layout.addWidget(self.export_xlsx_button)

        self.export_png_button = QPushButton("Экспорт диаграммы в PNG")
        self.export_png_button.clicked.connect(self.export_png)
        export_layout.addWidget(self.export_png_button)

        layout.addLayout(export_layout)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()

    def set_text(self, text: str):
        """Оставлено для совместимости с main_window."""
        self.status_label.setText(text)

    def build_graph(self):
        json_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите сохраненный результат симуляции (JSON)",
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

        try:
            html_text = build_html_from_saved_result(saved)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сгенерировать HTML:\n{e}")
            return

        html_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить HTML-страницу",
            "visualization.html",
            "HTML (*.html)"
        )
        if not html_path:
            return
        if not html_path.lower().endswith(".html"):
            html_path += ".html"

        if self._write_html(html_path, html_text):
            self.status_label.setText(f"HTML сохранен: {html_path}")
            QMessageBox.information(self, "Готово", f"HTML сохранен:\n{html_path}")

    def build_parameter_charts(self):
        json_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Выберите JSON-файлы с расчетами",
            "results",
            "JSON (*.json)"
        )
        if not json_paths:
            return

        payloads: List[Dict[str, Any]] = []
        source_names: List[str] = []
        errors: List[str] = []

        for path in json_paths:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("ожидался JSON-объект")
                payloads.append(data)
                source_names.append(os.path.basename(path))
            except Exception as e:
                errors.append(f"{os.path.basename(path)}: {e}")

        if errors:
            QMessageBox.warning(
                self,
                "Часть файлов не прочитана",
                "Некоторые JSON-файлы пропущены:\n" + "\n".join(errors)
            )

        if not payloads:
            QMessageBox.critical(self, "Ошибка", "Не удалось прочитать ни один JSON-файл.")
            return

        try:
            html_text = build_parameter_charts_html(payloads, source_names)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось построить графики:\n{e}")
            return

        html_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить HTML-страницу с графиками",
            "parameter_charts.html",
            "HTML (*.html)"
        )
        if not html_path:
            return
        if not html_path.lower().endswith(".html"):
            html_path += ".html"

        if self._write_html(html_path, html_text):
            self.status_label.setText(f"HTML с графиками сохранен: {html_path}")
            QMessageBox.information(self, "Готово", f"HTML с графиками сохранен:\n{html_path}")

    def export_xlsx(self):
        saved = self._pick_and_load_simulation_json()
        if saved is None:
            return

        xlsx_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить данные временной диаграммы",
            "timeline_export.xlsx",
            "Excel (*.xlsx)"
        )
        if not xlsx_path:
            return
        if not xlsx_path.lower().endswith(".xlsx"):
            xlsx_path += ".xlsx"

        try:
            export_timeline_xlsx(saved, xlsx_path)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать XLSX:\n{e}")
            return

        self.status_label.setText(f"XLSX сохранен: {xlsx_path}")
        QMessageBox.information(self, "Готово", f"XLSX сохранен:\n{xlsx_path}")

    def export_png(self):
        saved = self._pick_and_load_simulation_json()
        if saved is None:
            return

        options = self._ask_png_options()
        if options is None:
            return

        png_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить временную диаграмму в PNG",
            "timeline_export.png",
            "PNG (*.png)"
        )
        if not png_path:
            return
        if not png_path.lower().endswith(".png"):
            png_path += ".png"

        try:
            export_timeline_png(saved, png_path, options)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось экспортировать PNG:\n{e}")
            return

        self.status_label.setText(f"PNG сохранен: {png_path}")
        QMessageBox.information(self, "Готово", f"PNG сохранен:\n{png_path}")

    def _pick_and_load_simulation_json(self) -> Optional[Dict[str, Any]]:
        json_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите сохраненный результат симуляции (JSON)",
            "results",
            "JSON (*.json)"
        )
        if not json_path:
            return None

        try:
            with open(json_path, "r", encoding="utf-8") as f:
                saved = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось прочитать JSON:\n{e}")
            return None

        if not isinstance(saved, dict):
            QMessageBox.critical(self, "Ошибка", "Ожидался JSON-объект с результатами симуляции.")
            return None
        return saved

    def _ask_png_options(self) -> Optional[PngExportOptions]:
        dialog = QDialog(self)
        dialog.setWindowTitle("Параметры PNG")

        layout = QVBoxLayout(dialog)
        form = QFormLayout()

        width_input = QSpinBox(dialog)
        width_input.setRange(900, 2000)
        width_input.setSingleStep(50)
        width_input.setValue(1300)
        form.addRow("Ширина картинки, px", width_input)

        hours_input = QDoubleSpinBox(dialog)
        hours_input.setRange(0.25, 24.0)
        hours_input.setSingleStep(0.25)
        hours_input.setDecimals(2)
        hours_input.setValue(3.0)
        form.addRow("Часов в одной строке", hours_input)

        tick_input = QDoubleSpinBox(dialog)
        tick_input.setRange(0.05, 12.0)
        tick_input.setSingleStep(0.25)
        tick_input.setDecimals(2)
        tick_input.setValue(0.5)
        form.addRow("Шаг сетки, часов", tick_input)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dialog)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() != QDialog.Accepted:
            return None

        return PngExportOptions(
            image_width=width_input.value(),
            hours_per_strip=hours_input.value(),
            tick_step=tick_input.value(),
        )

    def _write_html(self, path: str, html_text: str) -> bool:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(html_text)
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось сохранить HTML:\n{e}")
            return False
        return True
