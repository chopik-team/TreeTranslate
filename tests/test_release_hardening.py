from threading import Event
from types import SimpleNamespace

import pytest

from app.engine.backends.text_segments import translate_segments
from app.engine.types import InferenceOptions
from tools.qa_release_quality import hard_checks, numeric_atoms
from app.engine.output_validation import checked_output
from app.engine.errors import TranslationError


def test_question_boundary_keeps_following_prohibition_and_original_whitespace():
    seen=[]
    def infer(batch):
        seen.extend(''.join(x) for x in batch)
        return [SimpleNamespace(hypotheses=[x]) for x in batch]
    options=InferenceOptions('cpu','int8',1,1,192,192,512)
    source='Dr. Smith checked 12.5 mm?  Do not start!\tKeep closed.\n\nNext.'
    result=translate_segments(source,'en',list,''.join,infer,options,Event(),question_boundaries=True)
    assert result==source
    assert seen==['Dr. Smith checked 12.5 mm?','Do not start!','Keep closed.','Next.']


def test_quality_invariants_catch_lost_prohibition_without_rejecting_thousands_separator():
    case={'source':'Did she check both valves yesterday? Do not start the pump.','target_language':'ru','category':'grammar'}
    assert not hard_checks(case,'Она проверила оба клапана вчера?')['pump_prohibition_present']
    assert hard_checks(case,'Она проверила оба клапана вчера? Не запускайте насос.')['pump_prohibition_present']
    assert numeric_atoms('1 250 and 12.5')==numeric_atoms('1,250 and 12.5')
    assert numeric_atoms('1 250')!=numeric_atoms('1 251')
    assert numeric_atoms('−20 °C')!=numeric_atoms('20 °C')


@pytest.mark.parametrize('output',['<unk>','__ru__ translated','broken\ufffdtext','broken\x00text','\ud800'])
def test_decoder_artifacts_are_errors(output):
    with pytest.raises(TranslationError):checked_output('Save the file.',output)


def test_literal_case_restore_does_not_invent_missing_files_or_collapse_ambiguous_spellings():
    assert checked_output('run python main.py and open config.json','Запустите Python main.py и Config.json')=='Запустите python main.py и config.json'
    assert checked_output('Open config.json','Откройте файл')=='Откройте файл'
    assert checked_output('Compare foo.py and FOO.py','FOO.py and foo.py')=='FOO.py and foo.py'
    assert checked_output('Explain <unk>','Объяснить <unk>')=='Объяснить <unk>'
    assert checked_output('打开config.json，然后运行python main.py','Config.json Python main.py')=='config.json python main.py'


def test_negative_quantity_guard_does_not_treat_dates_or_ids_as_negative_numbers():
    with pytest.raises(TranslationError):checked_output('限值为−20 °C。','Предел — 20 °C.')
    assert checked_output('−20 °C','минус 20 °C')=='минус 20 °C'
    assert checked_output('−20 °C','Limits are−20 °C')=='Limits are−20 °C'
    assert checked_output('Date 2026-09-28; ITM-20','Дата 2026-09-28; ITM-20')=='Дата 2026-09-28; ITM-20'
    with pytest.raises(TranslationError):checked_output('−20 °C on 2026-09-28','-20 °C')


def test_request_local_duplicate_chunks_keep_every_occurrence_and_order():
    seen=[]
    def infer(batch):
        seen.extend(''.join(x) for x in batch)
        return [SimpleNamespace(hypotheses=[x]) for x in batch]
    options=InferenceOptions('cpu','int8',1,1,192,192,512)
    source='First.\n\nRepeat.\nLast.\nRepeat.\nFirst.'
    for _ in range(2):
        assert translate_segments(source,'en',list,''.join,infer,options,Event())==source
    assert seen==['First.','Repeat.','Last.']*2  # Nothing retained across requests.


def test_close_active_window_waits_cooperatively_without_blocking_gui():
    from test_hybrid_service import SlowEngine, wait_for
    from PySide6.QtWidgets import QApplication
    from app.gui.main_window import MainWindow
    from app.services.hybrid_translation_service import HybridTranslationService
    from app.config.settings import PerformanceSettings
    app=QApplication.instance() or QApplication([])
    engine=SlowEngine();service=HybridTranslationService(engine=engine)
    window=MainWindow(translation_service=service);window.show();app.processEvents()
    service.submit_text('one','en','ru',PerformanceSettings(device='CPU'),'close-test')
    assert engine.entered.wait(2)
    try:
        window.close()
        assert window.isVisible() and not engine.closed
    finally:
        engine.release.set()
    wait_for(lambda:not window.isVisible())
    assert engine.closed


def test_corrupted_output_falls_back_locally_and_cancel_prevents_next_backend():
    from test_router import FakeBackend, FakeDevices, request
    from app.engine.router.translation_router import TranslationRouter
    from app.engine.types import BackendOutput
    from app.engine.errors import TranslationCancelledError
    a=FakeBackend('argos',[('en','ru')]);b=FakeBackend('m2m100',languages=['en','ru'])
    engine=TranslationRouter({'argos':a,'m2m100':b},devices=FakeDevices())
    try:
        a.translate=lambda *args:BackendOutput('<unk>',('fake',))
        result=engine.translate(request())
        assert result.backend=='m2m100' and result.fallback_used
        cancelled=Event();b.calls.clear()
        def cancel(*args):
            cancelled.set()
            return BackendOutput('<unk>',('fake',))
        a.translate=cancel
        with pytest.raises(TranslationCancelledError):engine.translate(request(),cancelled)
        assert not b.calls
    finally:engine.shutdown()


@pytest.mark.parametrize('failure',[PermissionError,OSError])
def test_destination_write_failure_is_safe_user_error(tmp_path,monkeypatch,failure):
    from docx import Document
    from test_document_service import wait_for
    from PySide6.QtWidgets import QApplication
    from app.documents.docx_document import DocxDocument
    from app.documents.control import JobControl
    from app.documents.scanner import scan_sources
    from app.documents.job import DocumentConfig
    from app.services.hybrid_translation_service import HybridTranslationService
    app=QApplication.instance() or QApplication([])
    path=tmp_path/'source.docx';document=Document();document.add_paragraph('Save the file.');document.save(path)
    engine=SimpleNamespace(translate=lambda *args:SimpleNamespace(translated_text='Сохраните файл.'),
                           languages=SimpleNamespace(resolve=lambda *args:('en','ru')),shutdown=lambda:None)
    service=HybridTranslationService(engine=engine);messages=[];service.files.failed.connect(messages.append)
    def fail(*args):raise failure('private filesystem details')
    monkeypatch.setattr(DocxDocument,'write',fail)
    service.files.selected=scan_sources([path],JobControl()).files
    service.files.config=DocumentConfig(source='en',target='ru',output=tmp_path/'output')
    try:
        service.start();wait_for(lambda:not service.files.busy)
        assert messages and all('private' not in m and 'Traceback' not in m for m in messages)
        assert not list((tmp_path/'output').glob('*.docx'))
    finally:service.shutdown()
