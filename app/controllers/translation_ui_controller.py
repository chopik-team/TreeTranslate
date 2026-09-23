from pathlib import Path
from dataclasses import replace

from PySide6.QtCore import QDir, QObject, QProcess, QUrl, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtGui import QIcon

from app.config.paths import icon_path
from app.gui.pages.file_translation_page import FileTranslationPage
from app.gui.pages.text_translation_page import TextTranslationPage
from app.models.file_item import FileItem, mock_file_tree
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
        self.preferences = preferences or TranslationPreferences(SettingsService(), self)
        self.settings = self.preferences.settings
        self.sessions = sessions or TranslationSessionManager(parent=self)
        self._text_request_id = 0
        self._source_paths: tuple[Path, ...] = ()
        self._restoring_job = False
        self._restore_attempted = False
        self.job_config = TranslationJobConfig(
            translate_directories=self.preferences.translate_directories,
            translate_filenames=self.preferences.translate_filenames,
        )
        self._source_name = "Документация проект.zip"
        file_page.drop_zone.paths_dropped.connect(self.accept_paths)
        file_page.drop_zone.browse_files_requested.connect(self.choose_files)
        file_page.drop_zone.browse_folder_requested.connect(self.choose_folder)
        file_page.start_requested.connect(self._start_translation)
        file_page.progress.pause_requested.connect(self.service.pause_or_resume)
        file_page.progress.cancel_requested.connect(self.service.cancel)
        file_page.progress.show_output_requested.connect(self._show_output)
        file_page.progress.open_file_requested.connect(self._open_file)
        if getattr(service, 'real_files', False):
            service.files.failed.connect(file_page.file_status.setText)
            service.files.notice.connect(file_page.file_status.setText)
        text_page.translate_requested.connect(self.translate_text)
        text_page.variant_chosen.connect(self._use_dictionary_variant)
        self.service.state_changed.connect(self._state_changed)
        self.service.progress_changed.connect(file_page.progress.set_progress)
        self.service.file_outputs_ready.connect(file_page.progress.set_output_paths)
        self.service.scan_finished.connect(self._show_tree)
        self.service.text_completed.connect(self._text_completed)
        self.service.text_failed.connect(self._text_failed)
        self.service.text_busy_changed.connect(self._text_busy_changed)
        text_page.source.editor.textChanged.connect(self._invalidate_text)
        for page in (file_page, text_page):
            page.mode.combo.currentIndexChanged.connect(
                lambda _, combo=page.mode.combo: self.preferences.set_profile(combo.clean_mode())
            )
        for page in (file_page, text_page):
            page.languages.source_combo.currentTextChanged.connect(self._save_languages)
            page.languages.target_combo.currentTextChanged.connect(self._save_languages)
            page.languages.languages_swapped.connect(self.preferences.set_languages)
            for button in page.acceleration.group.buttons():
                button.toggled.connect(lambda checked, name=button.text(): checked and self.preferences.set_device(name))
        file_page.translate_folders.toggled.connect(self.preferences.set_translate_directories)
        file_page.translate_filenames.toggled.connect(self.preferences.set_translate_filenames)
        self.preferences.device_changed.connect(self._apply_device)
        self.preferences.profile_changed.connect(self._apply_profile)
        self.preferences.languages_changed.connect(self._apply_languages)
        self.preferences.translate_directories_changed.connect(self._apply_translate_directories)
        self.preferences.translate_filenames_changed.connect(self._apply_translate_filenames)
        self.refresh_performance_controls()
        self.preferences.device_changed.connect(self._retranslate)
        self.preferences.profile_changed.connect(self._retranslate)
        self.preferences.languages_changed.connect(self._retranslate)

    def refresh_performance_controls(self) -> None:
        self._apply_profile(self.preferences.profile)
        self._apply_device(self.preferences.device)
        self._apply_languages(self.preferences.source_language, self.preferences.target_language)
        self._apply_translate_directories(self.preferences.translate_directories)
        self._apply_translate_filenames(self.preferences.translate_filenames)

    def _apply_profile(self, value: str) -> None:
        for page in (self.file_page, self.text_page):
            page.mode.combo.blockSignals(True)
            page.mode.combo.set_clean_mode(value)
            page.mode.combo.blockSignals(False)

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
        self.text_page.refresh_assistance()

    def _apply_translate_directories(self, enabled: bool) -> None:
        # Avoid echoing a user's already-applied click into ToggleSwitch while
        # its thumb is animating toward the same target.
        if self.file_page.translate_folders.isChecked() == enabled:
            self.job_config.translate_directories = enabled
            return
        self.file_page.translate_folders.blockSignals(True)
        self.file_page.translate_folders.setChecked(enabled)
        self.file_page.translate_folders.blockSignals(False)
        self.job_config.translate_directories = enabled

    def _apply_translate_filenames(self, enabled: bool) -> None:
        if self.file_page.translate_filenames.isChecked() == enabled:
            self.job_config.translate_filenames = enabled
            return
        self.file_page.translate_filenames.blockSignals(True)
        self.file_page.translate_filenames.setChecked(enabled)
        self.file_page.translate_filenames.blockSignals(False)
        self.job_config.translate_filenames = enabled

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
        if self.settings.restore_job_enabled() and self._source_paths:
            self.settings.save_unfinished_job(self._source_paths)
        self.file_page.progress.set_output_paths(())
        self.service.configure(self.settings.load_performance())
        if getattr(self.service, 'real_files', False):
            from app.documents.job import DocumentConfig
            from app.engine.types import DevicePreference, PerformanceProfile
            from app.services.hybrid_translation_service import PROFILE_NAMES
            selected = set(self.file_page.file_tree.selected_paths())
            self.service.files.selected = tuple(f for f in self.service.files.scan_result.files if f.path in selected)
            mode, path = self.settings.output_location()
            policy = self.settings.load_performance()
            self.service.files.config = DocumentConfig(
                self.preferences.source_language, self.preferences.target_language,
                DevicePreference(self.preferences.device.lower()),
                PROFILE_NAMES.get(self.preferences.profile, PerformanceProfile.AUTOMATIC),
                int(policy.cpu_threads) if policy.cpu_threads.isdigit() else None,
                Path(path) if mode == 'custom' and path else None,
                str(self.settings.value('general/output_template', '{name}_{lang}')),
                self.preferences.translate_directories,
                self.preferences.translate_filenames)
            self.file_page.file_status.setText('Перевод DOCX/PDF · Оригиналы сохраняются')
        self.service.start()

    def _open_file(self):
        paths = self.file_page.progress.output_paths
        if paths and paths[-1].is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths[-1].resolve())))

    @Slot()
    def _show_output(self) -> None:
        paths = self.file_page.progress.output_paths
        if not paths:
            return
        if len(paths) == 1 and paths[0].is_file():
            QProcess.startDetached(
                "explorer.exe",
                ["/select,", QDir.toNativeSeparators(str(paths[0].resolve()))],
            )
            return
        location = paths[0] if paths[0].is_dir() else paths[0].parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(location.resolve())))

    def _open_output_directory(self) -> None:
        paths = self.file_page.progress.output_paths
        if not paths:
            return
        location = paths[-1] if paths[-1].is_dir() else paths[-1].parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(location.resolve())))

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
        if not paths:
            return
        if getattr(self.service, 'real_files', False):
            if self.service.files.busy or not self.sessions.start('file'):
                return
        if not self._restoring_job:
            self._restore_attempted = True
        self._source_paths = tuple(Path(path).resolve() for path in paths)
        if self.settings.restore_job_enabled():
            self.settings.save_unfinished_job(self._source_paths)
        else:
            self.settings.clear_unfinished_job()
        if getattr(self.service, 'real_files', False):
            self.file_page.progress.set_output_paths(())
            self.service.scan(paths)
            return
        self._source_name = paths[0].name if len(paths) == 1 else f"Выбрано файлов: {len(paths)}"
        self.file_page.progress.set_output_paths(())
        self.service.scan()

    def restore_unfinished_job(self) -> None:
        if self._restore_attempted or self._source_paths:
            return
        self._restore_attempted = True
        if not getattr(self.service, 'real_files', False) or self.service.files.busy:
            return
        paths = self.settings.unfinished_job_paths()
        if not paths:
            if self.settings.value("job/unfinished", False, bool):
                self.settings.clear_unfinished_job()
            return
        self._restoring_job = True
        self.file_page.file_status.setText("Восстановление незавершённой задачи…")
        self.accept_paths(list(paths))

    def update_restore_preference(self) -> None:
        unfinished = self.service.state not in {JobState.COMPLETED, JobState.CANCELLED}
        if self.settings.restore_job_enabled() and self._source_paths and unfinished:
            self.settings.save_unfinished_job(self._source_paths)
        else:
            self.settings.clear_unfinished_job()

    def _show_tree(self) -> None:
        if getattr(self.service, 'real_files', False):
            result = self.service.files.scan_result
            root = FileItem('Выбранные документы', True)
            folders = {}
            for source in result.files:
                parent = root
                if source.root:
                    parts = (source.root.name,) + source.relative.parts[:-1]
                    key = str(source.root)
                    for part in parts:
                        key += '/' + part
                        if key not in folders:
                            folders[key] = FileItem(part, True)
                            parent.children.append(folders[key])
                        parent = folders[key]
                parent.children.append(FileItem(source.path.name, path=str(source.path)))
            self.file_page.file_tree.populate(root)
            self.file_page.start_button.setEnabled(bool(result.files))
            extensions = {source.path.suffix.lower() for source in result.files}
            formats = "/".join(name for name in ("DOCX", "PDF") if f".{name.lower()}" in extensions)
            found = f"Найдено {formats}: {len(result.files)}" if formats else "Найдено: 0"
            self.file_page.file_status.setText(
                f'{found}. Пропущено: {len(result.skipped)}. Формат пока не поддерживается для других файлов.'
                if result.skipped else f'{found}. Оригиналы сохраняются.')
            if self._restoring_job:
                self._restoring_job = False
                self.file_page.file_status.setText(
                    f"Задача восстановлена. {found}. Нажмите «Начать перевод»."
                )
            return
        self.file_page.file_tree.populate(mock_file_tree(self._source_name))
        self.file_page.progress.set_progress(self.service.progress)

    def _state_changed(self, state: JobState) -> None:
        busy = state in {JobState.SCANNING, JobState.TRANSLATING, JobState.PAUSED, JobState.CANCELLING}
        for widget in (self.file_page.drop_zone, self.file_page.file_tree, self.file_page.languages,
                       self.file_page.mode, self.file_page.acceleration, self.file_page.translate_folders,
                       self.file_page.translate_filenames):
            widget.setEnabled(not busy)
        self.file_page.progress.set_state(state)
        self.file_page.start_button.setEnabled(state in {JobState.READY, JobState.COMPLETED, JobState.CANCELLED, JobState.ERROR})
        restart = state in {JobState.COMPLETED, JobState.CANCELLED, JobState.ERROR}
        self.file_page.start_button.setText("  Запустить снова" if restart else "  Начать перевод")
        self.file_page.start_button.setIcon(QIcon(icon_path("refresh" if restart else "play")))
        if state in {JobState.READY, JobState.CANCELLED, JobState.COMPLETED, JobState.ERROR}:
            self.sessions.finish("file")
        if state is JobState.COMPLETED or (
            state is JobState.CANCELLED and not getattr(self.service, '_closed', False)
        ):
            self.settings.clear_unfinished_job()
        if state is JobState.COMPLETED and self.settings.value("general/open_output", False, bool):
            self._open_output_directory()

    @Slot(str)
    def translate_text(self, text: str) -> None:
        self._text_request_id += 1
        request_id = self._text_request_id
        if not self.sessions.start("text"):
            self.text_page.set_status("Дождитесь завершения перевода файлов.")
            return
        policy = replace(self.settings.load_performance(), device=self.preferences.device, mode=self.preferences.profile)
        self.text_page.set_status("Подготовка локального перевода…")
        self.service.submit_text(text, self.preferences.source_language, self.preferences.target_language,
                                 policy, str(request_id))

    def _text_completed(self, result) -> None:
        if result.request_id == str(self._text_request_id):
            self.text_page.set_resolved_languages(result.source_language, result.target_language)
            self.text_page.set_result(result.translated_text)
            suffix = " · резервный маршрут" if result.fallback_used else ""
            self.text_page.set_status(f"{result.backend} · {result.device.upper()} · {result.duration_ms:.0f} мс{suffix}")

    def _text_failed(self, request_id: str, message: str) -> None:
        if request_id == str(self._text_request_id):
            self.text_page.set_status(message)

    def _use_dictionary_variant(self, text: str) -> None:
        self.cancel_text_requests()
        self.text_page.set_result(text)
        self.text_page.set_status("Выбран словарный вариант")

    def _text_busy_changed(self, busy: bool) -> None:
        if not busy:
            self.sessions.finish("text")

    def _invalidate_text(self) -> None:
        self._text_request_id += 1
        self.service.cancel_text()
        self.text_page.result.editor.clear()
        self.text_page.set_status("")

    def _retranslate(self, *_args) -> None:
        self._invalidate_text()
        if self.text_page.source.editor.toPlainText().strip():
            self.text_page._translate_timer.start()

    def cancel_text_requests(self) -> None:
        self._text_request_id += 1
        self.text_page._translate_timer.stop()
        self.service.cancel_text()
        if not self.service.text_busy:
            self.sessions.finish("text")
