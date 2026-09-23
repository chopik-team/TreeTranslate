from PIL import Image
from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtGui import QIcon, QImage, QPainter, QPixmap

from app.config.paths import ICONS_DIR


class AnimatedIcon(QObject):
    """Small APNG icon shared by existing Qt actions and tree items."""

    changed = Signal(QIcon)

    def __init__(self, name: str, parent=None, size: int = 24):
        super().__init__(parent)
        self.frames = []
        self.durations = []
        with Image.open(ICONS_DIR / f"animated-{name}.png") as source:
            for index in range(source.n_frames):
                source.seek(index)
                rgba = source.convert("RGBA")
                image = QImage(rgba.tobytes(), rgba.width, rgba.height,
                               QImage.Format.Format_RGBA8888).copy()
                pixmap = QPixmap.fromImage(image).scaled(
                    size, size, Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation)
                painter = QPainter(pixmap)
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
                painter.fillRect(pixmap.rect(), Qt.GlobalColor.white)
                painter.end()
                self.frames.append(QIcon(pixmap))
                self.durations.append(max(20, int(source.info.get("duration", 80))))
        self.index = 0
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._advance)

    @property
    def icon(self):
        return self.frames[self.index]

    def start(self):
        if not self.timer.isActive():
            self.timer.start(self.durations[self.index])

    def stop(self):
        self.timer.stop()
        self.index = 0
        self.changed.emit(self.icon)

    def _advance(self):
        self.index = (self.index + 1) % len(self.frames)
        self.changed.emit(self.icon)
        self.timer.start(self.durations[self.index])
