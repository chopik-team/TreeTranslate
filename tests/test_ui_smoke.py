import os
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QButtonGroup, QCheckBox, QComboBox, QLabel, QPushButton, QScrollArea, QToolButton
from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest

from app.gui.main_window import MainWindow as ProductionMainWindow
from app.services.mock_translation_service import MockTranslationService
from app.gui.dialogs.settings_dialog import SettingsDialog
from app.gui.dialogs.about_dialog import AboutDialog
from app.models.translation_job import JobState, TranslationProgress
from app.gui.widgets.translation_mode import ModeRequirementsCombo
from app.gui.widgets.workspace_splitter import WorkspaceSplitterHandle
from app.gui.widgets.language_combo import LanguageComboBox
from app.gui.widgets.language_selector import LanguageSelector
from app.gui.widgets.acceleration_selector import HoverInfoButton
from app.config.constants import APP_VERSION, BOOSTY_URL, PROJECT_GITHUB_URL
from app.gui.styles.theme import load_stylesheet


def MainWindow():
    return ProductionMainWindow(translation_service=MockTranslationService())


def test_main_window_and_states() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.file_page.progress.processed.text() == "0 / 0"
    assert window.stack.count() == 2
    assert window.minimumWidth() <= 1280 and window.minimumHeight() <= 720
    for state in JobState:
        window.file_page.progress.set_state(state)
    window.close()


def test_object_total_appears_after_scan() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.translation._show_tree()
    assert window.file_page.progress.processed.text() == "0 / 14"
    window.close()


def test_file_preview_does_not_keep_clicked_row_selected() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    tree = window.file_page.file_tree.tree
    tree.setCurrentItem(tree.topLevelItem(0))
    assert tree.selectedItems() == []
    window.close()


def test_settings_has_separate_language_section() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog()
    assert dialog.sections.count() == 4
    assert dialog.pages.count() == 4
    assert "Язык" in dialog.SECTIONS
    assert "Перевод" not in dialog.SECTIONS
    assert "О программе" not in dialog.SECTIONS
    assert not any(
        checkbox.text() == "Сворачивать приложение в системный трей"
        for checkbox in dialog.findChildren(QCheckBox)
    )
    benchmark = dialog.findChild(QPushButton, "hardwareRecommendation")
    assert benchmark is not None and benchmark.isEnabled()
    hardware_values = dialog.findChildren(QLabel, "hardwareValue")
    assert len(hardware_values) == 2
    assert dialog.performance_mode.clean_mode() in ("Автоматический", "Эконом", "Быстрый", "Баланс", "Турбо", "Максимум")
    assert dialog.device_combo.currentText() in ("Auto", "CPU", "GPU")
    assert dialog.ram_combo.findText("4 GB") >= 0
    assert dialog.vram_combo.findText("4 GB") >= 0
    assert dialog.cpu_threads_combo.count() > 1
    assert "Масштаб интерфейса" not in {
        label.text() for label in dialog.findChildren(QLabel)
    }
    assert all(
        scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        for scroll in dialog.findChildren(QScrollArea)
    )
    dialog.close()


def test_about_dialog_has_sorted_product_credits() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = AboutDialog()
    labels = " ".join(label.text() for label in dialog.findChildren(QLabel))
    buttons = [button.text() for button in dialog.findChildren(QPushButton)]
    assert "локального перевода" in labels
    assert f"{APP_VERSION} · Windows" in labels
    assert "офлайн" not in labels
    assert "Алексей Широков · Станислав Смирнов" in labels
    assert "Станислав Смирнов" in labels
    assert "ChatGPT 5.6 Sol" in labels
    assert "Translation Engine" not in labels
    assert "Translation backend" not in labels
    assert "Argos Translate 1.11.0 — MIT (программный код)" in labels
    assert "M2M100 418M INT8 — MIT" in labels
    assert "CTranslate2 4.8.2 — MIT" in labels
    assert "SentencePiece 0.2.2 — Apache-2.0" in labels
    assert "лицензия итоговых весов требует уточнения" not in labels
    assert buttons == ["TreeTranslate", "Закрыть"]
    dialog.close()


