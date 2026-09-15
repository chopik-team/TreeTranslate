import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from app.engine.errors import BackendUnavailableError, ModelMissingError
from app.engine.factory import create_translation_engine
from app.engine.runtime.offline import offline_scope
from app.engine.types import TranslationRequest


def test_guard_blocks_socket_attempt():
    with offline_scope(), pytest.raises(BackendUnavailableError):
        socket.create_connection(("example.invalid", 443))


def test_missing_models_never_attempt_network(tmp_path, monkeypatch):
    monkeypatch.setattr(socket, "create_connection", lambda *_a, **_k: pytest.fail("network"))
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_a, **_k: pytest.fail("DNS"))
    engine = create_translation_engine(tmp_path)
    with pytest.raises(ModelMissingError):
        engine.translate(TranslationRequest("Hello.", "en", "ru"))
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    engine.shutdown()


def test_gui_startup_does_not_import_inference_or_load_models():
    code = '''
import os,sys
os.environ['QT_QPA_PLATFORM']='offscreen'
from PySide6.QtWidgets import QApplication
from app.gui.main_window import MainWindow
app=QApplication([])
window=MainWindow()
assert not any(name in sys.modules for name in ['argostranslate','ctranslate2','sentencepiece','transformers','torch','langid'])
assert window.translation_service.engine.runtime._warm is None
window.close()
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr


def test_gui_has_no_specific_backend_imports():
    for file in Path("app/gui").rglob("*.py"):
        text = file.read_text(encoding="utf-8")
        assert not any(token in text for token in ("import argostranslate", "import ctranslate2", "import transformers", "app.engine.backends"))
