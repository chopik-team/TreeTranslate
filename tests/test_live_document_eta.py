import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PySide6.QtCore import QObject

from app.documents.batch_eta import BatchEta
from app.documents.job import DocumentConfig
from app.documents.measurements import bundled_calibration,calibration
from app.documents.scanner import SourceFile
from app.engine.types import DevicePreference
from app.models.translation_job import JobState,TranslationProgress


def test_bundled_measured_speed_and_complexity_are_available_without_user_history():
    rates=bundled_calibration(DocumentConfig())
    assert rates['runs']==['736fc7a72805']
    assert rates['docs_per_hour']==pytest.approx(251.99513190764281)
    assert set(rates['classes'])=={'native','mixed','image_only'}
    assert all(p['segment_seconds']>0 and p['document_page_seconds']>0 for p in rates['classes'].values())
    assert not next(r for r in rates['references'] if r['run_id']=='2bf4fd0f345e')['used_for_rates']
    assert bundled_calibration(DocumentConfig(target='de')) is None
    assert bundled_calibration(DocumentConfig(device=DevicePreference.CPU)) is None


def test_calibration_accepts_original_gpu_cpu_fallback_routes(tmp_path):
    run=dict(state='COMPLETED',elapsed=40,routes=[dict(source='zh',target='ru',device='cuda'),dict(source='zh',target='ru',device='cpu')],
             sources=[dict(segments=20,pages=2,chars=600)],processes=dict(engine_translation=[20],document_write=[4]),ocr=[],run='real',date='2026')
    (tmp_path/'one.json').write_text(json.dumps(run),'utf8')
    rates=calibration(DocumentConfig(device=DevicePreference.GPU),tmp_path)
    assert rates['segment_seconds']==1
    assert rates['write_page_seconds']==2


def test_countdown_keeps_decreasing_when_stage_exceeds_initial_budget():
    control=SimpleNamespace(active_seconds=0)
    eta=BatchEta(dict(segment_seconds=1,write_page_seconds=1,ocr_seconds=2),control)
    eta.files=[dict(extract=10,translate=80,write=10)];eta.begin()
    control.active_seconds=20
    assert eta.remaining()==80  # Old implementation froze at 90 after extract's ten seconds.
    control.active_seconds=25
    assert eta.remaining()==75


def test_each_document_keeps_its_complexity_rate_after_all_extractions():
    rates=bundled_calibration(DocumentConfig());control=SimpleNamespace(active_seconds=0)
    eta=BatchEta(rates,control)
    eta.workloads=[dict(kind='image_only'),dict(kind='native')]
    eta.files=[dict(extract=0,translate=0,write=1) for _ in range(2)]
    eta.extracted(1,1000);eta.extracted(2,100)
    native_budget=eta.files[1]['translate']
    eta.update(TranslationProgress(file_index=1,stage='TRANSLATING',total=1100,processed=1),[.001]*8)
    assert eta.translation_rate<.05
    assert eta.files[0]['translate']==pytest.approx(999*eta.translation_rate)
    assert eta.files[1]['translate']==native_budget
    eta.update(TranslationProgress(file_index=2,stage='TRANSLATING',total=1100,processed=1001),[.3]*8)
    assert eta.translation_rate>.2


def test_archive_1000_member_estimate_does_not_open_any_pdf(monkeypatch):
    rates=bundled_calibration(DocumentConfig())
    control=SimpleNamespace(active_seconds=0,checkpoint=lambda:None)
    eta=BatchEta(rates,control)
    monkeypatch.setattr(eta,'_inspect',lambda *args:pytest.fail('Archive ETA must not open members'))
    files=[SourceFile(Path(f'C:/source.zip/{i}.pdf'),None,Path(f'{i}.pdf'),32768,Path('C:/source.zip')) for i in range(1000)]
    eta.prepare(files,DocumentConfig(),'test');initial=eta.remaining();eta.begin()
    assert initial>1000 and len(eta.files)==1000
    control.active_seconds=7
    assert eta.remaining()==pytest.approx(initial-7)
    eta.update(TranslationProgress(percent=20,stage='TRANSLATING',file_index=10),[])
    remaining=eta.remaining();control.active_seconds=8
    eta.update(TranslationProgress(percent=10,stage='EXTRACTING',file_index=11),[])
    assert eta.remaining()==pytest.approx(remaining-1)  # A prepared child cannot roll back the watermark.
    final=TranslationProgress(percent=100,stage='COMPLETED_WITH_FAILURES')
    eta.update(final,[])
    assert final.eta_seconds==eta.remaining()==0


