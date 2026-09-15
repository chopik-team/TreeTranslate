from pathlib import Path
import os
import sys

PROJECT_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
ASSETS_DIR = PROJECT_ROOT / "assets"
MODELS_DIR = PROJECT_ROOT / "vendor" / "models"
LOGOS_DIR = ASSETS_DIR / "logos"
ICONS_DIR = ASSETS_DIR / "icons"
STYLES_DIR = PROJECT_ROOT / "app" / "gui" / "styles"
TREE_TRANSLATE_LOGO = LOGOS_DIR / "treetranslate.svg"
APP_DATA_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "CHOPIK Team" / "TreeTranslate"
LOGS_DIR = APP_DATA_DIR / "logs"


def icon_path(name: str) -> str:
    return str(ICONS_DIR / f"{name}.svg")


def stylesheet_url(path: Path) -> str:
    """Return a runtime-resolved path in the format accepted by Qt QSS."""
    return path.resolve().as_posix()
