from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMainWindow, QMessageBox, QSizeGrip, QStackedWidget, QVBoxLayout, QWidget

from app.config.constants import APP_NAME, BOOSTY_URL, DEFAULT_WINDOW_SIZE, MINIMUM_WINDOW_SIZE
from app.controllers.navigation_controller import NavigationController
from app.controllers.translation_ui_controller import TranslationUiController
from app.gui.dialogs.about_dialog import AboutDialog
from app.gui.dialogs.changelog_dialog import ChangelogDialog
from app.gui.dialogs.settings_dialog import SettingsDialog
from app.gui.pages.file_translation_page import FileTranslationPage
from app.gui.pages.text_translation_page import TextTranslationPage
from app.gui.widgets.brand_menu import BrandMenu
from app.gui.widgets.title_bar import TitleBar
from app.services.settings_service import SettingsService
from app.services.translation_preferences import TranslationPreferences
from app.services.translation_session_manager import TranslationSessionManager
from app.services.hybrid_translation_service import HybridTranslationService


class MainWindow(QMainWindow):
    def __init__(self, translation_service=None) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(*MINIMUM_WINDOW_SIZE)
        self.resize(*DEFAULT_WINDOW_SIZE)
        root = QWidget(objectName="root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        self.title_bar = TitleBar(self)
        layout.addWidget(self.title_bar)
        self.stack = QStackedWidget()
        self.file_page = FileTranslationPage()
        self.text_page = TextTranslationPage()
        self.stack.addWidget(self.file_page)
        self.stack.addWidget(self.text_page)
        layout.addWidget(self.stack, 1)
        self.size_grip = QSizeGrip(root)
        self.size_grip.setFixedSize(18, 18)
        self.navigation = NavigationController(self.stack, self)
        self.settings = SettingsService()
        self.preferences = TranslationPreferences(self.settings, self)
        self.sessions = TranslationSessionManager(parent=self)
        self.translation_service = translation_service or HybridTranslationService(self)
        self.translation = TranslationUiController(
            self.file_page, self.text_page, self.translation_service,
            self.preferences, self.sessions, self
        )
        self.brand_menu = BrandMenu(self)
        self.title_bar.page_changed.connect(self.request_navigation)
        self.title_bar.brand_requested.connect(self.open_brand_menu)
        self.brand_menu.settings_requested.connect(self.open_settings)
        self.brand_menu.about_requested.connect(self.open_about)
        self.brand_menu.changelog_requested.connect(self.open_changelog)
        self.brand_menu.support_requested.connect(self.open_support_page)
        self.brand_menu.exit_requested.connect(self.close)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.translation.restore_unfinished_job()

    def closeEvent(self, event) -> None:
        self.text_page.shutdown()
        self.translation.cancel_text_requests()
        self.translation_service.shutdown()
        super().closeEvent(event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.size_grip.move(self.width() - self.size_grip.width() - 3, self.height() - self.size_grip.height() - 3)
        self.size_grip.raise_()

    def open_brand_menu(self) -> None:
        position = self.title_bar.brand.mapToGlobal(self.title_bar.brand.rect().bottomLeft())
        self.brand_menu.show_at(position)

    def open_settings(self) -> None:
        SettingsDialog(self, self.settings, self.preferences).exec()
        self.translation.refresh_performance_controls()
        self.translation.update_restore_preference()

    def request_navigation(self, index: int) -> None:
        current = self.stack.currentIndex()
        if index == current:
            return
        target_kind = "file" if index == 0 else "text"
        active_kind = "text" if index == 0 else "file"
        if self.sessions.is_active(active_kind) and self.sessions.conflicts_with(target_kind):
            if not self._confirm_stop_and_switch(active_kind):
                self.title_bar.tabs.set_current(current)
                return
            if active_kind == "file":
                self.translation.service.cancel()
            else:
                self.translation.cancel_text_requests()
        self.navigation.navigate(index)
        self.title_bar.tabs.set_current(index)
        if index == 0:
            self.translation.cancel_text_requests()

    def _confirm_stop_and_switch(self, active_kind: str) -> bool:
        noun = "файлов" if active_kind == "file" else "текста"
        target = "текста" if active_kind == "file" else "файлов"
        dialog = QMessageBox(self)
        dialog.setWindowTitle("Переключение режима")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText(
            f"Сейчас выполняется перевод {noun}.\n"
            f"Чтобы перейти к переводу {target}, текущую задачу необходимо остановить."
        )
        stay = dialog.addButton("Остаться", QMessageBox.ButtonRole.RejectRole)
        stop = dialog.addButton("Остановить и перейти", QMessageBox.ButtonRole.AcceptRole)
        dialog.setDefaultButton(stay)
        dialog.exec()
        return dialog.clickedButton() is stop

    def open_about(self) -> None:
        AboutDialog(self).exec()

    def open_changelog(self) -> None:
        ChangelogDialog(self).exec()

    @staticmethod
    def open_support_page() -> None:
        QDesktopServices.openUrl(QUrl(BOOSTY_URL))

    def show_placeholder(self, title: str) -> None:
        QMessageBox.information(
            self,
            title,
            "Этот раздел будет доступен в следующей версии TreeTranslate.",
        )
