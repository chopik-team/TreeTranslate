from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget

from app.gui.widgets.brand_widget import BrandWidget
from app.gui.widgets.navigation_tabs import NavigationTabs
from app.config.paths import icon_path


class TitleBar(QWidget):
    brand_requested = Signal()
    page_changed = Signal(int)

    def __init__(self, window, parent=None) -> None:
        super().__init__(parent)
        self.window = window
        self.setFixedHeight(66)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 10, 8)
        self.brand = BrandWidget()
        self.brand.clicked.connect(self.brand_requested)
        layout.addWidget(self.brand)
        layout.addSpacing(10)
        self.tabs = NavigationTabs()
        self.tabs.page_changed.connect(self.page_changed)
        layout.addWidget(self.tabs)
        layout.addStretch()
        minimize = QPushButton(QIcon(icon_path("minus")), "", objectName="windowButton")
        minimize.clicked.connect(window.showMinimized)
        self.maximize = QPushButton(QIcon(icon_path("maximize")), "", objectName="windowButton")
        self.maximize.clicked.connect(self.toggle_maximize)
        close = QPushButton(QIcon(icon_path("close")), "", objectName="closeButton")
        close.clicked.connect(window.close)
        for button in (minimize, self.maximize, close):
            button.setFixedSize(44, 40)
            button.setIconSize(QSize(18, 18))
            layout.addWidget(button)

    def toggle_maximize(self) -> None:
        if self.window.isMaximized():
            self.window.showNormal()
            self.maximize.setIcon(QIcon(icon_path("maximize")))
        else:
            self.window.showMaximized()
            self.maximize.setIcon(QIcon(icon_path("window_restore")))

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle_maximize()

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self.window.isMaximized():
            handle = self.window.windowHandle()
            if handle:
                handle.startSystemMove()
        super().mousePressEvent(event)
