from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QRadioButton, QVBoxLayout, QWidget


class AccelerationSelector(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Ускорение", objectName="caption"))
        info = QLabel("ⓘ")
        info.setToolTip("Режим выбирается только для демонстрации интерфейса")
        title_row.addWidget(info)
        title_row.addStretch()
        layout.addLayout(title_row)
        options = QHBoxLayout()
        options.setSpacing(14)
        self.group = QButtonGroup(self)
        for name in ("Auto", "CPU", "GPU"):
            radio = QRadioButton(name)
            radio.setMinimumWidth(64)
            radio.setMinimumHeight(24)
            radio.setChecked(name == "Auto")
            self.group.addButton(radio)
            options.addWidget(radio)
        options.addStretch()
        layout.addLayout(options)

    def selected(self) -> str:
        button = self.group.checkedButton()
        return button.text() if button else "Auto"
