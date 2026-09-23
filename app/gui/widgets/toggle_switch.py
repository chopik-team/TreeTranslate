from PySide6.QtCore import QAbstractAnimation, Property, QEasingCurve, QPropertyAnimation, QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QAbstractButton

from app.gui.styles.theme import color


class ToggleSwitch(QAbstractButton):
    def __init__(self, checked: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self._progress = 1.0 if checked else 0.0
        self._animation_target = self._progress
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._animation = QPropertyAnimation(self, b"progress", self)
        self._animation.setDuration(200)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(lambda _value: self.update())
        super().setChecked(checked)
        self.toggled.connect(self._animate)

    def setChecked(self, checked: bool) -> None:
        """Keep progress in sync when callers block the toggled signal."""
        super().setChecked(checked)
        if self.signalsBlocked() and hasattr(self, "_animation"):
            target = 1.0 if checked else 0.0
            # The preferences controller can echo the state changed by a user
            # click while the visual animation is still running. Keep that
            # animation when its target already matches the echoed state.
            if (self._animation.state() == QAbstractAnimation.State.Running
                    and self._animation_target == target):
                return
            self._animation.stop()
            self._animation_target = target
            self.progress = target

    def _animate(self, checked: bool) -> None:
        self._animation.stop()
        self._animation_target = 1.0 if checked else 0.0
        self._animation.setStartValue(self.progress)
        self._animation.setEndValue(self._animation_target)
        self._animation.start()

    def get_progress(self) -> float:
        return self._progress

    def set_progress(self, value: float) -> None:
        self._progress = max(0.0, min(1.0, float(value)))
        self.update()

    progress = Property(float, get_progress, set_progress)

    @staticmethod
    def _blend_color(off: QColor, on: QColor, progress: float) -> QColor:
        return QColor(
            round(off.red() + (on.red() - off.red()) * progress),
            round(off.green() + (on.green() - off.green()) * progress),
            round(off.blue() + (on.blue() - off.blue()) * progress),
        )

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        off_color = QColor(color("toggle_off"))
        on_color = QColor(color("accent"))
        painter.setBrush(self._blend_color(off_color, on_color, self.progress))
        painter.drawRoundedRect(QRectF(0, 1, 44, 22), 11, 11)
        painter.setBrush(QColor(color("text_primary")))
        left = 3.0
        right = 23.0
        x = left + (right - left) * self.progress
        painter.drawEllipse(QRectF(x, 4, 16, 16))
