from app.models.file_item import mock_file_tree
from app.models.translation_job import JobState, TranslationProgress


def test_mock_tree_has_content() -> None:
    tree = mock_file_tree()
    assert tree.is_folder
    assert tree.children
    def counts(item):
        files, folders = (0, 1) if item.is_folder else (1, 0)
        for child in item.children:
            child_files, child_folders = counts(child)
            files += child_files
            folders += child_folders
        return files, folders
    assert counts(tree) == (10, 4)


def test_all_required_states_exist() -> None:
    required = {"IDLE", "DRAGGING", "SCANNING", "READY", "TRANSLATING", "PAUSED", "CANCELLING", "COMPLETED", "ERROR", "CANCELLED"}
    assert required == {state.name for state in JobState}


def test_progress_defaults() -> None:
    progress = TranslationProgress()
    assert progress.percent == 0
