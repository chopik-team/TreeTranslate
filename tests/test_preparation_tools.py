import json
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest

from app.engine.runtime.model_manager import ModelManager
from tools.model_artifacts import record_model
from tools.prepare_argos_models import prepare


@pytest.mark.parametrize("script,args", [
    ("prepare_argos_models.py", ["--pairs", "en-ru"]),
    ("prepare_m2m100.py", ["--source", "facebook/m2m100_418M"]),
])
def test_build_download_requires_explicit_opt_in(script, args):
    run = subprocess.run([sys.executable, str(Path("tools") / script), *args], capture_output=True, text=True, timeout=10)
    assert run.returncode == 2
    assert "--allow-network" in run.stderr


def test_argos_archive_traversal_is_rejected_before_extract(tmp_path):
    archive = tmp_path / "bad.argosmodel"
    with zipfile.ZipFile(archive, "w") as file:
        file.writestr("../../../escaped.txt", "not allowed")
    with pytest.raises(ValueError, match="Unsafe"):
        prepare(archive, tmp_path / "models", "local fixture")
    assert not (tmp_path / "escaped.txt").exists()


def test_preparation_manifest_is_readable_and_hashes_match(tmp_path):
    root = tmp_path / "models"
    model = root / "example"
    model.mkdir(parents=True)
    (model / "model.bin").write_bytes(b"example model")
    (model / "README.md").write_text("Model fixture", encoding="utf-8")
    record_model(root, model, model_id="example", backend="argos", version="1", source="test fixture",
                 languages=["en", "ru"], pairs=[["en", "ru"]], quantization="int8", license_text="test")
    manager = ModelManager(root)
    record, = manager.records
    manager.validate(record, full=True)
    assert (tmp_path / "model-metadata/example/README.md").read_text() == "Model fixture"
