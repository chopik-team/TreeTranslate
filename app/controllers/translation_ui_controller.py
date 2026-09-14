from pathlib import Path

from PySide6.QtCore import QObject, Slot
from PySide6.QtGui import QIcon

from app.config.paths import icon_path
from app.gui.pages.file_translation_page import FileTranslationPage
from app.gui.pages.text_translation_page import TextTranslationPage
from app.models.file_item import mock_file_tree
from app.models.translation_job import JobState
from app.services.file_picker import FilePicker
from app.services.mock_translation_service import MockTranslationService
from app.services.settings_service import SettingsService


class TranslationUiController(QObject):
    def __init__(self, file_page: FileTranslationPage, text_page: TextTranslationPage, parent=None) -> None:
        super().__init__(parent)
        self.file_page = file_page
        self.text_page = text_page
        self.service = MockTranslationService(self)
        self.settings = SettingsService()
        self._source_name = "Документация проект.zip"
        file_page.drop_zone.paths_dropped.connect(self.accept_paths)
        file_page.drop_zone.browse_files_requested.connect(self.choose_files)
        file_page.drop_zone.browse_folder_requested.connect(self.choose_folder)
        file_page.start_requested.connect(self._start_translation)
        file_page.progress.pause_requested.connect(self.service.pause_or_resume)
        file_page.progress.cancel_requested.connect(self.service.cancel)
        text_page.translate_requested.connect(self.translate_text)
        self.service.state_changed.connect(self._state_changed)
        self.service.progress_changed.connect(file_page.progress.set_progress)
        self.service.scan_finished.connect(self._show_tree)
        file_page.mode.combo.currentIndexChanged.connect(lambda _: self._save_main_mode())
        self.refresh_performance_controls()

    def refresh_performance_controls(self) -> None:
        policy = self.settings.load_performance()
        self.file_page.mode.combo.blockSignals(True)
        self.file_page.mode.combo.set_clean_mode(policy.mode)
        self.file_page.mode.combo.blockSignals(False)

    def _save_main_mode(self) -> None:
        self.settings.save_value("performance/mode", self.file_page.mode.combo.clean_mode())

    @Slot()
    def _start_translation(self) -> None:
        self.service.configure(self.settings.load_performance())
        self.service.start()

    @Slot()
    def choose_files(self) -> None:
        paths = FilePicker.choose_files(self.file_page)
        if paths:
            self.accept_paths(paths)

    @Slot()
    def choose_folder(self) -> None:
        path = FilePicker.choose_folder(self.file_page)
        if path:
            self.accept_paths([path])

    @Slot(list)
    def accept_paths(self, paths: list[Path]) -> None:
        self._source_name = paths[0].name if len(paths) == 1 else f"Выбрано файлов: {len(paths)}"
        self.service.scan()

    def _show_tree(self) -> None:
        self.file_page.file_tree.populate(mock_file_tree(self._source_name))
        self.file_page.progress.set_progress(self.service.progress)

    def _state_changed(self, state: JobState) -> None:
        self.file_page.progress.set_state(state)
        self.file_page.start_button.setEnabled(state in {JobState.READY, JobState.COMPLETED, JobState.CANCELLED, JobState.ERROR})
        restart = state in {JobState.COMPLETED, JobState.CANCELLED, JobState.ERROR}
        self.file_page.start_button.setText("  Запустить снова" if restart else "  Начать перевод")
        self.file_page.start_button.setIcon(QIcon(icon_path("refresh" if restart else "play")))

    @Slot(str)
    def translate_text(self, text: str) -> None:
        self.text_page.set_result(self.service.mock_translate_text(text))
