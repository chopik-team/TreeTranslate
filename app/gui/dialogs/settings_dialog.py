from __future__ import annotations

from collections.abc import Iterable
import os

from PySide6.QtCore import QSize, Qt, QObject, Signal
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QListWidget, QPushButton, QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget,
)

from app.gui.widgets.language_combo import language_icon
from app.services.settings_service import SettingsService
from app.services.hardware_profile_service import HardwareProfileService
from app.gui.styles.theme_manager import ThemeManager
from app.services.translation_preferences import TranslationPreferences

from app.localization.widgets import QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QLabel, QListWidget, QPushButton


class HardwareDetection(QObject):
    completed = Signal(object, bool)

    def run(self):
        from app.engine.runtime.device_manager import DeviceManager
        service = HardwareProfileService()
        hardware = service.detect()
        try:
            service.save(hardware)
        except OSError:
            pass  # A read-only settings folder does not invalidate hardware detection.
        self.completed.emit(hardware, DeviceManager().gpu_available())


class SettingsDialog(QDialog):
    SECTIONS = ("Общие", "Язык", "Производительность", "Интерфейс")

    def __init__(
        self, parent=None, settings: SettingsService | None = None,
        preferences: TranslationPreferences | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings or SettingsService()
        self.preferences = preferences or TranslationPreferences(self.settings, self)
        from app.localization import localization, saved_locale
        localization.use(saved_locale(self.settings))
        self.setWindowTitle("Настройки TreeTranslate")
        self.setMinimumSize(900, 620)
        self.resize(980, 690)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.addWidget(QLabel("Настройки", objectName="heading"))
        content = QHBoxLayout()
        content.setSpacing(22)
        self.sections = QListWidget(objectName="settingsNav")
        self.sections.setFixedWidth(205)
        self.sections.addItems(self.SECTIONS)
        self.pages = QStackedWidget()
        builders = (self._general_page, self._language_page, self._performance_page, self._interface_page)
        for builder in builders:
            self.pages.addWidget(self._scrollable(builder()))
        self.sections.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.sections.setCurrentRow(0)
        content.addWidget(self.sections)
        content.addWidget(self.pages, 1)
        root.addLayout(content, 1)
        footer = QHBoxLayout()
        footer.addWidget(QLabel("Изменения сохраняются автоматически", objectName="secondary"))
        footer.addStretch()
        close = QPushButton("Готово")
        close.clicked.connect(self.accept)
        footer.addWidget(close)
        root.addLayout(footer)

    @staticmethod
    def _scrollable(page: QWidget) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(page)
        return scroll

    @staticmethod
    def _page(title: str, description: str) -> tuple[QWidget, QVBoxLayout, QFormLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(4, 2, 14, 12)
        layout.setSpacing(13)
        layout.addWidget(QLabel(title, objectName="heading"))
        description_label = QLabel(description, objectName="secondary")
        description_label.setWordWrap(True)
        layout.addWidget(description_label)
        form = QFormLayout()
        form.setHorizontalSpacing(30)
        form.setVerticalSpacing(12)
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.addLayout(form)
        return page, layout, form

    def _combo(self, key: str, default: str, options: Iterable[str]) -> QComboBox:
        combo = QComboBox()
        combo.addItems(list(options))
        combo.setCurrentText(str(self.settings.value(key, default)))
        combo.currentTextChanged.connect(lambda value, k=key: self.settings.save_value(k, value))
        return combo

    def _check(self, key: str, text: str, default: bool) -> QCheckBox:
        check = QCheckBox(text)
        check.setChecked(self.settings.value(key, default, bool))
        check.toggled.connect(lambda value, k=key: self.settings.save_value(k, value))
        return check

    @staticmethod
    def _add_checks(layout: QVBoxLayout, checks: Iterable[QCheckBox]) -> None:
        for check in checks:
            layout.addWidget(check)

    def _general_page(self) -> QWidget:
        page, layout, form = self._page("Общие", "Основное поведение приложения и сохранение результатов.")
        output_location = QComboBox(objectName="outputLocation")
        mode, saved_path = self.settings.output_location()
        output_location.addItem("Рядом с оригиналом", "near_original")
        if saved_path:
            output_location.addItem(saved_path, "custom")
        output_location.setCurrentIndex(1 if mode == "custom" and saved_path else 0)
        change_output = QPushButton("Изменить…", objectName="changeOutputLocation")

        def select_output_mode(index: int) -> None:
            self.settings.save_value("general/output_location", output_location.itemData(index))

        def choose_output_location() -> None:
            current_path = str(self.settings.value("general/output_path", ""))
            selected_path = QFileDialog.getExistingDirectory(self, "Выберите папку сохранения", current_path)
            if selected_path:
                self.settings.save_value("general/output_location", "custom")
                self.settings.save_value("general/output_path", selected_path)
                custom_index = output_location.findData("custom")
                if custom_index < 0:
                    output_location.addItem(selected_path, "custom")
                    custom_index = output_location.count() - 1
                else:
                    output_location.setItemText(custom_index, selected_path)
                output_location.setCurrentIndex(custom_index)
                output_location.setToolTip(selected_path)

        output_location.currentIndexChanged.connect(select_output_mode)
        change_output.clicked.connect(choose_output_location)
        output_row = QHBoxLayout()
        output_row.addWidget(output_location, 1)
        output_row.addWidget(change_output)
        form.addRow("Папка сохранения", output_row)
        naming = QComboBox(objectName="outputNamingMode")
        naming.addItems(("Добавить язык к имени", "Оставить как в оригинале"))
        saved_template = str(self.settings.value("general/output_template", "{name}_{lang}"))
        naming.setCurrentIndex(1 if saved_template == "{name}" else 0)
        preview = QLabel(objectName="secondary")
        def update_naming_mode(value: str) -> None:
            add_language = value == "Добавить язык к имени"
            self.settings.save_value("general/output_template", "{name}_{lang}" if add_language else "{name}")
            preview.setText("Пример: Manual_RU" if add_language else "Пример: Manual")
        naming.currentIndexChanged.connect(lambda: update_naming_mode(naming.currentText()))
        update_naming_mode(naming.currentText())
        naming_box = QVBoxLayout()
        naming_box.addWidget(naming)
        naming_box.addWidget(preview)
        form.addRow("Название выходной папки", naming_box)
        layout.addSpacing(4)
        safety = QLabel("🔒  Оригинальные файлы всегда сохраняются", objectName="safetyNotice")
        layout.addWidget(safety)
        restore_job = self._check(
            "general/restore_job", "Восстанавливать незавершённую задачу после запуска", False
        )
        restore_job.toggled.connect(
            lambda enabled: None if enabled else self.settings.clear_unfinished_job()
        )
        self._add_checks(layout, [
            self._check("general/open_output", "Открывать папку после завершения", False),
            self._check("general/remember_language", "Запоминать последний выбранный язык", True),
            restore_job,
        ])
        layout.addStretch()
        return page

    def _language_page(self) -> QWidget:
        page, layout, _ = self._page(
            "Язык интерфейса",
            "Выберите язык приложения. Изменения применяются сразу.",
        )
        languages = (
            "Русский",
            "English (US)",
            "English (UK)",
            "Deutsch",
            "Español",
            "Français",
            "中文",
            "日本語",
        )
        from app.localization import LOCALES, localization, saved_locale
        selected_language = LOCALES[saved_locale(self.settings)]
        self.language_group = QButtonGroup(self)
        self.language_group.setExclusive(True)
        for language in languages:
            button = QPushButton(language, objectName="languageChoice")
            button.setIcon(language_icon(language))
            button.setIconSize(QSize(24, 17))
            button.setCheckable(True)
            button.setChecked(language == selected_language)
            button.setMinimumHeight(44)
            button.setProperty("language", language)
            button.clicked.connect(
                lambda checked, value=language: checked and self._change_locale(value)
            )
            self.language_group.addButton(button)
            layout.addWidget(button)
        if not self.language_group.checkedButton():
            self.language_group.buttons()[0].setChecked(True)
        layout.addStretch()
        return page

    def _change_locale(self, label):
        from app.localization import LOCALES, localization
        locale = next(key for key,value in LOCALES.items() if value == label)
        self.settings.save_value('general/ui_language', locale)
        self.settings.sync()
        localization.use(locale)

    def _performance_page(self) -> QWidget:
        page, layout, form = self._page(
            "Производительность",
            "Auto выбирает подходящее устройство. CPU и GPU задают устройство явно.",
        )
        self.device_combo = self._combo("performance/device", self.preferences.device, ["Auto", "CPU", "GPU"])
        self.device_combo.currentTextChanged.connect(self.preferences.set_device)
        self.preferences.device_changed.connect(self._set_device)
        form.addRow("Устройство обработки", self.device_combo)
        self.hardware_value = QLabel("Нажмите «Определить оборудование»", objectName="hardwareValue")
        self.hardware_value.setWordWrap(True)
        form.addRow("Оборудование", self.hardware_value)
        detect = self.detect_button = QPushButton("Определить оборудование", objectName="hardwareDetection")
        detect.clicked.connect(self._show_hardware_recommendation)
        layout.addWidget(detect, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addStretch()
        saved = HardwareProfileService().load()
        if saved:
            self._display_hardware_profile(saved)
        return page

    def _set_device(self, value):
        self.device_combo.setCurrentText(value)

    def _show_hardware_recommendation(self):
        from threading import Thread
        self.detect_button.setEnabled(False)
        worker = self._hardware_worker = HardwareDetection()
        worker.completed.connect(self._hardware_detected)
        Thread(target=worker.run, daemon=True, name='hardware-detection').start()

    def _hardware_detected(self, hardware, available):
        self.detect_button.setEnabled(True)
        self._display_hardware_profile(hardware, available)

    def _display_hardware_profile(self, hardware, cuda_available=None):
        ram = str(hardware.ram_gb) + " GB" if hardware.ram_gb else "Не определено"
        vram = str(hardware.vram_gb) + " GB" if hardware.vram_gb else "Не определено"
        cores = hardware.logical_cores or 'Не определено'
        from app.engine.runtime.device_manager import DeviceManager
        available = "Доступно" if (DeviceManager().gpu_available() if cuda_available is None else cuda_available) else "Недоступно"
        self.hardware_value.setText(
            f"CPU: {hardware.cpu}\nЛогических потоков: {cores}\nRAM: {ram}\n"
            f"GPU: {hardware.gpu}\nVRAM: {vram}\nCUDA: {available}")

    def _interface_page(self) -> QWidget:
        page, layout, form = self._page("Интерфейс", "Внешний вид и отображение прогресса.")
        self._add_checks(layout, [
            self._check("interface/eta", "Показывать расчёт оставшегося времени", True),
            self._check("interface/detailed_progress", "Показывать подробный прогресс", True),
        ])
        layout.addStretch()
        return page
