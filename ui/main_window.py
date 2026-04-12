import json

from PySide6.QtWidgets import (
    QWidget,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QFrame,
    QTextEdit,
    QMessageBox,
)

from ui.settings_window import SettingsWindow

from simulation.simulator import simulate, build_servers  # <- под текущий симулятор


CONFIG_PATH = "config.json"

DEFAULT_CONFIG = {
    "call_flow": 0,
    "operators": [],
    "queue_size": 0,
    "duration": 1,
    # опциональные параметры симулятора (можно потом добавить в UI):
    "free_server_policy": "round_robin",  # или "fastest"
    "seed": None,
    "drain": True,
    "start_at_zero": True,
}


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("СМО – симулятор")
        self.setFixedSize(650, 520)

        self.setStyleSheet("""
            QLabel { font-size: 12px; }
            QPushButton { padding: 6px 12px; }
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
        self.policy_label = QLabel()
        self.drain_label = QLabel()
        self.seed_label = QLabel()

        self.channels_label.setWordWrap(True)

        self.form_layout.addRow("Интенсивность (λ):", self.call_flow_label)
        self.form_layout.addRow("Каналы:", self.channels_label)
        self.form_layout.addRow("Размер очереди:", self.queue_label)
        self.form_layout.addRow("Продолжительность:", self.duration_label)
        self.form_layout.addRow("Политика свободных серверов:", self.policy_label)
        self.form_layout.addRow("Drain (доработать хвост):", self.drain_label)
        self.form_layout.addRow("Seed:", self.seed_label)

        main_layout.addLayout(self.form_layout)

        # -------- Разделитель --------

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        main_layout.addWidget(line)

        # -------- Результаты --------

        results_title = QLabel("Результаты симуляции")
        results_title.setStyleSheet("font-size:14px; font-weight:bold;")
        main_layout.addWidget(results_title)

        self.results_box = QTextEdit()
        self.results_box.setReadOnly(True)
        self.results_box.setPlaceholderText("Нажмите «Запустить симуляцию»")
        main_layout.addWidget(self.results_box)

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

        self.config = {}
        self.load_config()

    # --------------------------

    def load_config(self):
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                self.config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self.config = DEFAULT_CONFIG.copy()

        # подстрахуем отсутствующие ключи
        for k, v in DEFAULT_CONFIG.items():
            self.config.setdefault(k, v)

        self.update_view()

    # --------------------------

    def update_view(self):
        if not self.config:
            self.call_flow_label.setText("Конфиг не загружен")
            self.channels_label.setText("")
            self.queue_label.setText("")
            self.duration_label.setText("")
            self.policy_label.setText("")
            self.drain_label.setText("")
            self.seed_label.setText("")
            return

        self.call_flow_label.setText(f"{self.config.get('call_flow', 0)} шт/час")

        channels_text = []
        for op in self.config.get("operators", []):
            try:
                channels_text.append(
                    f"{op['type']} – μ={op['mu']} шт/час (кол-во: {op.get('count', 1)})"
                )
            except KeyError:
                channels_text.append(str(op))

        self.channels_label.setText("\n".join(channels_text) if channels_text else "—")

        self.queue_label.setText(f"{self.config.get('queue_size', 0)} шт")
        self.duration_label.setText(f"{self.config.get('duration', 0)} часов")

        self.policy_label.setText(str(self.config.get("free_server_policy", "round_robin")))
        self.drain_label.setText("Да" if bool(self.config.get("drain", True)) else "Нет")

        seed = self.config.get("seed", None)
        self.seed_label.setText("None" if seed in (None, "", "None") else str(seed))

    # --------------------------

    def open_settings(self):
        self.settings_window = SettingsWindow(self.config)

        if self.settings_window.exec():
            self.load_config()

    # --------------------------

    def run_simulation(self):
        # сбрасываем результаты
        self.results_box.clear()

        try:
            res = simulate(self.config)  # simulator.py принимает UI-конфиг напрямую
        except Exception as e:
            QMessageBox.critical(self, "Ошибка симуляции", str(e))
            return

        # Для красивого вывода утилизации по именам серверов
        try:
            servers = build_servers(self.config.get("operators", []))
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
            # fallback: просто по id
            for sid in sorted(res.server_utilization.keys()):
                lines.append(f"  Server #{sid}: {res.server_utilization[sid]:.4f}")

        self.results_box.setPlainText("\n".join(lines))