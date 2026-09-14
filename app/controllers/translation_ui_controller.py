from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Slot
from PySide6.QtGui import QIcon

from app.config.paths import icon_path
from app.gui.pages.file_translation_page import FileTranslationPage
from app.gui.pages.text_translation_page import TextTranslationPage
from app.models.file_item import mock_file_tree
from app.models.translation_job import JobState
from app.services.file_picker import FilePicker
from app.services.settings_service import SettingsService
from app.services.translation_service import TranslationService
from app.services.translation_preferences import TranslationPreferences
from app.services.translation_session_manager import TranslationSessionManager
from app.config.settings import TranslationJobConfig


class TranslationUiController(QObject):
    def __init__(
        self, file_page: FileTranslationPage, text_page: TextTranslationPage,
        service: TranslationService,
        preferences: TranslationPreferences | None = None,
        sessions: TranslationSessionManager | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.file_page = file_page
        self.text_page = text_page
        self.service = service
        self.settings = SettingsService()
        self.preferences = preferences or TranslationPreferences(self.settings, self)
        self.sessions = sessions or TranslationSessionManager(parent=self)
        self._text_request_id = 0
        self.job_config = TranslationJobConfig(self.preferences.translate_directories)
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
        file_page.mode.combo.currentIndexChanged.connect(
            lambda _: self.preferences.set_profile(file_page.mode.combo.clean_mode())
        )
        for page in (file_page, text_page):
            page.languages.source_combo.currentTextChanged.connect(self._save_languages)
            page.languages.target_combo.currentTextChanged.connect(self._save_languages)
            for button in page.acceleration.group.buttons():
                button.toggled.connect(lambda checked, name=button.text(): checked and self.preferences.set_device(name))
        file_page.translate_folders.toggled.connect(self.preferences.set_translate_directories)
        self.preferences.device_changed.connect(self._apply_device)
        self.preferences.profile_changed.connect(self._apply_profile)
        self.preferences.languages_changed.connect(self._apply_languages)
        self.preferences.translate_directories_changed.connect(self._apply_translate_directories)
        self.refresh_performance_controls()

    def refresh_performance_controls(self) -> None:
        policy = self.settings.load_performance()
        self._apply_profile(self.preferences.profile)
        self._apply_device(self.preferences.device)
        self._apply_languages(self.preferences.source_language, self.preferences.target_language)
        self._apply_translate_directories(self.preferences.translate_directories)

    def _apply_profile(self, value: str) -> None:
        self.file_page.mode.combo.blockSignals(True)
        self.file_page.mode.combo.set_clean_mode(value)
        self.file_page.mode.combo.blockSignals(False)

    def _apply_device(self, value: str) -> None:
        for page in (self.file_page, self.text_page):
            page.acceleration.set_selected(value)

    def _apply_languages(self, source: str, target: str) -> None:
        for selector in (self.file_page.languages, self.text_page.languages):
            selector.source_combo.blockSignals(True)
            selector.target_combo.blockSignals(True)
            selector.source_combo.setCurrentText(source)
            selector.target_combo.setCurrentText(target)
            selector.source_combo.blockSignals(False)
            selector.target_combo.blockSignals(False)

    def _apply_translate_directories(self, enabled: bool) -> None:
        self.file_page.translate_folders.blockSignals(True)
        self.file_page.translate_folders.setChecked(enabled)
        self.file_page.translate_folders.blockSignals(False)
        self.job_config.translate_directories = enabled

    def _save_languages(self) -> None:
        sender = self.sender()
        selector = self.file_page.languages if sender in (
            self.file_page.languages.source_combo, self.file_page.languages.target_combo
        ) else self.text_page.languages
        source = selector.source_combo.currentText()
        target = selector.target_combo.currentText()
        self.preferences.set_languages(source, target)

    @Slot()
    def _start_translation(self) -> None:
        if not self.sessions.start("file"):
            return
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
        if state in {JobState.CANCELLED, JobState.COMPLETED, JobState.ERROR}:
            self.sessions.finish("file")

    @Slot(str)
    def translate_text(self, text: str) -> None:
        self._text_request_id += 1
        request_id = self._text_request_id
        if not self.sessions.start("text"):
            return
        QTimer.singleShot(0, lambda: self._complete_text_request(request_id, text))

    def _complete_text_request(self, request_id: int, text: str) -> None:
        result = self.service.translate_text(text)
        if request_id == self._text_request_id and text == self.text_page.source.editor.toPlainText():
            self.text_page.set_result(result)
        self.sessions.finish("text")

    def cancel_text_requests(self) -> None:
        self._text_request_id += 1
        self.text_page._translate_timer.stop()
        self.sessions.finish("text")
