from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QLabel, QRadioButton, QToolButton, QToolTip, QVBoxLayout, QWidget

from app.config.paths import icon_path


class HoverInfoButton(QToolButton):
    """Shows help immediately and reliably on every hover."""

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        QToolTip.showText(self.mapToGlobal(self.rect().bottomRight()), self.toolTip(), self)

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        QToolTip.hideText()


class AccelerationSelector(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Ускорение", objectName="caption"))
        info = HoverInfoButton(objectName="infoButton")
        info.setIcon(QIcon(icon_path("info")))
        info.setIconSize(QSize(17, 17))
        info.setFixedSize(24, 24)
        info.setCursor(Qt.CursorShape.ArrowCursor)
        info.setToolTipDuration(30000)
        info.setToolTip(
            "<div style='width:360px'><b>Ускорение перевода</b><br><br>"
            "<b>Auto</b> — приложение оценит доступную память и само распределит "
            "вычисления между процессором и видеокартой.<br><br>"
            "<b>CPU</b> — перевод выполняется центральным процессором. Подходит, "
            "если видеокарта не поддерживается или её ресурсы нужны другим программам.<br><br>"
            "<b>GPU</b> — задействует мощности видеокарты для более сложных вычислений "
            "и ускоренной обработки крупных файлов. Для работы потребуется свободная VRAM.<br><br>"
            "Ограничить использование CPU, RAM, GPU и VRAM можно в разделе "
            "<b>Настройки → Производительность</b>. При нехватке памяти приложение сможет "
            "автоматически снизить нагрузку.<br><br>"
            "<span style='color:#91a69b'>В AW 0.2 рекомендации по распределению нагрузки "
            "носят предварительный характер и будут уточняться в следующих версиях.</span></div>"
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
