"""Isolated QA adapters using the existing backend contract and segmentation.

Production never imports this module. No Torch, Transformers or hub dependency.
"""
import json
from pathlib import Path
from threading import Event

from app.engine.backends.m2m100_backend import M2M100Backend
from app.engine.backends.m2m100_tokenizer import LocalM2M100Tokenizer
from app.engine.backends.text_segments import translate_segments
from app.engine.backends.base_backend import check_cancelled
from app.engine.errors import ModelMissingError, UnsupportedLanguageError
from app.engine.types import BackendCapabilities, BackendOutput, PairKind

ROOT = Path(__file__).resolve().parents[1]
LANGUAGES = frozenset({'zh','ru','en','de','fr','es','ja'})


class CandidateBackend(M2M100Backend):
    """QA-only candidate: reuses M2M inference and shutdown for same-family model."""
    def __init__(self, model_id):
        from app.engine.runtime.model_manager import ModelManager
        super().__init__(ModelManager(ROOT/'build/aw084/candidates'))
        self.model_id = model_id
        self.root = ROOT/'build/aw084/candidates'/model_id
        self.prepared = json.loads((ROOT/'qa/aw084'/f'{model_id}-prepared.json').read_text('utf-8'))
        self.record = next((r for r in self.models.records if r.id == model_id),None)
        if self.record is None:
            raise ModelMissingError()
        self.root = self.models.path(self.record)

    def capabilities(self):
        return BackendCapabilities(languages=LANGUAGES)

    def _load(self, options):
        if self._translator is not None and self._options == options:
            return
        self.shutdown()
        self.models.validate(self.record)
        import ctranslate2
        if self.model_id.startswith('m2m'):
            self._tokenizer = LocalM2M100Tokenizer(self.root/'tokenizer')
        else:
            import sentencepiece
            self._tokenizer = sentencepiece.SentencePieceProcessor(model_file=str(self.root/'tokenizer/spiece.model'))
        self._translator = ctranslate2.Translator(str(self.root/'model'),device=options.device,
            compute_type=options.compute_type,intra_threads=options.threads,inter_threads=1)
        self._options = options

    def translate(self, request, kind, options, cancelled):
        check_cancelled(cancelled)
        if self.model_id.startswith('m2m'):
            # Existing implementation needs a record only to label its output.
            self._load(options)
            self._record = self.record
            # Parent shutdown uses ModelManager state; adapter overrides it below.
            return super().translate(request,kind,options,cancelled)
        check_cancelled(cancelled)
        if kind != PairKind.DIRECT or not self.supports_pair(request.source_language,request.target_language):
            raise UnsupportedLanguageError()
        self._load(options)
        processor = self._tokenizer
        def infer(batch):
            tag = processor.encode(f'<2{request.target_language}> ',out_type=str)
            return self._translator.translate_batch([tag+pieces+['</s>'] for pieces in batch],
                beam_size=options.beam_size,max_batch_size=options.batch_tokens,batch_type='tokens',
                max_input_length=0,max_decoding_length=options.max_decoding_length)
        def decode(tokens):
            return processor.decode_pieces([t for t in tokens if t not in {'<pad>','</s>','<s>'}]).strip()
        text = translate_segments(request.text,request.target_language,
            lambda s:processor.encode(s,out_type=str),decode,infer,options,cancelled)
        return BackendOutput(text,(self.model_id,))

    def shutdown(self):
        if self._translator is not None:
            self._translator.unload_model(to_cpu=False)
        self._translator = self._tokenizer = self._options = self._record = None
        import gc
        gc.collect()


def backend(model_id):
    if model_id == 'm2m100-418m':
        from app.engine.runtime.model_manager import ModelManager
        return M2M100Backend(ModelManager(ROOT/'vendor/models'))
    return CandidateBackend(model_id)
