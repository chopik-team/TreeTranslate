from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QSplitter, QSplitterHandle

from app.gui.styles.theme import color


class WorkspaceSplitterHandle(QSplitterHandle):
    def __init__(self, orientation: Qt.Orientation, parent: QSplitter) -> None:
        super().__init__(orientation, parent)
        self._hovered = False
        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CursorShape.SplitHCursor))

    def enterEvent(self, event) -> None:
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = QColor(color("splitter_hover") if self._hovered else color("splitter"))
        center_x = self.width() / 2
        painter.setPen(QPen(accent, 1))
        painter.drawLine(QPointF(center_x, 14), QPointF(center_x, self.height() - 14))
        grip = QRectF(center_x - 4, self.height() / 2 - 27, 8, 54)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color("splitter_grip_hover") if self._hovered else color("splitter_grip")))
        painter.drawRoundedRect(grip, 4, 4)
        painter.setBrush(accent)
        for offset in (-9, 0, 9):
            painter.drawEllipse(QPointF(center_x, self.height() / 2 + offset), 1.4, 1.4)


class WorkspaceSplitter(QSplitter):
    def createHandle(self) -> QSplitterHandle:
        return WorkspaceSplitterHandle(self.orientation(), self)
