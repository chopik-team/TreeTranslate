"""Archive startup and persistent-backend regression, not translation quality."""
from dataclasses import replace
from threading import Event
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from app.documents.control import JobControl
from app.documents.job import DocumentConfig, DocumentJob
from app.documents.scanner import scan_sources
from app.engine.errors import DeviceUnavailableError, ModelCorruptedError, TranslationCancelledError, TranslationError
from app.engine.runtime.runtime_manager import RuntimeManager
from app.engine.types import PairKind
from app.engine.router.translation_router import TranslationRouter
from app.engine.router.routing_policy import RoutingPolicy
from test_router import FakeBackend, FakeDevices, request
from test_zip_output import docx_bytes


def test_thousand_members_start_first_child_without_eager_path_translation(tmp_path, monkeypatch):
    source = tmp_path / 'archive.zip'
    with ZipFile(source, 'w') as archive:
        # Directory records all precede documents, as in real ZIP producers.
        for i in range(1000):
            archive.writestr(f'目录{i}/', b'')
        for i in range(1000):
            archive.writestr(f'目录{i}/文件.docx', docx_bytes())
    control = JobControl()
    scanned = scan_sources([source], control)
    calls = []
    def translate(req, cancel):
        calls.append(req)
        return SimpleNamespace(translated_text='Имя')
    original = DocumentJob.run
    entered = []
    def child(job):
        if job.destination_override:
            entered.append(job.files[0].relative.as_posix())
            assert not calls  # Not even the first filename/folder is pretranslated.
            assert not tuple(job.config.output.rglob('*'))
            control.cancel()
            control.checkpoint()
        return original(job)
    monkeypatch.setattr(DocumentJob, 'run', child)
    config = DocumentConfig(source='zh', target='ru', translate_filenames=True, translate_directories=True)
    with pytest.raises(TranslationCancelledError):
        DocumentJob(scanned.files, config, control, translate, lambda *args: ('zh', 'ru')).run()
    assert entered == ['目录0/文件.docx']
    assert list(tmp_path.iterdir()) == [source]


def test_archive_component_cache_shared_across_children(tmp_path):
    source = tmp_path / 'archive.zip'
    with ZipFile(source, 'w') as archive:
        for folder in ('甲', '乙'):
            archive.writestr(folder + '/通用/名称.docx', docx_bytes())
    control = JobControl()
    calls = []
    def translate(req, cancel):
        if req.segment_type in {'FILENAME', 'FOLDER_NAME'}:
            calls.append((req.segment_type, req.text))
        return SimpleNamespace(translated_text='Перевод')
    config = DocumentConfig(source='zh', target='ru', translate_filenames=True, translate_directories=True)
    output, = DocumentJob(scan_sources([source], control).files, config, control, translate,
                          lambda *args: ('zh', 'ru')).run()
    assert calls.count(('FOLDER_NAME', '通用')) == 1
    assert calls.count(('FILENAME', '名称')) == 1
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert sum(name.endswith('.docx') for name in archive.namelist()) == 2


def test_warm_run_keeps_backends_loaded_across_fallback_switches():
    backends = {name: FakeBackend(name) for name in ('argos', 'm2m100')}
    runtime = RuntimeManager(backends, idle_timeout_seconds=0)
    options = FakeDevices().options('cpu', RoutingPolicy().profile(request().performance_profile))[0]
    try:
        with runtime.keep_warm():
            for _ in range(10):
                for name in backends:
                    runtime.run(name, request(), PairKind.DIRECT, options, Event())
            assert [b.loads for b in backends.values()] == [1, 1]
            assert all(b.loaded for b in backends.values())
            runtime.release_models()  # Existing OCR memory boundary still works.
            assert all(not b.loaded for b in backends.values())
    finally:
        runtime.shutdown()


@pytest.mark.parametrize('failure', [DeviceUnavailableError, ModelCorruptedError])
def test_run_circuit_breaker_skips_deterministic_failures_and_resets(failure):
    argos = FakeBackend('argos', [('en', 'ru')])
    m2m = FakeBackend('m2m100', languages={'en', 'ru'})
    def fail(req, kind, options, cancelled):
        argos.calls.append((req, kind, options))
        raise failure()
    argos.translate = fail
    router = TranslationRouter({'argos': argos, 'm2m100': m2m}, devices=FakeDevices())
    try:
        with router.runtime.keep_warm():
            for i in range(100):
                result = router.translate(replace(request(), text=f'Input {i}.'))
                assert result.backend == 'm2m100' and result.fallback_used
            assert len(argos.calls) == 1
            assert m2m.loads == 1
        with router.runtime.keep_warm():
            router.translate(request())
        assert len(argos.calls) == 2
    finally:
        router.shutdown()


def test_input_specific_failure_does_not_open_backend_circuit():
    argos = FakeBackend('argos', [('en', 'ru')])
    m2m = FakeBackend('m2m100', languages={'en', 'ru'})
    translate = argos.translate
    def sometimes(req, *args):
        if req.text == 'bad input':
            raise TranslationError()
        return translate(req, *args)
    argos.translate = sometimes
    router = TranslationRouter({'argos': argos, 'm2m100': m2m}, devices=FakeDevices())
    try:
        with router.runtime.keep_warm():
            assert router.translate(replace(request(), text='bad input')).backend == 'm2m100'
            assert router.translate(request()).backend == 'argos'
    finally:
        router.shutdown()


def test_m2m_inference_options_do_not_reload_model(monkeypatch):
    from app.engine.backends.m2m100_backend import M2M100Backend
    backend = M2M100Backend(SimpleNamespace())
    options = FakeDevices().options('cpu', RoutingPolicy().profile(request().performance_profile))[0]
    model = backend._translator = object()
    backend._options = options
    monkeypatch.setattr(backend, 'shutdown', lambda: pytest.fail('model reloaded for inference-only options'))
    changed = replace(options, beam_size=options.beam_size + 1, max_decoding_length=99, batch_tokens=77)
    backend._load(changed)
    assert backend._translator is model and backend._options == changed


def test_lightweight_names_use_existing_glossary_and_protect_tokens(tmp_path, monkeypatch):
    from app.glossary.bundled import bundled_paths
    from app.glossary.engine import GlossaryEngine
    from app.translation_memory.knowledge import TranslationKnowledgeEngine
    argos = FakeBackend('argos', [('zh', 'ru')])
    router = TranslationRouter({'argos': argos}, devices=FakeDevices())
    memory = SimpleNamespace(lookup=lambda *args: pytest.fail('filename entered TM'))
    glossary = GlossaryEngine(tmp_path / 'user.db', builtin_paths=bundled_paths())
    engine = TranslationKnowledgeEngine(router, memory, glossary)
    monkeypatch.setattr(engine, '_template', lambda *args: pytest.fail('filename entered semantic templates'))
    monkeypatch.setattr(engine, 'profile_document', lambda *args, **kw: pytest.fail('filename entered profiler'))
    monkeypatch.setattr(engine, '_ensure_safe', lambda *args: pytest.fail('filename entered full prose guards'))
    try:
        from app.engine.types import TranslationRequest
        name = TranslationRequest('散热器盖', 'zh', 'ru', domain='automotive', segment_type='FILENAME')
        assert engine.translate_path(name).translated_text == 'Крышка радиатора'
        assert not argos.calls
        result = engine.translate_path(replace(name, text='CN7C 2022 散热器盖'))
        assert result.translated_text == 'CN7C 2022 Крышка радиатора'
        assert not argos.calls
    finally:
        engine.shutdown()
