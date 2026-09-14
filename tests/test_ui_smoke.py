import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton, QToolButton
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest

from app.gui.main_window import MainWindow
from app.gui.dialogs.settings_dialog import SettingsDialog
from app.models.translation_job import JobState
from app.gui.widgets.translation_mode import ModeRequirementsCombo
from app.gui.widgets.workspace_splitter import WorkspaceSplitterHandle


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


def test_settings_has_five_user_sections() -> None:
    app = QApplication.instance() or QApplication([])
    dialog = SettingsDialog()
    assert dialog.sections.count() == 5
    assert dialog.pages.count() == 5
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
    assert window.text_page.result.editor.toPlainText() == "Hi"
    assert not window.text_page.reference_area.isHidden()
    window.text_page.source.editor.clear()
    assert window.text_page.reference_area.isHidden()
    assert window.text_page.findChildren(QPushButton, "primary") == []
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


def test_logo_mouse_events_do_not_reach_title_bar() -> None:
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    opened = []
    window.title_bar.brand.clicked.connect(lambda: opened.append(True))
    QTest.mousePress(window.title_bar.brand, Qt.MouseButton.LeftButton, pos=window.title_bar.brand.rect().center())
    QTest.mouseRelease(window.title_bar.brand, Qt.MouseButton.LeftButton, pos=window.title_bar.brand.rect().center())
    assert opened == [True]
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
    assert not info.icon().isNull()
    assert all(mode in info.toolTip() for mode in ("Auto", "CPU", "GPU"))
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
    window.close()
