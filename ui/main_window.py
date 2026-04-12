import json

from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QFrame
)

from ui.settings_window import SettingsWindow


CONFIG_PATH = "config.json"

DEFAULT_CONFIG = {
    "call_flow": 0,
    "operators": [],
    "queue_size": 0,
    "duration": 1
}


class MainWindow(QWidget):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("СМО – симулятор")
        self.setFixedSize(500, 400)

        self.setStyleSheet("""
            QLabel {
                font-size: 12px;
            }

            QPushButton {
                padding: 6px 12px;
            }
        """)

        main_layout = QVBoxLayout()

        # -------- Заголовок --------

        title = QLabel("Параметры модели")
        title.setStyleSheet("font-size:14px; font-weight:bold;")

        main_layout.addWidget(title)

        # -------- Форма параметров --------

        self.form_layout = QFormLayout()

        self.call_flow_label = QLabel()
        self.channels_label = QLabel()
        self.queue_label = QLabel()
        self.duration_label = QLabel()

        self.channels_label.setWordWrap(True)

        self.form_layout.addRow("Интенсивность событий:", self.call_flow_label)
        self.form_layout.addRow("Каналы:", self.channels_label)
        self.form_layout.addRow("Размер очереди:", self.queue_label)
        self.form_layout.addRow("Продолжительность:", self.duration_label)

        main_layout.addLayout(self.form_layout)

        # -------- Разделитель --------

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        main_layout.addWidget(line)

        # spacer чтобы кнопки были внизу
        main_layout.addStretch()

        # -------- Кнопки --------

        buttons_layout = QHBoxLayout()

        self.settings_button = QPushButton("Настройка параметров")
        self.settings_button.clicked.connect(self.open_settings)

        self.run_button = QPushButton("Запустить симуляцию")
        self.run_button.clicked.connect(self.run_simulation)

        buttons_layout.addWidget(self.settings_button)
        buttons_layout.addWidget(self.run_button)

        main_layout.addLayout(buttons_layout)

        self.setLayout(main_layout)

        self.load_config()

    # --------------------------

    def load_config(self):

        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                self.config = json.load(f)

        except FileNotFoundError:
            self.config = DEFAULT_CONFIG

        except json.JSONDecodeError:
            self.config = DEFAULT_CONFIG

        self.update_view()

    # --------------------------

    def update_view(self):

        if not self.config:
            self.call_flow_label.setText("Конфиг не загружен")
            self.channels_label.setText("")
            self.queue_label.setText("")
            self.duration_label.setText("")
            return

        self.call_flow_label.setText(
            f"{self.config.get('call_flow', 0)} шт/час"
        )

        channels_text = [
            f"{op['type']} – {op['mu']} шт/час ({op['count']} шт)"
            for op in self.config.get("operators", [])
        ]

        self.channels_label.setText("\n".join(channels_text))

        self.queue_label.setText(
            f"{self.config.get('queue_size', 0)} шт"
        )

        self.duration_label.setText(
            f"{self.config.get('duration', 0)} часов"
        )

    # --------------------------

    def open_settings(self):

        self.settings_window = SettingsWindow(self.config)

        if self.settings_window.exec():
            self.load_config()

    # --------------------------

    def run_simulation(self):

        print("Simulation started")