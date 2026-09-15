from __future__ import annotations

import hashlib
import logging
from enum import StrEnum
from pathlib import Path

from app.engine.errors import ModelCorruptedError, ModelMissingError
from app.engine.models.manifest import ModelRecord, local_path, read_manifest

logger = logging.getLogger("treetranslate.engine.models")


class ModelState(StrEnum):
    AVAILABLE = "available"
    MISSING = "missing"
    CORRUPTED = "corrupted"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"


class ModelManager:
    """Manifest and filesystem only. No tokenizer, inference or startup hashing."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._records: tuple[ModelRecord, ...] | None = None
        self.states: dict[str, ModelState] = {}
        logger.info("model_root=%s manifest_exists=%s",
                    self.root, (self.root / "models_manifest.json").is_file())

    @property
    def records(self) -> tuple[ModelRecord, ...]:
        if self._records is None:
            self._records = read_manifest(self.root / "models_manifest.json")
        return self._records

    def path(self, record: ModelRecord) -> Path:
        return local_path(self.root, record.path)

    def validate(self, record: ModelRecord, *, full: bool = False) -> Path:
        root = self.path(record)
        if self.states.get(record.id) == ModelState.CORRUPTED and not full:
            raise ModelCorruptedError()
        try:
            for item in record.files:
                file = local_path(root, item.path)
                if not file.is_file():
                    self.states[record.id] = ModelState.MISSING
                    logger.warning("model_id=%s model_state=%s", record.id, ModelState.MISSING.value)
                    raise ModelMissingError()
                if file.stat().st_size != item.size:
                    raise ModelCorruptedError()
                if full:
                    with file.open("rb") as stream:
                        digest = hashlib.file_digest(stream, "sha256").hexdigest()
                    if digest != item.sha256:
                        raise ModelCorruptedError()
        except ModelCorruptedError:
            self.states[record.id] = ModelState.CORRUPTED
            logger.warning("model_id=%s model_state=%s", record.id, ModelState.CORRUPTED.value)
            raise
        except OSError:
            self.states[record.id] = ModelState.ERROR
            logger.warning("model_id=%s model_state=%s", record.id, ModelState.ERROR.value)
            raise ModelCorruptedError() from None
        if self.states.get(record.id) not in {ModelState.LOADING, ModelState.READY}:
            self.states[record.id] = ModelState.AVAILABLE
        logger.debug("model_id=%s model_state=%s", record.id, self.states[record.id].value)
        return root

    def available(self, backend: str) -> tuple[ModelRecord, ...]:
        records = []
        for record in self.records:
            if record.backend != backend:
                continue
            try:
                self.validate(record)
                records.append(record)
            except ModelMissingError:
                continue
        return tuple(records)
