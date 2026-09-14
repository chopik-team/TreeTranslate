from PySide6.QtCore import Signal
from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QWidget

from app.config.paths import icon_path


class NavigationTabs(QWidget):
    page_changed = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        for index, text in enumerate(("Перевод файлов", "Перевод текста")):
            button = QPushButton(text, objectName="navTab", checkable=True)
            button.setIcon(QIcon(icon_path("folder" if index == 0 else "edit")))
            button.setIconSize(QSize(22, 22))
            button.setChecked(index == 0)
            self.group.addButton(button, index)
            layout.addWidget(button)
        self.group.idClicked.connect(self.page_changed)

    def set_current(self, index: int) -> None:
        button = self.group.button(index)
        if button:
            button.setChecked(True)
