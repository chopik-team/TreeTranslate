from pathlib import Path
import logging

from app.engine.backends.argos_backend import ArgosBackend
from app.engine.backends.m2m100_backend import M2M100Backend
from app.engine.router.translation_router import TranslationRouter
from app.engine.runtime.model_manager import ModelManager
from app.config.paths import MODELS_DIR

logger = logging.getLogger("treetranslate.engine.factory")


def create_translation_engine(models_root: Path | None = None) -> TranslationRouter:
    models_root = MODELS_DIR if models_root is None else models_root
    manager = ModelManager(models_root)
    logger.info("engine factory model_root=%s manifest_exists=%s",
                manager.root, (manager.root / "models_manifest.json").is_file())
    return TranslationRouter({"argos": ArgosBackend(manager), "m2m100": M2M100Backend(manager)})
