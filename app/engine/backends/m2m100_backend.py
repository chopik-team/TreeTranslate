from __future__ import annotations

import gc
import logging
from threading import Event

from app.engine.backends.base_backend import BaseBackend, check_cancelled
from app.engine.backends.text_segments import translate_segments
from app.engine.errors import BackendUnavailableError, DeviceUnavailableError, ModelCorruptedError, ModelMissingError, UnsupportedLanguageError
from app.engine.runtime.model_manager import ModelManager, ModelState
from app.engine.types import BackendCapabilities, BackendOutput, InferenceOptions, PairKind, TranslationRequest

logger = logging.getLogger("treetranslate.engine.m2m100")


class M2M100Backend(BaseBackend):
    name = "m2m100"

    def __init__(self, models: ModelManager) -> None:
        self.models = models
        self._translator = None
        self._tokenizer = None
        self._options = None
        self._record = None

    def capabilities(self) -> BackendCapabilities:
        records = self.models.available(self.name)
        record = next((row for row in records if row.id == "m2m100-418m-int8"), None)
        return BackendCapabilities(languages=frozenset(record.languages) if record else frozenset())

    def _load(self, options: InferenceOptions) -> None:
        if self._translator is not None and self._options == options:
            return
        self.shutdown()
        records = self.models.available(self.name)
        record = next((row for row in records if row.id == "m2m100-418m-int8"), None)
        if record is None:
            raise ModelMissingError()
        self._record = record
        root = self.models.validate(record)
        self.models.states[record.id] = ModelState.LOADING
        try:
            import ctranslate2
            from app.engine.backends.m2m100_tokenizer import LocalM2M100Tokenizer
            self._tokenizer = LocalM2M100Tokenizer(root / "tokenizer")
            self._translator = ctranslate2.Translator(
                str(root / "model"), device=options.device, compute_type=options.compute_type,
                intra_threads=options.threads, inter_threads=1)
        except ImportError as error:
            self.models.states[record.id] = ModelState.ERROR
            logger.error("backend=m2m100 model_id=%s model_state=%s runtime_dependency_missing=%s",
                         record.id, ModelState.ERROR.value, error.name or "unknown")
            raise BackendUnavailableError() from None
        except (RuntimeError, OSError):
            self.models.states[record.id] = ModelState.ERROR
            if options.device == "cuda":
                raise DeviceUnavailableError() from None
            raise ModelCorruptedError() from None
        self._options = options
        self.models.states[record.id] = ModelState.READY

    def translate(self, request: TranslationRequest, kind: PairKind,
                  options: InferenceOptions, cancelled: Event) -> BackendOutput:
        check_cancelled(cancelled)
        if kind != PairKind.DIRECT or not self.supports_pair(request.source_language, request.target_language):
            raise UnsupportedLanguageError()
        self._load(options)
        tokenizer = self._tokenizer
        if not {request.source_language, request.target_language} <= tokenizer.languages:
            raise ModelCorruptedError()

        def infer(batch):
            source = [tokenizer.source_tokens(pieces, request.source_language) for pieces in batch]
            return self._translator.translate_batch(
                source, target_prefix=[[f"__{request.target_language}__"]] * len(source),
                beam_size=options.beam_size, max_batch_size=options.batch_tokens, batch_type="tokens",
                max_input_length=0, max_decoding_length=options.max_decoding_length)

        text = translate_segments(request.text, request.target_language, tokenizer.encode,
                                  tokenizer.decode, infer, options, cancelled)
        return BackendOutput(text, (self._record.id,))

    def shutdown(self) -> None:
        if self._translator is not None:
            self._translator.unload_model(to_cpu=False)
        self._translator = None
        self._tokenizer = None
        self._options = None
        if self._record:
            self.models.states[self._record.id] = ModelState.AVAILABLE
        self._record = None
        gc.collect()
