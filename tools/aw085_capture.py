"""Capture baseline/after from real production ZIP workflow without changing results."""
import sys, json, time, os
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile
ROOT = Path('C:/TreeTranslate'); sys.path.insert(0, str(ROOT))
MODE = sys.argv[1]
QA = ROOT / 'qa/aw085'; QA.mkdir(parents=True, exist_ok=True)
BUILD = ROOT / 'build/aw085-quality'; BUILD.mkdir(parents=True, exist_ok=True)
SOURCE = Path('C:/Users/PC/Downloads/车身尺寸.zip')
os.environ['TREETRANSLATE_TM_PATH']=str(QA/'run-tm.db')
os.environ['TREETRANSLATE_GLOSSARY_PATH']=str(QA/'run-glossary.db')
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QSettings
from app.config.logging_config import configure_logging
from app.services.settings_service import SettingsService
from app.gui.styles.theme import load_stylesheet
from app.documents.pdf_document import PdfDocument
from app.models.translation_job import JobState
import app.gui.main_window as main
configure_logging(); app = QApplication([]); app.setStyleSheet(load_stylesheet())
settings = SettingsService(QSettings(str(BUILD/(MODE+'.ini')), QSettings.Format.IniFormat))
for k,v in {'language/source':'Китайский','language/target':'Русский','performance/device':'Auto',
 'general/output_location':'custom','general/output_path':str(ROOT/'output/aw085'/MODE),
 'general/open_output':False,'general/restore_job':False,'general/output_template':'{name}_{lang}',
 'translation/translate_folders':True,'translation/translate_filenames':True}.items(): settings.save_value(k,v)
main.SettingsService=lambda: settings
documents=[]
original_validate=PdfDocument.validate
def validate(self,path):
    result=original_validate(self,path)
    relative=Path(*self.path.parts[self.path.parts.index('input')+1:]).as_posix()
    documents.append(dict(file=relative,source_pages=len(self.pages),output_pages=len(self.pages)+self.continuation_count,
      segments=[asdict(s) for s in self.segments],output_hash=sha256(Path(path).read_bytes()).hexdigest()))
    return result
PdfDocument.validate=validate
window=main.MainWindow();window.show();service=window.translation_service.files
errors=[];service.failed.connect(errors.append)
started=time.monotonic();before=sha256(SOURCE.read_bytes()).hexdigest()
def wait():
    last=0
    while service.busy:
        app.processEvents();time.sleep(.03)
        if time.monotonic()-last>30:
            p=service.progress;print(MODE,p.stage,p.file_index,p.processed,p.total,round(time.monotonic()-started),flush=True);last=time.monotonic()
        if time.monotonic()-started>3600:service.cancel();raise TimeoutError()
    app.processEvents()
try:
    window.translation.accept_paths([SOURCE]);wait()
    assert service.state==JobState.READY,errors
    window.file_page.start_button.click();wait()
    result=dict(mode=MODE,run=service._run_id,state=service.state.name,errors=errors,documents=documents,
      elapsed=time.monotonic()-started,source_hash_before=before,source_hash_after=sha256(SOURCE.read_bytes()).hexdigest(),
      outputs=[str(p) for p in service.completed_outputs],warnings=list(service.warnings))
    if service.completed_outputs:
        with ZipFile(service.completed_outputs[-1]) as z:
            result['entries']=[dict(name=i.filename,size=i.file_size) for i in z.infolist()]
            result['crc_ok']=z.testzip() is None
    (QA/(MODE+'_segments.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    window.grab().save(str(BUILD/(MODE+'.png')))
    print('RESULT',MODE,result['state'],round(result['elapsed'],2),result['outputs'],flush=True)
finally:window.close()
