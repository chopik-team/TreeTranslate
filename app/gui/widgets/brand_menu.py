from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout

from app.config.paths import icon_path


class BrandMenu(QFrame):
    settings_requested = Signal()
    about_requested = Signal()
    changelog_requested = Signal()
    support_requested = Signal()
    exit_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("panel")
        self.setFixedWidth(235)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        actions = (
            ("settings", "Настройки", self.settings_requested),
            ("info", "О проекте", self.about_requested),
            ("clock", "История изменений", self.changelog_requested),
            ("plus", "Поддержать TreeTranslate", self.support_requested),
        )
        for icon, text, signal in actions:
            button = QPushButton(QIcon(icon_path(icon)), text)
            button.setStyleSheet("text-align:left")
            button.clicked.connect(signal)
            button.clicked.connect(self.close)
            layout.addWidget(button)
        separator = QFrame()
        separator.setFixedHeight(1)
        separator.setStyleSheet("background: #26352d; border: 0")
        layout.addWidget(separator)
        exit_button = QPushButton(QIcon(icon_path("close")), "Выход")
        exit_button.setObjectName("danger")
        exit_button.setStyleSheet("text-align:left")
        exit_button.clicked.connect(self.exit_requested)
        exit_button.clicked.connect(self.close)
        layout.addWidget(exit_button)
        self._animation = QPropertyAnimation(self, b"windowOpacity", self, duration=130)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def show_at(self, position) -> None:
        self.move(position)
        self.setWindowOpacity(0.0)
        self.show()
        self._animation.stop()
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.start()
