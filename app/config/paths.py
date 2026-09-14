from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ASSETS_DIR = PROJECT_ROOT / "assets"
LOGOS_DIR = ASSETS_DIR / "logos"
ICONS_DIR = ASSETS_DIR / "icons"
STYLES_DIR = PROJECT_ROOT / "app" / "gui" / "styles"
TREE_TRANSLATE_LOGO = LOGOS_DIR / "treetranslate.svg"


def icon_path(name: str) -> str:
    return str(ICONS_DIR / f"{name}.svg")