def test_about_product_title_opens_its_github_repository() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = AboutDialog()
    title = dialog.findChild(QPushButton, "aboutProjectLink")
    assert title is not None
    assert "QPushButton#aboutProjectLink:hover" in load_stylesheet()
    with patch("app.gui.dialogs.about_dialog.QDesktopServices.openUrl", return_value=True) as open_url:
        title.click()
    open_url.assert_called_once()
    assert open_url.call_args.args[0].toString() == PROJECT_GITHUB_URL
    dialog.close()


def test_interface_languages_have_placeholder_flags_and_selection() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog()
    group = dialog.findChild(QButtonGroup)
    choices = group.buttons()
    assert len(choices) == 8
    assert group.exclusive()
    assert all(button.text().strip() for button in choices)
    assert all(not button.icon().isNull() for button in choices)
    assert {button.property("language") for button in choices} >= {"中文", "日本語"}
    assert group.checkedButton() is not None
    choices[1].click()
    assert group.checkedButton() is choices[1]
    dialog.close()


def test_all_main_language_selectors_use_flag_icons() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    dialog = SettingsDialog()
    combos = window.findChildren(LanguageComboBox) + dialog.findChildren(LanguageComboBox)
    assert len(combos) == 4
    for combo in combos:
        for index in range(combo.count()):
            if combo.itemText(index) not in ("Авто", "Определить автоматически"):
                assert not combo.itemIcon(index).isNull()
    dialog.close()
    window.close()


def test_language_pair_never_keeps_the_same_explicit_language() -> None:
    app = QApplication.instance() or QApplication([])
    selector = LanguageSelector()
    assert selector.source_combo.findText("Русский") >= 0
    assert selector.target_combo.findText(selector.AUTOMATIC) >= 0

    selector.source_combo.setCurrentText("Русский")
    selector.target_combo.setCurrentText("Английский")
    selector.target_combo.setCurrentText("Русский")
    assert selector.source_combo.currentText() == selector.AUTOMATIC
    assert selector.target_combo.currentText() == "Русский"

    selector.target_combo.setCurrentText("Английский")
    selector.source_combo.setCurrentText("Английский")
    assert selector.source_combo.currentText() == "Английский"
    assert selector.target_combo.currentText() == selector.AUTOMATIC


def test_chinese_and_japanese_are_available_in_both_directions() -> None:
    app = QApplication.instance() or QApplication([])
    selector = LanguageSelector()
    for language in ("Китайский", "Японский"):
        source_index = selector.source_combo.findText(language)
        target_index = selector.target_combo.findText(language)
        assert source_index >= 0 and target_index >= 0
        assert not selector.source_combo.itemIcon(source_index).isNull()
        assert not selector.target_combo.itemIcon(target_index).isNull()

    selector.source_combo.setCurrentText("Китайский")
    selector.target_combo.setCurrentText("Японский")
    assert (selector.source_combo.currentText(), selector.target_combo.currentText()) == ("Китайский", "Японский")

    selector.source_combo.setCurrentText("Японский")
    assert (selector.source_combo.currentText(), selector.target_combo.currentText()) == ("Японский", selector.AUTOMATIC)

    selector.source_combo.setCurrentText("Китайский")
    selector.target_combo.setCurrentText("Китайский")
    assert (selector.source_combo.currentText(), selector.target_combo.currentText()) == (selector.AUTOMATIC, "Китайский")


def test_british_and_american_english_are_separate_choices() -> None:
    app = QApplication.instance() or QApplication([])
    selector = LanguageSelector()

    for language in ("Английский", "Английский (США)"):
        source_index = selector.source_combo.findText(language)
        target_index = selector.target_combo.findText(language)
        assert source_index >= 0 and target_index >= 0
        assert not selector.source_combo.itemIcon(source_index).isNull()
        assert not selector.target_combo.itemIcon(target_index).isNull()

    british_index = selector.source_combo.findText("Английский")
    american_index = selector.source_combo.findText("Английский (США)")
    assert (
        selector.source_combo.itemIcon(british_index).cacheKey()
        != selector.source_combo.itemIcon(american_index).cacheKey()
    )


def test_language_swap_button_exchanges_the_pair_atomically() -> None:
    app = QApplication.instance() or QApplication([])
    selector = LanguageSelector()
    selector.source_combo.setCurrentText("Русский")
    selector.target_combo.setCurrentText("Китайский")
    selector.swap_button.click()
    assert selector.source_combo.currentText() == "Китайский"
    assert selector.target_combo.currentText() == "Русский"

    selector.source_combo.setCurrentText(selector.AUTOMATIC)
    selector.target_combo.setCurrentText("Японский")
    selector.swap_button.click()
    assert selector.source_combo.currentText() == "Японский"
    assert selector.target_combo.currentText() == selector.AUTOMATIC


