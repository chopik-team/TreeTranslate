from PySide6.QtCore import QObject, Slot
from PySide6.QtWidgets import QStackedWidget


class NavigationController(QObject):
    def __init__(self, stack: QStackedWidget, parent=None) -> None:
        super().__init__(parent)
        self.stack = stack

    @Slot(int)
    def navigate(self, index: int) -> None:
        if 0 <= index < self.stack.count():
            self.stack.setCurrentIndex(index)
