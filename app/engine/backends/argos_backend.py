from __future__ import annotations

import gc
import logging
import os
from collections import deque
from threading import Event, RLock

from app.engine.backends.base_backend import BaseBackend, check_cancelled
from app.engine.backends.text_segments import translate_segments
from app.engine.errors import BackendUnavailableError, DeviceUnavailableError, ModelCorruptedError, UnsupportedLanguageError
from app.engine.runtime.model_manager import ModelManager, ModelState
from app.engine.types import BackendCapabilities, BackendOutput, InferenceOptions, PairKind, TranslationRequest

_ARGOS_LOCK = RLock()  # Argos settings are module-global, across backend instances.
logger = logging.getLogger("treetranslate.engine.argos")


class ArgosBackend(BaseBackend):
    """Official Argos package discovery/tokenizers with a small CT2 adapter.

    Intentionally does not import argostranslate.translate: 1.11 requires Stanza
    (and PyTorch) at import and its SBD can download models. No upstream fork,
    CachedTranslation, external package index, or remote provider is used here.
    """

    name = "argos"

    def __init__(self, models: ModelManager) -> None:
        self.models = models
        self._packages = None
        self._translators = {}
        self._options = None

    def _discover(self):
        with _ARGOS_LOCK:
            if self._packages is not None:
                return self._packages
            records = self.models.available(self.name)
            if not records:
                return {}
            root = self.models.root / "argos"
            os.environ["ARGOS_PACKAGE_DIR"] = str(root)
            os.environ["ARGOS_PACKAGES_DIR"] = str(root)  # actual 1.11 key
            os.environ["ARGOS_DEVICE_TYPE"] = "cpu"
            os.environ["ARGOS_DEBUG"] = "0"
            os.environ["ARGOS_MODEL_PROVIDER"] = "OPENNMT"
            try:
                # Argos reads XDG settings even when an environment override is
                # present. Isolate its config/cache from any user Argos install.
                from app.config.paths import APP_DATA_DIR
                state_root = APP_DATA_DIR / "argos-runtime"
                overrides = {f"XDG_{kind}_HOME": str(state_root / kind.lower())
                             for kind in ("DATA", "CONFIG", "CACHE")}
                previous = {key: os.environ.get(key) for key in overrides}
                os.environ.update(overrides)
                try:
                    from argostranslate import package, settings
                finally:
                    for key, value in previous.items():
                        if value is None:
                            os.environ.pop(key, None)
                        else:
                            os.environ[key] = value
                settings.debug = False
                settings.package_data_dir = root
                settings.package_dirs = [root]
                # The explicit path prevents global user packages entering discovery.
                # 1.11's annotation says Path, but implementation iterates roots.
                installed = package.get_installed_packages(path=[root])
            except ImportError as error:
                logger.error("backend=argos runtime_dependency_missing=%s", error.name or "unknown")
                raise BackendUnavailableError() from None
            except (OSError, ValueError, KeyError, TypeError):
                raise ModelCorruptedError() from None
            by_path = {self.models.path(record): record for record in records}
            self._packages = {}
            for pkg in installed:
                record = by_path.get(pkg.package_path.resolve())
                if record and pkg.type == "translate" and hasattr(pkg, "tokenizer"):
                    # Pair is obtained from the official API; the manifest must agree.
                    pair = (pkg.from_code, pkg.to_code)
                    if pair not in record.pairs:
                        raise ModelCorruptedError()
                    self._packages[pair] = (pkg, record)
            return self._packages

    def _path(self, source: str, target: str, *, pivot: bool = False):
        packages = self._discover()
        queue = deque([(source, ())])
        seen = {source}
        while queue:
            current, path = queue.popleft()
            for pair in sorted(packages):
                if pair[0] != current or (pivot and not path and pair[1] == target):
                    continue
                candidate = path + (pair,)
                if pair[1] == target:
                    return candidate
                if pair[1] not in seen:
                    seen.add(pair[1])
                    queue.append((pair[1], candidate))
        return ()

    def capabilities(self) -> BackendCapabilities:
        packages = self._discover()
        languages = {code for pair in packages for code in pair}
        pivots = {(source, target) for source in languages for target in languages
                  if source != target and self._path(source, target, pivot=True)}
        return BackendCapabilities(direct_pairs=frozenset(packages), pivot_pairs=frozenset(pivots))

    def translate(self, request: TranslationRequest, kind: PairKind,
                  options: InferenceOptions, cancelled: Event) -> BackendOutput:
        with _ARGOS_LOCK:
            check_cancelled(cancelled)
            path = self._path(request.source_language, request.target_language, pivot=kind == PairKind.PIVOT)
            if not path or (kind == PairKind.DIRECT and len(path) != 1):
                raise UnsupportedLanguageError()
            if self._options != options:
                self._unload_translators()
                self._options = options
            from argostranslate import settings
            settings.device = options.device
            os.environ["ARGOS_DEVICE_TYPE"] = options.device
            settings.intra_threads = options.threads
            settings.inter_threads = 1
            settings.compute_type = options.compute_type
            settings.beam_size = options.beam_size
            settings.batch_size = options.batch_tokens
            text = request.text
            ids = []
            for pair in path:
                check_cancelled(cancelled)
                pkg, record = self._packages[pair]
                ids.append(record.id)
                if pair not in self._translators:
                    self.models.states[record.id] = ModelState.LOADING
                    try:
                        import ctranslate2
                        translator = ctranslate2.Translator(
                            str(self.models.validate(record) / "model"), device=options.device,
                            compute_type=options.compute_type, intra_threads=options.threads, inter_threads=1)
                    except (RuntimeError, OSError):
                        self.models.states[record.id] = ModelState.ERROR
                        if options.device == "cuda":
                            raise DeviceUnavailableError() from None
                        raise ModelCorruptedError() from None
                    self._translators[pair] = translator
                    self.models.states[record.id] = ModelState.READY
                translator = self._translators[pair]
                prefix = getattr(pkg, "target_prefix", "")

                def infer(batch):
                    return translator.translate_batch(
                        batch, target_prefix=[[prefix]] * len(batch) if prefix else None,
                        replace_unknowns=True, beam_size=options.beam_size, length_penalty=0.2,
                        max_batch_size=options.batch_tokens, batch_type="tokens",
                        max_input_length=0, max_decoding_length=options.max_decoding_length)

                def decode(tokens):
                    if prefix and tokens and tokens[0] == prefix:
                        tokens = tokens[1:]
                    return pkg.tokenizer.decode(tokens).strip()

                text = translate_segments(text, pair[1], pkg.tokenizer.encode, decode, infer, options, cancelled)
            return BackendOutput(text, tuple(ids))

    def _unload_translators(self) -> None:
        for translator in self._translators.values():
            translator.unload_model(to_cpu=False)
        self._translators.clear()
        if self._packages:
            for pkg, record in self._packages.values():
                self.models.states[record.id] = ModelState.AVAILABLE
        self._options = None

    def shutdown(self) -> None:
        with _ARGOS_LOCK:
            self._unload_translators()
            self._packages = None  # also releases official tokenizer processors
            gc.collect()
