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
    QScrollArea,
    QComboBox,
    QCheckBox,
)


from ui.operator_row import OperatorRow


CONFIG_PATH = "config.json"
MAX_OPERATORS = 36


class SettingsWindow(QDialog):
    def __init__(self, config: dict):
        super().__init__()

        self.setWindowTitle("Настройки модели")
        self.setFixedSize(450, 600)

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

        form.addRow("Интенсивность событий (λ), шт/час:", self.flow_input)
        form.addRow("Размер очереди:", self.queue_input)
        form.addRow("Продолжительность, часов:", self.duration_input)

        main_layout.addLayout(form)

        # ------------------------
        # дополнительные параметры симулятора
        # ------------------------

        extra_title = QLabel("Дополнительные параметры симулятора")
        extra_title.setStyleSheet("font-weight:bold")
        main_layout.addWidget(extra_title)

        extra_form = QFormLayout()

        self.policy_input = QComboBox()
        self.policy_input.addItem("Очередь свободных (round-robin)", "round_robin")
        self.policy_input.addItem("Самый быстрый (fastest)", "fastest")

        self.drain_input = QCheckBox("Доработать хвост (после duration)")
        self.start_at_zero_input = QCheckBox("Первая заявка в момент t=0")

        # seed: чекбокс + число
        self.seed_enable = QCheckBox("Использовать seed (воспроизводимость)")
        self.seed_input = QSpinBox()
        self.seed_input.setRange(0, 2_147_483_647)
        self.seed_input.setEnabled(False)
        self.seed_enable.toggled.connect(self.seed_input.setEnabled)

        # max_arrivals: чекбокс + число (опционально)
        self.max_arrivals_enable = QCheckBox("Ограничить число заявок (max_arrivals)")
        self.max_arrivals_input = QSpinBox()
        self.max_arrivals_input.setRange(1, 10_000_000)
        self.max_arrivals_input.setEnabled(False)
        self.max_arrivals_enable.toggled.connect(self.max_arrivals_input.setEnabled)

        extra_form.addRow("Политика свободных серверов:", self.policy_input)
        extra_form.addRow("", self.drain_input)
        extra_form.addRow("", self.start_at_zero_input)
        extra_form.addRow("", self.seed_enable)
        extra_form.addRow("Seed:", self.seed_input)
        extra_form.addRow("", self.max_arrivals_enable)
        extra_form.addRow("Max arrivals:", self.max_arrivals_input)

        main_layout.addLayout(extra_form)

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
        scroll.setMinimumHeight(180)

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

    def clear_operators(self):
        while self.operators_container.count():
            item = self.operators_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.update_add_button_state()

    # --------------------------------------------------

    def add_operator(self, data=None):
        if self.operators_container.count() >= MAX_OPERATORS:
            return

        row = OperatorRow()
        if data:
            row.set_data(data)

        # обработка удаления (в OperatorRow обычно есть логика removeLater)
        row.delete_button.clicked.connect(self.update_add_button_state)

        self.operators_container.addWidget(row)
        self.update_add_button_state()

    # --------------------------------------------------

    def update_add_button_state(self):
        self.add_operator_btn.setEnabled(self.operators_container.count() < MAX_OPERATORS)

    # --------------------------------------------------

    def apply_config(self, config: dict):
        # базовые
        self.flow_input.setValue(int(config.get("call_flow", 0)))
        self.queue_input.setValue(int(config.get("queue_size", 0)))
        self.duration_input.setValue(int(config.get("duration", 1)))

        # дополнительные
        policy = str(config.get("free_server_policy", "round_robin"))
        idx = self.policy_input.findData(policy)
        self.policy_input.setCurrentIndex(idx if idx != -1 else 0)

        self.drain_input.setChecked(bool(config.get("drain", True)))
        self.start_at_zero_input.setChecked(bool(config.get("start_at_zero", True)))

        seed = config.get("seed", None)
        if seed is None or seed == "" or seed == "None":
            self.seed_enable.setChecked(False)
            self.seed_input.setValue(0)
        else:
            self.seed_enable.setChecked(True)
            self.seed_input.setValue(int(seed))

        max_arrivals = config.get("max_arrivals", None)
        if max_arrivals is None or max_arrivals == "" or max_arrivals == "None":
            self.max_arrivals_enable.setChecked(False)
            self.max_arrivals_input.setValue(1)
        else:
            self.max_arrivals_enable.setChecked(True)
            self.max_arrivals_input.setValue(int(max_arrivals))

        # операторы
        self.clear_operators()
        for op in config.get("operators", []):
            self.add_operator(op)

    # --------------------------------------------------

    def get_config(self) -> dict:
        operators = []
        for i in range(self.operators_container.count()):
            row = self.operators_container.itemAt(i).widget()
            operators.append(row.get_data())

        seed_val = int(self.seed_input.value()) if self.seed_enable.isChecked() else None
        max_arrivals_val = int(self.max_arrivals_input.value()) if self.max_arrivals_enable.isChecked() else None

        return {
            # UI-конфиг (как у вас)
            "call_flow": self.flow_input.value(),
            "queue_size": self.queue_input.value(),
            "duration": self.duration_input.value(),
            "operators": operators,

            # доп. параметры симулятора
            "free_server_policy": self.policy_input.currentData(),
            "drain": bool(self.drain_input.isChecked()),
            "seed": seed_val,
            "start_at_zero": bool(self.start_at_zero_input.isChecked()),
            "max_arrivals": max_arrivals_val,
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

            # сохраняем как основной конфиг проекта
            shutil.copy(path, CONFIG_PATH)

            self.apply_config(config)

        except Exception as e:
            print("Ошибка загрузки:", e)