def test_output_folder_naming_uses_clear_mode_selector() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog()
    naming = dialog.findChild(QComboBox, "outputNamingMode")
    assert naming is not None
    assert [naming.itemText(index) for index in range(naming.count())] == [
        "Добавить язык к имени",
        "Оставить как в оригинале",
    ]
    dialog.close()


def test_output_location_has_clear_change_button() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog()
    location = dialog.findChild(QComboBox, "outputLocation")
    assert location is not None
    assert location.itemText(0) == "Рядом с оригиналом"
    change = dialog.findChild(QPushButton, "changeOutputLocation")
    assert change is not None and change.text() == "Изменить…"
    assert dialog.findChild(QLabel, "safetyNotice") is not None
    assert not any(check.text() == "Не изменять оригинальные файлы" for check in dialog.findChildren(QCheckBox))
    dialog.close()


def test_mode_menu_contains_requirements() -> None:
    app = QApplication.instance() or QApplication([])
    combo = ModeRequirementsCombo()
    assert combo.count() == 6
    assert combo.model().columnCount() == 4
    assert combo.model().item(1, 0).isSelectable()
    assert combo.model().item(1, 1).isSelectable()
    assert combo.view().selectionBehavior() == combo.view().SelectionBehavior.SelectRows
    combo.set_clean_mode("Турбо")
    assert combo.clean_mode() == "Турбо"


def test_workspace_uses_custom_splitter_handle() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    handles = window.file_page.findChildren(WorkspaceSplitterHandle)
    active_handles = [handle for handle in handles if not handle.isHidden()]
    assert len(active_handles) == 1
    assert active_handles[0].width() == 13
    window.close()


def test_text_page_uses_automatic_translation() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    assert window.text_page.reference_area.isHidden()
    window.text_page.source.editor.setPlainText("Привет")
    window.text_page._request_translation()
    app.processEvents()
    assert window.text_page.result.editor.toPlainText() == "Hi"
    # Fixed dictionary/examples from AW 0.3 do not describe real input.
    assert window.text_page.reference_area.isHidden()
    window.text_page.source.editor.clear()
    assert window.text_page.reference_area.isHidden()
    assert window.text_page.findChildren(QPushButton, "primary") == []
    assert window.text_page.mode.combo.count() == 6
    window.close()


def test_clicking_svg_logo_opens_brand_menu() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    QTest.mouseClick(window.title_bar.brand, Qt.MouseButton.LeftButton, pos=window.title_bar.brand.rect().center())
    app.processEvents()
    assert window.brand_menu.isVisible()
    window.brand_menu.close()
    window.close()


def test_support_menu_item_fits_and_uses_boosty_icon() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    support = next(
        button for button in window.brand_menu.findChildren(QPushButton)
        if button.text() == "Поддержать TreeTranslate"
    )
    assert window.brand_menu.width() >= support.sizeHint().width()
    assert not support.icon().isNull()
    window.close()


def test_support_menu_opens_project_boosty_page() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    with patch("app.gui.main_window.QDesktopServices.openUrl", return_value=True) as open_url:
        window.brand_menu.support_requested.emit()
    open_url.assert_called_once()
    assert open_url.call_args.args[0].toString() == BOOSTY_URL
    window.close()


def test_logo_mouse_events_do_not_reach_title_bar() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    opened = []
    window.title_bar.brand.clicked.connect(lambda: opened.append(True))
    QTest.mousePress(window.title_bar.brand, Qt.MouseButton.LeftButton, pos=window.title_bar.brand.rect().center())
    QTest.mouseRelease(window.title_bar.brand, Qt.MouseButton.LeftButton, pos=window.title_bar.brand.rect().center())
    assert opened == [True]
    window.close()


