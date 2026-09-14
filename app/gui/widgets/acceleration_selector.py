from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QRadioButton, QToolButton, QVBoxLayout, QWidget

from app.config.paths import icon_path


class AccelerationSelector(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Ускорение", objectName="caption"))
        info = QToolButton(objectName="infoButton")
        info.setIcon(QIcon(icon_path("info")))
        info.setIconSize(QSize(17, 17))
        info.setFixedSize(24, 24)
        info.setCursor(Qt.CursorShape.WhatsThisCursor)
        info.setToolTip(
            "<b>Ускорение перевода</b><br><br>"
            "<b>Auto</b> — приложение само выберет оптимальное устройство.<br>"
            "<b>CPU</b> — использовать центральный процессор.<br>"
            "<b>GPU</b> — использовать видеокарту, если она поддерживается.<br><br>"
            "В AW 0.2 выбор сохраняется только как параметр интерфейса."
        )
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
