from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from app.config.constants import APP_NAME, ORGANIZATION_NAME
from app.gui.main_window import MainWindow
from app.gui.styles.theme import load_stylesheet


class TreeTranslateApplication:
    def __init__(self) -> None:
        self.qt_app = QApplication.instance() or QApplication(sys.argv)
        self.qt_app.setApplicationName(APP_NAME)
        self.qt_app.setOrganizationName(ORGANIZATION_NAME)
        self.qt_app.setStyleSheet(load_stylesheet())
        self.window = MainWindow()

    def run(self) -> int:
        self.window.show()
        return self.qt_app.exec()
