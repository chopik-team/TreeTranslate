"""Suite C uses the real GUI ZIP workflow with an isolated injected QA engine."""
import json
import sys
import time
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
MODE=sys.argv[1];QA=ROOT/'qa/aw084';BUILD=ROOT/'build/aw084/e2e';BUILD.mkdir(parents=True,exist_ok=True)
SOURCE=Path('C:/Users/PC/Downloads/车身尺寸.zip')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from app.config.logging_config import configure_logging
from app.services.settings_service import SettingsService
from app.gui.styles.theme import load_stylesheet
from app.documents.pdf_document import PdfDocument
from app.models.translation_job import JobState
from tools.aw084_production import create
import app.engine.factory as factory
import app.gui.main_window as main
factory.create_translation_engine=lambda *a,**k:create(MODE)
configure_logging();app=QApplication([]);app.setStyleSheet(load_stylesheet())
settings=SettingsService(QSettings(str(BUILD/(MODE+'.ini')),QSettings.Format.IniFormat))
for key,value in {'language/source':'Китайский','language/target':'Русский','performance/device':'Auto',
    'general/output_location':'custom','general/output_path':str(ROOT/'output/aw084'/MODE),
    'general/open_output':False,'general/restore_job':False,'general/output_template':'{name}_{lang}',
    'translation/translate_folders':True,'translation/translate_filenames':True}.items():settings.save_value(key,value)
main.SettingsService=lambda:settings
documents=[];original=PdfDocument.validate
def validate(self,path):
    result=original(self,path)
    relative=Path(*self.path.parts[self.path.parts.index('input')+1:]).as_posix()
    documents.append({'file':relative,'source_pages':len(self.pages),'output_pages':len(self.pages)+self.continuation_count,
                      'segments':[asdict(s) for s in self.segments],'output_hash':sha256(Path(path).read_bytes()).hexdigest()})
    return result
PdfDocument.validate=validate
window=main.MainWindow();service=window.translation_service.files
errors=[];service.failed.connect(errors.append)
started=time.monotonic();before=sha256(SOURCE.read_bytes()).hexdigest()
def wait():
    last=0
    while service.busy:
        app.processEvents();time.sleep(.03)
        if time.monotonic()-last>30:
            progress=service.progress
            print(MODE,progress.stage,progress.file_index,progress.processed,progress.total,round(time.monotonic()-started),flush=True)
            last=time.monotonic()
        if time.monotonic()-started>1800:service.cancel();raise TimeoutError()
    app.processEvents()
try:
    window.translation.accept_paths([SOURCE]);wait()
    assert service.state==JobState.READY,errors
    window.file_page.start_button.click();wait()
    result={'mode':MODE,'run':service._run_id,'state':service.state.name,'errors':errors,'documents':documents,
            'elapsed':time.monotonic()-started,'source_hash_before':before,'source_hash_after':sha256(SOURCE.read_bytes()).hexdigest(),
            'outputs':[str(p) for p in service.completed_outputs],'warnings':list(service.warnings)}
    if service.completed_outputs:
        with ZipFile(service.completed_outputs[-1]) as archive:
            result['entries']=[{'name':i.filename,'size':i.file_size} for i in archive.infolist()]
            result['crc_ok']=archive.testzip() is None
    (QA/(MODE+'_segments.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    print('RESULT',result['state'],result['run'],result['elapsed'],result['outputs'],flush=True)
finally:window.close()
