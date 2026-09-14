from PySide6.QtCore import QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QCursor, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QWidget

from app.config.paths import TREE_TRANSLATE_LOGO


class HoverLogoWidget(QWidget):
    """Renders a repeatable SVG glow without unstable graphics effects."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(47, 47)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._renderer = QSvgRenderer(str(TREE_TRANSLATE_LOGO), self)
        self._hovered = False

    def set_hovered(self, hovered: bool) -> None:
        if self._hovered == hovered:
            return
        self._hovered = hovered
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        logo_rect = QRectF(4, 4, 39, 39)
        if self._hovered:
            painter.setOpacity(0.16)
            for dx, dy in ((-3, 0), (3, 0), (0, -3), (0, 3), (-2, -2), (2, -2), (-2, 2), (2, 2)):
                self._renderer.render(painter, logo_rect.translated(dx, dy))
            painter.setOpacity(0.30)
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                self._renderer.render(painter, logo_rect.translated(dx, dy))
        painter.setOpacity(1.0)
        self._renderer.render(painter, logo_rect)


class BrandWidget(QFrame):
    clicked = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        self.logo = HoverLogoWidget()
        layout.addWidget(self.logo)
        self._hover_timer = QTimer(self, interval=40)
        self._hover_timer.timeout.connect(self.refresh_hover)
        self._hover_timer.start()

    def refresh_hover(self) -> None:
        local_position = self.mapFromGlobal(QCursor.pos())
        self.logo.set_hovered(self.isVisible() and self.rect().contains(local_position))

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.clicked.emit()
            self.refresh_hover()
            event.accept()
            return
        super().mouseReleaseEvent(event)
