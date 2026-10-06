"""AW0.8.2 functional checks, not a benchmark or profile competition."""
import argparse
from dataclasses import asdict
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from threading import Event,Thread
from time import monotonic,sleep

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
BUILD=ROOT/'build/aw082';QA=ROOT/'docs/qa/aw082'


def wait(predicate, app=None, timeout=60):
    deadline=monotonic()+timeout
    while not predicate() and monotonic()<deadline:
        if app:app.processEvents()
        sleep(.01)
    assert predicate()


def restart_worker(locale,phase):
    from PySide6.QtCore import QSettings,Qt
    from PySide6.QtWidgets import QApplication
    from docx import Document
    from types import SimpleNamespace
    from app.engine.types import TranslationResult
    from app.services.settings_service import SettingsService
    from app.services.hybrid_translation_service import HybridTranslationService
    from app.gui.main_window import MainWindow
    from app.gui.dialogs.settings_dialog import SettingsDialog
    from app.localization import LOCALES,localization
    from app.models.translation_job import JobState
    import app.gui.main_window as main_module
    app=QApplication([])
    settings=SettingsService(QSettings(str(BUILD/f'restart-{locale}.ini'),QSettings.Format.IniFormat))
    main_module.SettingsService=lambda:settings
    class Engine:
        entered=Event();release=Event();calls=0
        languages=SimpleNamespace(resolve=lambda *a:('en','ru'))
        def translate(self,r,c):
            self.calls+=1;self.entered.set();self.release.wait(10)
            return TranslationResult('Тест', 'en','ru','test','cpu',0,'test',False,r.request_id)
        def shutdown(self):pass
    engine=Engine();service=HybridTranslationService(engine=engine)
    window=MainWindow(translation_service=service)
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen,True)
    source=BUILD/f'restart-{locale}.docx'
    try:
        if phase=='write':
            doc=Document();doc.add_paragraph('The technician opened the door.');doc.save(source)
            settings.save_value('general/restore_job',True)
            settings.save_value('interface/eta',False)
            settings.save_value('interface/detailed_progress',False)
            dialog=SettingsDialog(window,settings,window.preferences)
            dialog._change_locale(LOCALES[locale]);dialog.close()
            window.translation.accept_paths([source]);wait(lambda:service.state==JobState.READY,app)
            window.translation._start_translation();wait(engine.entered.is_set,app)
            window.close();engine.release.set();wait(lambda:not service.files.busy,app)
            window.close();settings.sync()
            assert settings.unfinished_job_paths()==(source.resolve(),)
        else:
            engine.release.set();window.show();wait(lambda:service.state==JobState.READY,app)
            assert localization.locale==locale
            assert window.file_page.file_tree.selected_paths()==[source.resolve()]
            assert engine.calls==0
            assert window.file_page.progress.remaining.isHidden() and window.file_page.progress.current.isHidden()
        print(json.dumps({'locale':locale,'phase':phase,'passed':True}))
    finally:engine.release.set();window.close()


def main():
    BUILD.mkdir(parents=True,exist_ok=True);QA.mkdir(parents=True,exist_ok=True)
    parser=argparse.ArgumentParser();parser.add_argument('--restart',nargs=2);args=parser.parse_args()
    if args.restart:return restart_worker(*args.restart)
    os.environ['TREETRANSLATE_TM_PATH']=str(BUILD/'smoke-tm.db')
    os.environ['TREETRANSLATE_GLOSSARY_PATH']=str(BUILD/'smoke-glossary.db')
    from app.localization import LOCALES
    report={'restart':[],'devices':[],'documents':[]}
    for locale in LOCALES:
        for phase in ('write','read'):
            run=subprocess.run([sys.executable,'-X','utf8',__file__,'--restart',locale,phase],
                cwd=ROOT,capture_output=True,text=True,encoding='utf-8',timeout=45,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            assert run.returncode==0,run.stderr
            report['restart'].append(json.loads(run.stdout))
        print('restart',locale,'OK',flush=True)
    from app.engine.factory import create_translation_engine
    from app.engine.types import TranslationRequest,DevicePreference
    from app.engine.errors import TranslationCancelledError
    from app.documents.job import DocumentConfig,DocumentJob
    from app.documents.control import JobControl
    from app.documents.scanner import scan_sources
    from app.services.hardware_profile_service import HardwareProfileService
    from app.engine.runtime.device_manager import DeviceManager
    from app.ocr.router.ocr_router import OcrRouter
    import socket
    network=[]
    def deny(*a,**k):network.append(True);raise RuntimeError('offline QA')
    socket.getaddrinfo=deny;socket.create_connection=deny
    engine=create_translation_engine()
    try:
        report['hardware']=asdict(HardwareProfileService().detect())
        report['hardware']['cuda_available']=DeviceManager().gpu_available()
        for device in DevicePreference:
            result=engine.translate(TranslationRequest('Do not start the pump before the valve is open.','en','ru',device,domain='auto'))
            report['devices'].append({'requested':device.value,'actual':result.device,'backend':result.backend,
                'compute_type':result.compute_type,'fallback_used':result.fallback_used,'domain':result.domain,
                'output':result.translated_text})
        ocr=[];original=OcrRouter.recognize
        def recognize(self,request):
            result=original(self,request)
            ocr.append({'backend':result.backend,'device':result.device,'network_attempts':result.timings['network_attempts']})
            return result
        OcrRouter.recognize=recognize
        for kind,name in [('docx','quality.docx'),('native_pdf','native.pdf'),('ocr_pdf','scan.pdf')]:
            source=ROOT/'build/aw08'/name
            assert source.is_file(),'AW0.8 fixture required'
            digest=sha256(source.read_bytes()).hexdigest();control=JobControl()
            config=DocumentConfig(source='en',target='ru',output=BUILD/'smoke-output',domain='auto')
            job=DocumentJob(scan_sources([source],control).files,config,control,engine.translate,engine.languages.resolve,
                before_ocr=engine.runtime.release_models)
            outputs=job.run()
            assert outputs and all(p.is_file() for p in outputs)
            assert digest==sha256(source.read_bytes()).hexdigest()
            report['documents'].append({'kind':kind,'completed':True,'source_unchanged':True,
                'domain':[asdict(e) for e in job.detected_domains],'outputs':[str(p) for p in outputs]})
            print(kind,'OK',flush=True)
        # Actual document translation paused at a cooperative segment boundary,
        # then resumed; cancellation uses the same existing checkpoint contract.
        source=ROOT/'build/aw08/quality.docx'
        for cancel in (False,True):
            control=JobControl();paused=Event();finished=Event();errors=[]
            def progress(p):
                if p.processed>=1 and not paused.is_set():control.pause();paused.set()
            job=DocumentJob(scan_sources([source],control).files,
                DocumentConfig(source='en',target='ru',domain='auto',output=BUILD/('cancel' if cancel else 'resume')),
                control,engine.translate,engine.languages.resolve,progress)
            def work():
                try:job.run()
                except Exception as e:errors.append(type(e).__name__)
                finally:finished.set()
            thread=Thread(target=work);thread.start();wait(paused.is_set)
            assert not finished.is_set()
            if cancel:control.cancel()
            else:control.resume()
            wait(finished.is_set);thread.join()
            assert errors==(['TranslationCancelledError'] if cancel else [])
            if cancel:assert not job.completed
            report['cancel' if cancel else 'pause_resume']='passed'
        report['ocr']=ocr;report['network_attempts']=len(network)
        assert not network
    finally:engine.shutdown()
    (QA/'real-smoke.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
