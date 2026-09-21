from __future__ import annotations

from collections.abc import Iterable
import os

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel,
    QListWidget, QPushButton, QScrollArea,
    QStackedWidget, QVBoxLayout, QWidget,
)

from app.gui.widgets.language_combo import language_icon
from app.gui.widgets.translation_mode import ModeRequirementsCombo
from app.services.settings_service import SettingsService
from app.services.hardware_profile_service import HardwareProfileService
from app.gui.styles.theme_manager import ThemeManager
from app.services.translation_preferences import TranslationPreferences


class SettingsDialog(QDialog):
    SECTIONS = ("Общие", "Язык", "Производительность", "Интерфейс")

    def __init__(
        self, parent=None, settings: SettingsService | None = None,
        preferences: TranslationPreferences | None = None,
    ) -> None:
        super().__init__(parent)
        self.settings = settings or SettingsService()
        self.preferences = preferences or TranslationPreferences(self.settings, self)
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
        naming.currentTextChanged.connect(update_naming_mode)
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
            "Выберите язык приложения. Пока выбор сохраняется как настройка-заглушка.",
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
        selected_language = str(self.settings.value("general/ui_language", "Русский"))
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
                lambda checked, value=language: checked and self.settings.save_value("general/ui_language", value)
            )
            self.language_group.addButton(button)
            layout.addWidget(button)
        if not self.language_group.checkedButton():
            self.language_group.buttons()[0].setChecked(True)
        layout.addStretch()
        return page

    def _performance_page(self) -> QWidget:
        page, layout, form = self._page(
            "Производительность",
            "Полный контроль нагрузки хранится только на этом компьютере. По умолчанию все параметры выбираются автоматически.",
        )
        self.performance_mode = ModeRequirementsCombo()
        self.performance_mode.setObjectName("performanceMode")
        self.performance_mode.set_clean_mode(self.preferences.profile)
        self.performance_mode.currentIndexChanged.connect(
            lambda: self.preferences.set_profile(self.performance_mode.clean_mode())
        )
        logical_cores = max(1, os.cpu_count() or 1)
        thread_options = ["Автоматически", *[str(value) for value in range(1, logical_cores + 1)]]
        self.device_combo = self._combo("performance/device", self.preferences.device, ["Auto", "CPU", "GPU"])
        self.device_combo.currentTextChanged.connect(self.preferences.set_device)
        self.preferences.device_changed.connect(self._set_device)
        self.preferences.profile_changed.connect(self._set_profile)
        self.cpu_threads_combo = self._combo("performance/cpu_threads", "Автоматически", thread_options)
        self.gpu_combo = self._combo("performance/gpu", "Автоматически", ["Автоматически", "Отключено", "Предпочтительно", "Обязательно"])
        self.ram_combo = self._combo("performance/ram", "Автоматически", ["Автоматически", "2 GB", "4 GB", "6 GB", "8 GB", "12 GB", "16 GB", "24 GB", "32 GB", "48 GB", "64 GB"])
        self.vram_combo = self._combo("performance/vram", "Автоматически", ["Автоматически", "1 GB", "2 GB", "4 GB", "6 GB", "8 GB", "10 GB", "12 GB", "16 GB", "24 GB"])
        self.hardware_value = QLabel("Нажмите «Определить оборудование»", objectName="hardwareValue")
        self.hardware_value.setWordWrap(True)
        self.recommendation_value = QLabel("Будет рассчитан после анализа", objectName="hardwareValue")
        self.recommendation_value.setWordWrap(True)
        form.addRow("Режим перевода", self.performance_mode)
        form.addRow("Устройство", self.device_combo)
        form.addRow("Потоки CPU", self.cpu_threads_combo)
        form.addRow("Использование GPU", self.gpu_combo)
        form.addRow("Ограничение RAM", self.ram_combo)
        form.addRow("Ограничение VRAM", self.vram_combo)
        self._add_checks(layout, [
            self._check("performance/unload_model", "Освобождать модель из памяти после простоя", True),
            self._check("performance/reduce_load", "Автоматически снижать нагрузку при нехватке памяти", True),
        ])
        form.addRow("Ваше оборудование", self.hardware_value)
        form.addRow("Рекомендуемый профиль", self.recommendation_value)
        recommend = QPushButton("Определить оборудование")
        recommend.setObjectName("hardwareRecommendation")
        recommend.clicked.connect(self._show_hardware_recommendation)
        layout.addWidget(recommend, alignment=Qt.AlignmentFlag.AlignLeft)
        note = QLabel(
            "Анализ только показывает предварительную рекомендацию. В AW 0.4 работают выбор устройства, "
            "профиль, потоки CPU и выгрузка после простоя. Лимиты RAM/VRAM и снижение нагрузки пока не применяются.",
            objectName="secondary",
        )
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch()
        saved_hardware = HardwareProfileService().load()
        if saved_hardware:
            self._display_hardware_profile(saved_hardware)
        return page

    def _set_device(self, value: str) -> None:
        if hasattr(self, "device_combo") and self.device_combo.currentText() != value:
            self.device_combo.setCurrentText(value)

    def _set_profile(self, value: str) -> None:
        if hasattr(self, "performance_mode") and self.performance_mode.clean_mode() != value:
            self.performance_mode.set_clean_mode(value)

    def _show_hardware_recommendation(self) -> None:
        service = HardwareProfileService()
        hardware = service.detect()
        service.save(hardware)
        self._display_hardware_profile(hardware)

    def _display_hardware_profile(self, hardware) -> None:
        recommendation = HardwareProfileService.recommend(hardware)
        ram = f"{hardware.ram_gb} ГБ" if hardware.ram_gb else "не определена"
        vram = f"{hardware.vram_gb} ГБ" if hardware.vram_gb else "не определена"
        self.hardware_value.setText(
            f"CPU: {hardware.cpu}\n"
            f"Логических потоков: {hardware.logical_cores}\n"
            f"RAM: {ram}\n"
            f"GPU: {hardware.gpu}\n"
            f"VRAM: {vram}"
        )
        self.recommendation_value.setText(
            f"Устройство: {recommendation.device}\n"
            f"Профиль: {recommendation.profile}\n"
            f"Потоки CPU: {recommendation.cpu_threads}\n"
            f"Ограничение RAM: {recommendation.ram_limit}\n"
            f"Ограничение VRAM: {recommendation.vram_limit}"
        )

    def _interface_page(self) -> QWidget:
        page, layout, form = self._page("Интерфейс", "Внешний вид и отображение прогресса.")
        theme = self._combo("interface/theme", "Тёмная", ["Тёмная", "Системная"])
        theme.currentTextChanged.connect(
            lambda value: ThemeManager(QApplication.instance(), self.settings).apply(value)
        )
        form.addRow("Тема", theme)
        accent = QComboBox()
        accent.addItem("Фирменный зелёный TreeTranslate")
        accent.setEnabled(False)
        form.addRow("Акцентный цвет", accent)
        self._add_checks(layout, [
            self._check("interface/animations", "Анимации интерфейса", True),
            self._check("interface/eta", "Показывать расчёт оставшегося времени", True),
            self._check("interface/detailed_progress", "Показывать подробный прогресс", True),
            self._check("interface/extensions", "Показывать расширения файлов", True),
        ])
        layout.addStretch()
        return page
