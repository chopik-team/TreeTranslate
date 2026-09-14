from pathlib import Path

from app.config.paths import ASSETS_DIR, ICONS_DIR, TREE_TRANSLATE_LOGO
from app.gui.styles.theme import load_stylesheet


def test_resources_are_bundled_and_stylesheet_has_portable_urls() -> None:
    assert ASSETS_DIR.is_dir()
    assert ICONS_DIR.is_dir()
    assert TREE_TRANSLATE_LOGO.is_file()
    stylesheet = load_stylesheet()
    source = (Path(__file__).parents[1] / "app/gui/styles/stylesheet.qss").read_text(encoding="utf-8")
    assert "C:/TreeTranslate" not in source
    assert ICONS_DIR.resolve().as_posix() in stylesheet
    assert "radio_checked.svg" in stylesheet
    assert Path(TREE_TRANSLATE_LOGO).resolve().is_relative_to(ASSETS_DIR.resolve())


def test_gui_widgets_do_not_embed_local_stylesheets_or_color_literals() -> None:
    widgets = Path(__file__).parents[1] / "app/gui/widgets"
    sources = "\n".join(path.read_text(encoding="utf-8") for path in widgets.glob("*.py"))
    assert ".setStyleSheet(" not in sources
    assert "#1b7540" not in sources
    assert "#26352d" not in sources
