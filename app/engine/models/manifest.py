from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.engine.errors import ModelCorruptedError


def local_path(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or not path.is_relative_to(root.resolve()):
        raise ModelCorruptedError()
    return path


@dataclass(frozen=True, slots=True)
class ModelFile:
    path: str
    sha256: str
    size: int


@dataclass(frozen=True, slots=True)
class ModelRecord:
    id: str
    backend: str
    path: str
    version: str
    source: str
    languages: tuple[str, ...]
    pairs: tuple[tuple[str, str], ...]
    format: str
    quantization: str
    files: tuple[ModelFile, ...]
    license: str
    size: int


def read_manifest(path: Path) -> tuple[ModelRecord, ...]:
    if not path.exists():
        return ()
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        if document["schema_version"] != 1:
            raise ValueError("schema")
        records = []
        for row in document["models"]:
            record = ModelRecord(
                id=row["id"], backend=row["backend"], path=row["path"],
                version=row["version"], source=row["source"],
                languages=tuple(row.get("languages", [])),
                pairs=tuple(tuple(pair) for pair in row.get("pairs", [])),
                format=row["format"], quantization=row["quantization"],
                files=tuple(ModelFile(**item) for item in row["files"]),
                license=row["license"], size=row["size"],
            )
            if not re.fullmatch(r"[a-zA-Z0-9._-]+", record.id) or not record.files:
                raise ValueError("model")
            model_root = local_path(path.parent, record.path)
            for item in record.files:
                local_path(model_root, item.path)
                if not re.fullmatch(r"[0-9a-f]{64}", item.sha256) or item.size < 0:
                    raise ValueError("file")
            if record.size != sum(item.size for item in record.files):
                raise ValueError("size")
            if len({item.path for item in record.files}) != len(record.files):
                raise ValueError("duplicate file")
            if any(len(pair) != 2 for pair in record.pairs):
                raise ValueError("pair")
            records.append(record)
        if len({row.id for row in records}) != len(records):
            raise ValueError("duplicate model")
        return tuple(records)
    except (OSError, ValueError, KeyError, TypeError):
        raise ModelCorruptedError() from None
