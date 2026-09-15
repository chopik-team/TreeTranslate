import hashlib
import json

import pytest

from app.engine.errors import ModelCorruptedError, ModelMissingError
from app.engine.runtime.model_manager import ModelManager, ModelState
from app.config.paths import MODELS_DIR
from app.engine.factory import create_translation_engine


def write_model(root, *, backend="argos", name="argos-en-ru", pair=("en", "ru")):
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "model.bin").write_bytes(b"local-test-artifact")
    data = (folder / "model.bin").read_bytes()
    row = dict(id=name, backend=backend, path=name, version="test", source="test fixture",
               languages=list(pair), pairs=[list(pair)], format="ctranslate2", quantization="int8",
               files=[dict(path="model.bin", size=len(data), sha256=hashlib.sha256(data).hexdigest())],
               license="test", size=len(data))
    manifest = root / "models_manifest.json"
    rows = json.loads(manifest.read_text())["models"] if manifest.exists() else []
    rows.append(row)
    manifest.write_text(json.dumps(dict(schema_version=1, models=rows)), encoding="utf-8")
    return folder


def test_model_manager_lazy_inventory_and_no_startup_hash(tmp_path, monkeypatch):
    write_model(tmp_path)
    monkeypatch.setattr(hashlib, "file_digest", lambda *args: pytest.fail("startup hashing"))
    manager = ModelManager(tmp_path)
    assert manager._records is None
    record, = manager.available("argos")
    assert manager.states[record.id] == ModelState.AVAILABLE


def test_missing_size_and_manual_checksum_validation(tmp_path):
    folder = write_model(tmp_path)
    manager = ModelManager(tmp_path)
    record, = manager.records
    manager.validate(record, full=True)
    data = (folder / "model.bin").read_bytes()
    (folder / "model.bin").write_bytes(b"x" * len(data))
    manager.validate(record)
    with pytest.raises(ModelCorruptedError):
        manager.validate(record, full=True)
    with pytest.raises(ModelCorruptedError):
        manager.validate(record)
    (folder / "model.bin").unlink()
    manager.states.clear()
    with pytest.raises(ModelMissingError):
        manager.validate(record)
    assert manager.available("argos") == ()
    assert manager.states[record.id] == ModelState.MISSING


def test_manifest_cannot_escape_bundle(tmp_path):
    write_model(tmp_path)
    manifest = tmp_path / "models_manifest.json"
    data = json.loads(manifest.read_text())
    data["models"][0]["files"][0]["path"] = "../../outside.bin"
    manifest.write_text(json.dumps(data))
    with pytest.raises(ModelCorruptedError):
        ModelManager(tmp_path).records


def test_empty_installation_is_valid(tmp_path):
    assert ModelManager(tmp_path).available("m2m100") == ()


def test_production_factory_model_root_does_not_depend_on_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    engine = create_translation_engine()
    try:
        roots = {backend.models.root for backend in engine.backends.values()}
        assert roots == {MODELS_DIR.resolve()}
        assert (next(iter(roots)) / "models_manifest.json").is_file()
    finally:
        engine.shutdown()
