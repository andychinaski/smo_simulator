from PySide6.QtWidgets import (
    QWidget,
    QLineEdit,
    QSpinBox,
    QPushButton,
    QHBoxLayout
)

class OperatorRow(QWidget):

    def __init__(self):
        super().__init__()

        layout = QHBoxLayout()

        # тип оператора
        self.type_input = QLineEdit()
        self.type_input.setPlaceholderText("Тип")

        # скорость обслуживания
        self.mu_input = QSpinBox()
        self.mu_input.setRange(1, 100000)
        self.mu_input.setSuffix(" шт/час")

        # количество операторов
        self.count_input = QSpinBox()
        self.count_input.setRange(1, 1000)

        # кнопка удаления
        self.delete_button = QPushButton("✕")
        self.delete_button.setFixedWidth(30)
        self.delete_button.clicked.connect(self.delete_self)

        layout.addWidget(self.type_input)
        layout.addWidget(self.mu_input)
        layout.addWidget(self.count_input)
        layout.addWidget(self.delete_button)

        layout.setContentsMargins(0, 0, 0, 0)

        self.setLayout(layout)

    # --------------------------

    def delete_self(self):
        self.setParent(None)
        self.deleteLater()

    # --------------------------

    def get_data(self):

        return {
            "type": self.type_input.text(),
            "mu": self.mu_input.value(),
            "count": self.count_input.value()
        }

    # --------------------------

    def set_data(self, data):

        self.type_input.setText(data.get("type", ""))
        self.mu_input.setValue(data.get("mu", 1))
        self.count_input.setValue(data.get("count", 1))