def test_logo_hover_highlights_only_the_svg() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    brand = window.title_bar.brand
    brand._hover_timer.stop()
    assert brand.graphicsEffect() is None
    assert brand.logo.graphicsEffect() is None
    inside = brand.mapToGlobal(brand.rect().center())
    outside = inside + QPoint(1000, 1000)
    for _ in range(20):
        with patch("app.gui.widgets.brand_widget.QCursor.pos", return_value=inside):
            brand.refresh_hover()
            assert brand.logo._hovered
        with patch("app.gui.widgets.brand_widget.QCursor.pos", return_value=outside):
            brand.refresh_hover()
            assert not brand.logo._hovered
    window.close()


def test_logo_hover_recovers_after_popup_releases_mouse() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    brand = window.title_bar.brand
    brand._hover_timer.stop()
    window.open_brand_menu()
    app.processEvents()
    assert window.brand_menu.isVisible()
    window.brand_menu.close()
    app.processEvents()
    inside = brand.mapToGlobal(brand.rect().center())
    with patch("app.gui.widgets.brand_widget.QCursor.pos", return_value=inside):
        brand.refresh_hover()
        assert brand.logo._hovered
    window.close()


def test_source_picker_menu_matches_button_width() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window.show()
    app.processEvents()
    picker = next(button for button in window.file_page.drop_zone.findChildren(QPushButton) if button.objectName() == "outlinePrimary")
    picker.menu().aboutToShow.emit()
    assert picker.menu().width() == picker.width()
    window.close()


def test_acceleration_info_has_svg_and_help_text() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    info = window.file_page.acceleration.findChild(QToolButton, "infoButton")
    assert info is not None
    assert isinstance(info, HoverInfoButton)
    assert info.cursor().shape() == Qt.CursorShape.ArrowCursor
    assert not info.icon().isNull()
    assert all(mode in info.toolTip() for mode in ("Auto", "CPU", "GPU"))
    assert all(detail in info.toolTip() for detail in ("VRAM", "сложных вычислений", "Производительность"))
    window.close()


def test_acceleration_selection_is_visible_and_switches_reliably() -> None:
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(load_stylesheet())
    window = MainWindow()
    selector = window.file_page.acceleration
    buttons = {button.text(): button for button in selector.group.buttons()}
    assert "radio_checked.svg);" in app.styleSheet()
    for name in ("GPU", "CPU", "Auto", "GPU"):
        buttons[name].click()
        app.processEvents()
        assert selector.selected() == name
        assert buttons[name].isChecked()
        assert sum(button.isChecked() for button in buttons.values()) == 1
    window.close()


def test_file_controls_follow_job_state() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    controller = window.translation
    controller._show_tree()
    controller._state_changed(JobState.READY)
    assert window.file_page.start_button.isEnabled()
    controller.service.start()
    assert "Приостановить" in window.file_page.progress.pause.text()
    controller.service.pause_or_resume()
    assert "Продолжить" in window.file_page.progress.pause.text()
    controller.service.pause_or_resume()
    assert "Приостановить" in window.file_page.progress.pause.text()
    controller.service.cancel()
    assert "Запустить снова" in window.file_page.start_button.text()
    assert window.file_page.start_button.isEnabled()
    assert not window.file_page.progress.show_output.isEnabled()
    window.close()


def test_eta_value_does_not_repeat_approximation_marker() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    panel = window.file_page.progress
    panel.set_progress(TranslationProgress(percent=50, elapsed_seconds=84, eta_seconds=84))
    assert panel.remaining.text() == "00:01:24"
    panel.set_progress(TranslationProgress())
    assert panel.remaining.text() == "—"
    window.close()


def test_file_and_folder_name_translation_toggles_are_visually_symmetric() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    labels = [label.text() for label in window.file_page.findChildren(QLabel)]
    assert "Перевести названия папок" in labels
    assert "Перевести названия файлов" in labels
    assert window.file_page.translate_folders is not window.file_page.translate_filenames
    window.close()


def test_completed_file_can_be_revealed_in_explorer(tmp_path) -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    output = tmp_path / "document_ru.pdf"
    output.write_bytes(b"translated")

    window.translation.service.file_outputs_ready.emit([output])
    assert window.file_page.progress.show_output.isEnabled()
    with patch("app.controllers.translation_ui_controller.QProcess.startDetached", return_value=(True, 1)) as reveal:
        window.file_page.progress.show_output.click()
    reveal.assert_called_once()
    assert reveal.call_args.args[0] == "explorer.exe"
    assert str(output.resolve()) in reveal.call_args.args[1]
    window.close()
