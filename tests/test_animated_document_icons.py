import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from app.gui.widgets.drop_zone import DropZone
from app.gui.widgets.file_tree import FileTree
from app.models.file_item import FileItem


def test_menu_animation_restarts_and_stops_on_hide():
    app = QApplication.instance() or QApplication([])
    zone = DropZone()
    actions = list(zone._menu_icons)
    first = zone._menu_icons[actions[0]]
    try:
        for _ in range(3):
            zone._animate_menu_icon(actions[0])
            QTest.qWait(first.durations[0] + 30)
            assert first.index > 0
            zone._animate_menu_icon(actions[1])
            assert first.index == 0 and not first.timer.isActive()
            zone._choose_menu.aboutToHide.emit()
            assert all(not icon.timer.isActive() for icon in zone._menu_icons.values())
    finally:
        zone._stop_menu_icons()
        zone.close()


def test_folder_animation_preserves_checks_and_stops_before_tree_rebuild():
    app = QApplication.instance() or QApplication([])
    tree = FileTree()
    root = FileItem("Documents", True, [FileItem("Nested", True, [FileItem("one.pdf"), FileItem("two.docx")])])
    try:
        tree.populate(root)
        tree.show()
        app.processEvents()
        assert tree._root_animation.timer.isActive()
        item = tree.tree.topLevelItem(0).child(0)
        item.child(0).setCheckState(0, Qt.CheckState.Unchecked)
        for _ in range(3):
            tree._hover_item(item, 0)
            QTest.qWait(tree._folder_animation.durations[0] + 30)
            assert tree._folder_animation.index > 0
            assert item.child(0).checkState(0) == Qt.CheckState.Unchecked
            assert item.child(1).checkState(0) == Qt.CheckState.Checked
            tree._hover_item(item.child(1), 0)
            assert not tree._folder_animation.timer.isActive()
            assert tree._root_animation.timer.isActive()
        tree._hover_item(item, 0)
        tree.show_empty()
        assert tree._animated_item is None
        assert not tree._folder_animation.timer.isActive()
        assert not tree._root_animation.timer.isActive()
    finally:
        tree.close()
