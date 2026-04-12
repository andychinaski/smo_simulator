import json
import shutil

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QSpinBox,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QFileDialog,
    QWidget,
    QScrollArea
)

from ui.operator_row import OperatorRow


CONFIG_PATH = "config.json"
MAX_OPERATORS = 36

class SettingsWindow(QDialog):

    def __init__(self, config):
        super().__init__()

        self.setWindowTitle("Настройки модели")
        self.setFixedSize(450, 420)

        main_layout = QVBoxLayout()

        # ------------------------
        # основные параметры
        # ------------------------

        form = QFormLayout()

        self.flow_input = QSpinBox()
        self.flow_input.setRange(0, 100000)

        self.queue_input = QSpinBox()
        self.queue_input.setRange(0, 10000)

        self.duration_input = QSpinBox()
        self.duration_input.setRange(1, 100000)

        form.addRow("Интенсивность событий:", self.flow_input)
        form.addRow("Размер очереди:", self.queue_input)
        form.addRow("Продолжительность:", self.duration_input)

        main_layout.addLayout(form)

        # ------------------------
        # каналы
        # ------------------------

        channels_title = QLabel("Каналы")
        channels_title.setStyleSheet("font-weight:bold")

        main_layout.addWidget(channels_title)

        self.operators_container = QVBoxLayout()

        self.operators_container.setAlignment(Qt.AlignTop) 
        
        self.operators_container.setSpacing(5)

        container_widget = QWidget()
        container_widget.setLayout(self.operators_container)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(container_widget)
        scroll.setMinimumHeight(200)

        main_layout.addWidget(scroll)

        self.add_operator_btn = QPushButton("Добавить тип канала")
        self.add_operator_btn.clicked.connect(self.add_operator)

        main_layout.addWidget(self.add_operator_btn)

        # spacer
        main_layout.addStretch()

        # ------------------------
        # кнопки
        # ------------------------

        buttons_row1 = QHBoxLayout()

        self.load_btn = QPushButton("Загрузить конфиг")
        self.save_as_btn = QPushButton("Сохранить конфиг")

        self.load_btn.clicked.connect(self.load_config)
        self.save_as_btn.clicked.connect(self.save_config_as)

        buttons_row1.addWidget(self.load_btn)
        buttons_row1.addWidget(self.save_as_btn)

        main_layout.addLayout(buttons_row1)

        buttons_row2 = QHBoxLayout()

        cancel_btn = QPushButton("Отмена")
        save_btn = QPushButton("Сохранить")

        cancel_btn.clicked.connect(self.reject)
        save_btn.clicked.connect(self.save_config)

        buttons_row2.addWidget(cancel_btn)
        buttons_row2.addWidget(save_btn)

        main_layout.addLayout(buttons_row2)

        self.setLayout(main_layout)

        # ------------------------

        if config:
            self.apply_config(config)

    # --------------------------------------------------

    def add_operator(self, data=None):

        if self.operators_container.count() >= MAX_OPERATORS:
            return

        row = OperatorRow()

        if data:
            row.set_data(data)

        # обработка удаления
        row.delete_button.clicked.connect(self.update_add_button_state)

        self.operators_container.addWidget(row)

        self.update_add_button_state()

    # --------------------------------------------------

    def update_add_button_state(self):

        if self.operators_container.count() >= MAX_OPERATORS:
            self.add_operator_btn.setEnabled(False)
        else:
            self.add_operator_btn.setEnabled(True)

    # --------------------------------------------------

    def apply_config(self, config):

        self.flow_input.setValue(config.get("call_flow", 0))
        self.queue_input.setValue(config.get("queue_size", 0))
        self.duration_input.setValue(config.get("duration", 1))

        for op in config.get("operators", []):
            self.add_operator(op)

    # --------------------------------------------------

    def get_config(self):

        operators = []

        for i in range(self.operators_container.count()):

            row = self.operators_container.itemAt(i).widget()

            operators.append(row.get_data())

        return {
            "call_flow": self.flow_input.value(),
            "queue_size": self.queue_input.value(),
            "duration": self.duration_input.value(),
            "operators": operators
        }

    # --------------------------------------------------

    def save_config(self):

        config = self.get_config()

        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

        self.accept()

    # --------------------------------------------------

    def save_config_as(self):

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить конфиг",
            "",
            "JSON (*.json)"
        )

        if not path:
            return

        config = self.get_config()

        with open(path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

    # --------------------------------------------------

    def load_config(self):

        path, _ = QFileDialog.getOpenFileName(
            self,
            "Загрузить конфиг",
            "",
            "JSON (*.json)"
        )

        if not path:
            return

        try:

            with open(path, encoding="utf-8") as f:
                config = json.load(f)

            shutil.copy(path, CONFIG_PATH)

            self.flow_input.setValue(0)

            # очистить операторов
            while self.operators_container.count():
                item = self.operators_container.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()

            self.apply_config(config)

        except Exception as e:

            print("Ошибка загрузки:", e)