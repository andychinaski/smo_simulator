from __future__ import annotations

from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout, QFormLayout, QFrame


def policy_label(policy: str) -> str:
    if policy == "round_robin":
        return "Очередь свободных (round-robin)"
    if policy == "fastest":
        return "Самый быстрый (fastest)"
    return str(policy)


class ModelParamsWidget(QWidget):
    """Блок отображения параметров модели (используется только на вкладке Симуляция)."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        layout = QVBoxLayout(self)

        title = QLabel("Параметры модели")
        title.setStyleSheet("font-size:14px; font-weight:bold;")
        layout.addWidget(title)

        form = QFormLayout()

        self.call_flow_label = QLabel()
        self.channels_label = QLabel()
        self.queue_label = QLabel()
        self.duration_label = QLabel()
        self.policy_label = QLabel()
        self.drain_label = QLabel()
        self.seed_label = QLabel()
        self.start_at_zero_label = QLabel()
        self.max_arrivals_label = QLabel()

        self.channels_label.setWordWrap(True)

        form.addRow("Интенсивность (λ):", self.call_flow_label)
        form.addRow("Каналы:", self.channels_label)
        form.addRow("Размер очереди:", self.queue_label)
        form.addRow("Продолжительность:", self.duration_label)
        form.addRow("Политика свободных серверов:", self.policy_label)
        form.addRow("Drain (доработать хвост):", self.drain_label)
        form.addRow("Seed:", self.seed_label)
        form.addRow("Первая заявка в t=0:", self.start_at_zero_label)
        form.addRow("Max arrivals:", self.max_arrivals_label)

        layout.addLayout(form)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

    def update_view(self, config: dict):
        if not config:
            self.call_flow_label.setText("Конфиг не загружен")
            self.channels_label.setText("")
            self.queue_label.setText("")
            self.duration_label.setText("")
            self.policy_label.setText("")
            self.drain_label.setText("")
            self.seed_label.setText("")
            self.start_at_zero_label.setText("")
            self.max_arrivals_label.setText("")
            return

        self.call_flow_label.setText(f"{config.get('call_flow', 0)} шт/час")

        channels_text = []
        for op in config.get("operators", []):
            try:
                channels_text.append(
                    f"{op['type']} – μ={op['mu']} шт/час (кол-во: {op.get('count', 1)})"
                )
            except Exception:
                channels_text.append(str(op))

        self.channels_label.setText("\n".join(channels_text) if channels_text else "—")
        self.queue_label.setText(f"{config.get('queue_size', 0)} шт")
        self.duration_label.setText(f"{config.get('duration', 0)} часов")

        policy = str(config.get("free_server_policy", "round_robin"))
        self.policy_label.setText(policy_label(policy))

        self.drain_label.setText("Да" if bool(config.get("drain", True)) else "Нет")

        seed = config.get("seed", None)
        self.seed_label.setText("None" if seed in (None, "", "None") else str(seed))

        self.start_at_zero_label.setText("Да" if bool(config.get("start_at_zero", True)) else "Нет")

        max_arrivals = config.get("max_arrivals", None)
        self.max_arrivals_label.setText("None" if max_arrivals in (None, "", "None") else str(max_arrivals))