"""Fail closed for Python network access on engine threads, including dependencies.

The audit hook is scoped to the calling thread; user-opened browser links are
unaffected. Build tools deliberately opt out and never get imported by runtime.
"""
import os
import sys
import threading
from contextlib import contextmanager

from app.engine.errors import BackendUnavailableError

_scope = threading.local()
_installed = False
_lock = threading.Lock()


def _audit(event, args) -> None:
    if getattr(_scope, "depth", 0) and (event.startswith("socket.") or event == "urllib.Request"):
        raise BackendUnavailableError("Сетевой доступ движка заблокирован: перевод работает только локально.")


def configure_offline() -> None:
    global _installed
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["ARGOS_DEBUG"] = "0"
    os.environ["ARGOS_MODEL_PROVIDER"] = "OPENNMT"
    with _lock:
        if not _installed:
            sys.addaudithook(_audit)
            _installed = True


@contextmanager
def offline_scope():
    configure_offline()
    _scope.depth = getattr(_scope, "depth", 0) + 1
    try:
        yield
    finally:
        _scope.depth -= 1