@pytest.mark.parametrize('calibrated',[False,True])
def test_gui_heartbeat_counts_down_and_freezes_pause_without_new_worker_signals(qt_application,monkeypatch,calibrated):
    from app.services.document_translation_service import DocumentTranslationService
    from app.gui.widgets.progress_panel import ProgressPanel
    monkeypatch.setattr('app.services.document_translation_service.monotonic',lambda:100)
    monkeypatch.setattr('app.gui.widgets.progress_panel.monotonic',lambda:100)
    owner=QObject();owner._closed=False
    service=DocumentTranslationService(owner);service.state=JobState.TRANSLATING
    control=service.control=SimpleNamespace(active_seconds=0,elapsed=0)
    panel=ProgressPanel();panel.set_state(JobState.TRANSLATING)
    service.progress_changed.connect(panel.set_progress)
    if calibrated:
        eta=BatchEta(dict(segment_seconds=1,write_page_seconds=1,ocr_seconds=2),control)
        eta.files=[dict(extract=10,translate=100,write=10)];eta.begin();service._eta_estimator=eta
    else:service._eta_estimator=None
    service._worker_progress(TranslationProgress(percent=1,eta_scope='batch',eta_seconds=120,stage='OCR'))
    qt_application.processEvents()
    for active,expected in [(5,'00:01:55'),(10,'00:01:50'),(30,'00:01:30')]:
        control.active_seconds=control.elapsed=active
        service._tick();qt_application.processEvents()
        assert panel.remaining.text()==expected
    service.state=JobState.PAUSED;panel.set_state(JobState.PAUSED)
    control.elapsed=100;service._tick();qt_application.processEvents()
    assert panel.remaining.text()=='00:01:30'
    service.state=JobState.TRANSLATING;panel.set_state(JobState.TRANSLATING)
    control.active_seconds=35;control.elapsed=105
    service._tick();qt_application.processEvents()
    assert panel.remaining.text()=='00:01:25'
    if not calibrated:
        service._worker_progress(TranslationProgress(percent=40,eta_scope='batch',eta_seconds=200,stage='TRANSLATING'))
        qt_application.processEvents();control.active_seconds=36
        service._tick();qt_application.processEvents()
        assert panel.remaining.text()=='00:03:19'
    panel.set_state(JobState.COMPLETED)
    assert panel.remaining.text()=='00:00:00'
    service.timer.stop()


def test_ready_estimate_stays_static_and_expired_estimate_does_not_claim_completion(qt_application,monkeypatch):
    from app.gui.widgets.progress_panel import ProgressPanel
    monkeypatch.setattr('app.gui.widgets.progress_panel.monotonic',lambda:100)
    panel=ProgressPanel();panel.set_state(JobState.READY)
    panel.set_progress(TranslationProgress(eta_scope='batch',eta_seconds=60,sampled_at=0))
    assert panel.remaining.text()=='00:01:00'
    panel.set_state(JobState.TRANSLATING)
    assert panel.remaining.text()=='Оценка уточняется…'
    panel.set_state(JobState.CANCELLED)
    assert panel.remaining.text()=='—'


def test_pdf_gui_load_estimates_complexity_then_counts_down_to_completion(tmp_path,qt_application,monkeypatch):
    from dataclasses import replace
    from hashlib import sha256
    from app.gui.main_window import MainWindow
    from app.services.hybrid_translation_service import HybridTranslationService
    from test_document_service import make_engine,wait_for
    from tools.pdf_fixtures import make_pdf
    clock={'now':100.}
    monkeypatch.setattr('app.documents.control.monotonic',lambda:clock['now'])
    # Use the saved measured prior, independent of other tests' diagnostic logs.
    monkeypatch.setattr('app.documents.measurements.calibration',bundled_calibration)
    source=make_pdf(tmp_path/'manual.pdf',pages=10,lines=20,image=False)
    digest=sha256(source.read_bytes()).hexdigest()
    engine=make_engine();service=HybridTranslationService(engine=engine)
    window=MainWindow(translation_service=service)
    panel=window.file_page.progress
    def seconds():
        h,m,s=map(int,panel.remaining.text().split(':'))
        return h*3600+m*60+s
    try:
        window.translation.accept_paths([source])
        wait_for(lambda:service.state==JobState.READY)
        wait_for(lambda:panel.remaining.text().count(':')==2)
        assert seconds()>0 and not engine.calls
        assert service.files._eta_preview.workloads[0]['kind']=='native'
        assert service.files._eta_preview.workloads[0]['pages']==10
        service.files.config=replace(service.files.config,output=tmp_path/'output',ocr_enabled=False,
                                     translate_directories=False,translate_filenames=False)
        service.start();wait_for(engine.entered.is_set)
        wait_for(lambda:panel.remaining.text().count(':')==2)
        initial=seconds();assert initial>3
        clock['now']+=2;service.files._tick();qt_application.processEvents()
        assert seconds()==initial-2
        service.pause_or_resume();clock['now']+=20
        service.files._tick();qt_application.processEvents()
        assert seconds()==initial-2
        service.pause_or_resume();clock['now']+=1
        service.files._tick();qt_application.processEvents()
        assert seconds()==initial-3
        engine.release.set()
        wait_for(lambda:service.state in {JobState.COMPLETED,JobState.ERROR},timeout=10000)
        assert service.state==JobState.COMPLETED
        assert panel.remaining.text()=='00:00:00'
        assert panel.output_paths and all(p.is_file() for p in panel.output_paths)
        assert sha256(source.read_bytes()).hexdigest()==digest
    finally:
        engine.release.set();window.close()
