import socket
from pathlib import Path
import os
import subprocess
import sys

import pytest

from app.engine.errors import DeviceUnavailableError
from app.engine.factory import create_translation_engine
from app.engine.types import DevicePreference, PerformanceProfile, TranslationRequest

pytestmark = pytest.mark.integration

@pytest.fixture(scope="module")
def local_engine():
    engine = create_translation_engine()
    # Absence is a skip. A present but broken installation must fail the test.
    root = Path("vendor/models")
    if not (root / "m2m100-418m-int8/model/model.bin").is_file() or not (root / "argos/argos-en-ru/model/model.bin").is_file():
        pytest.skip("Prepared local Argos and M2M100 artifacts are absent")
    yield engine
    engine.shutdown()


@pytest.mark.parametrize("backend", ["argos", "m2m100", "router"])
@pytest.mark.parametrize("text,source,target", [
    ("Hello world.", "en", "ru"), ("Привет, мир.", "ru", "en"),
    ("你好世界", "zh", "ru"), ("Перезапустите приложение после установки.", "ru", "zh"),
])
def test_real_cpu_translation(local_engine, backend, text, source, target, monkeypatch):
    attempts = []
    def forbidden(*args, **kwargs):
        attempts.append(True)
        raise AssertionError("Runtime attempted network access")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    # Catch accidental official APIs before the audit hook can turn them into fallback.
    from argostranslate import package
    monkeypatch.setattr(package, "update_package_index", forbidden)
    monkeypatch.setattr(package.AvailablePackage, "download", forbidden)
    result = local_engine.translate(TranslationRequest(text, source, target, DevicePreference.CPU),
                                    backend_only=None if backend == "router" else backend)
    assert not attempts
    assert result.translated_text.strip()
    assert result.device == "cpu"
    if target == "ru":
        assert any("а" <= c.lower() <= "я" for c in result.translated_text)
    elif target == "zh":
        assert any("\u4e00" <= c <= "\u9fff" for c in result.translated_text)
    else:
        assert any("a" <= c.lower() <= "z" for c in result.translated_text)
    expected = ("m2m100" if "zh" in (source, target) else "argos") if backend == "router" else backend
    assert result.backend == expected
    assert not result.fallback_used


@pytest.mark.parametrize("backend", ["argos", "m2m100", "router"])
def test_real_gpu_translation_when_available(local_engine, backend):
    if not local_engine.devices.gpu_available():
        pytest.skip("No CUDA device")
    result = local_engine.translate(
        TranslationRequest("请重新启动应用程序。", "zh", "ru", DevicePreference.GPU),
        backend_only=None if backend == "router" else backend)
    assert result.device == "cuda" and result.translated_text
    assert not result.fallback_used


def test_real_model_reused_then_unloaded(local_engine):
    request = TranslationRequest("Save the configuration file.", "en", "ru", DevicePreference.CPU)
    local_engine.translate(request, backend_only="argos")
    backend = local_engine.backends["argos"]
    translator = backend._translators[("en", "ru")]
    local_engine.translate(request, backend_only="argos")
    assert backend._translators[("en", "ru")] is translator
    local_engine.runtime._last_used -= local_engine.runtime.idle_timeout_seconds + 1
    assert local_engine.runtime.release_idle()
    assert not translator.model_is_loaded
    local_engine.translate(request, backend_only="argos")
    assert backend._translators[("en", "ru")] is not translator


def test_first_real_import_and_inference_make_zero_network_attempts(local_engine, tmp_path):
    config = tmp_path / "foreign-config" / "argos-translate"
    config.mkdir(parents=True)
    (config / "settings.json").write_text('{"ARGOS_DEBUG":true,"ARGOS_MODEL_PROVIDER":"OPENAI"}')
    code = '''
import sys
attempts=[]
def audit(event,args):
    if event.startswith('socket.') or event=='urllib.Request': attempts.append(event)
sys.addaudithook(audit)
from app.engine.factory import create_translation_engine
from app.engine.types import TranslationRequest,DevicePreference
engine=create_translation_engine()
for backend,text,source,target in [('argos','Save the file.','en','ru'),('m2m100','你好世界','zh','ru')]:
    result=engine.translate(TranslationRequest(text,source,target,DevicePreference.CPU),backend_only=backend)
    assert result.translated_text and not result.fallback_used
assert not attempts,attempts
assert not any(name in sys.modules for name in ['torch','transformers','argostranslate.translate','stanza','spacy'])
from argostranslate import settings
assert not settings.debug
assert 'TreeTranslate' in str(settings.config_dir)
engine.shutdown()
from app.services.lexical_assistance import LexicalAssistance
lexicon = LexicalAssistance()
assert lexicon.suggest('Gam', 'en')[0].word == 'Game'
assert lexicon.reference('hi', 'en', 'ru').usage
assert not attempts, attempts
print('No network attempts; no PyTorch/Transformers; isolated Argos config')
'''
    env = dict(os.environ, XDG_CONFIG_HOME=str(config.parent))
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30, env=env)
    assert run.returncode == 0, run.stderr


def test_real_qt_gpu_window_exits_cleanly(local_engine):
    if sys.platform != "win32" or not local_engine.devices.gpu_available():
        pytest.skip("Native Windows CUDA UI smoke requires a CUDA device")
    env = dict(os.environ, QT_QPA_PLATFORM="windows", PYTHONIOENCODING="utf-8", PYTHONFAULTHANDLER="1")
    run = subprocess.run([sys.executable, "tools/smoke_translation_ui.py"], capture_output=True, text=True,
                         encoding="utf-8", timeout=45, env=env)
    assert run.returncode == 0, f"Native exit code {run.returncode}\n{run.stdout}\n{run.stderr}"
    assert "GPU idle/reload" in run.stdout


def test_native_dictionary_completion_and_maximum_translation(local_engine):
    if sys.platform != "win32" or not local_engine.devices.gpu_available():
        pytest.skip("Native Windows CUDA UI smoke requires a CUDA device")
    env = dict(os.environ, QT_QPA_PLATFORM="windows", PYTHONIOENCODING="utf-8", PYTHONFAULTHANDLER="1")
    run = subprocess.run([sys.executable, "tools/smoke_lexical_ui.py"], capture_output=True, text=True,
                         encoding="utf-8", timeout=45, env=env)
    assert run.returncode == 0, f"Native exit code {run.returncode}\n{run.stdout}\n{run.stderr}"
    assert "Game completion + Enter" in run.stdout
