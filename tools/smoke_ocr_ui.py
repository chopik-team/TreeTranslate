"""Actual Qt file-page OCR smoke with isolated preferences and real local models."""
from hashlib import sha256
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from docx import Document
from PySide6.QtCore import QSettings,QTimer,Qt
from PySide6.QtWidgets import QApplication
from app.gui.main_window import MainWindow
from app.gui.styles.theme import load_stylesheet
from app.models.translation_job import JobState
from tools.pdf_fixtures import make_pdf
from tools.ocr_fixtures import rasterize


def main():
    root=Path('build/aw062-ui').resolve();root.mkdir(parents=True,exist_ok=True)
    qa=Path('docs/qa/aw062/ui');qa.mkdir(parents=True,exist_ok=True)
    folder=root/'inputs';folder.mkdir(exist_ok=True)
    native=make_pdf(folder/'native.pdf','Save the configuration file before restarting the application.',lines=3)
    scan=rasterize(native,folder/'scan.pdf')
    word=Document();word.add_paragraph('Save the configuration file.');word.save(folder/'manual.docx')
    hashes={str(p):sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}
    app=QApplication([])
    app.setOrganizationName('CHOPIK Team QA');app.setApplicationName('TreeTranslate AW062 OCR QA')
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(root/'settings'))
    app.setStyleSheet(load_stylesheet())
    window=MainWindow();window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen,True);window.show()
    window.settings.save_value('general/output_location','custom')
    window.settings.save_value('general/output_path',str(root/'outputs'))
    window.preferences.set_languages('Определить автоматически','Русский')
    window.preferences.set_profile('Баланс')
    cases=[('folder','Auto',folder),('pause','CPU',scan),('cancel','GPU',scan)]
    reports=[];errors=[];current={}
    def fail(message):
        errors.append(message);window.translation_service.cancel();QTimer.singleShot(100,window.close)
    def begin():
        if not cases:window.close();return
        name,device,path=cases.pop(0)
        current.clear();current.update(name=name,device=device,acted=False,stages=[])
        window.preferences.set_device(device)
        window.translation_service.files.scan([path])
    def state(state):
        if state==JobState.READY:
            QTimer.singleShot(0,window.file_page.start_button.click)
        if state in (JobState.COMPLETED,JobState.CANCELLED,JobState.ERROR):
            expected=JobState.CANCELLED if current['name']=='cancel' else JobState.COMPLETED
            if state!=expected:fail(f'{current["name"]}: {state.name}');return
            assert hashes=={p:sha256(Path(p).read_bytes()).hexdigest() for p in hashes}
            assert not list((root/'outputs').rglob('.treetranslate-*'))
            if current['name'] in ('pause','cancel'):assert current['acted']
            outputs=window.file_page.progress.output_paths
            if current['name']=='folder':assert len(outputs)==3
            reports.append(dict(current,state=state.name,outputs=[str(p) for p in outputs],source_hashes_unchanged=True))
            def finish():
                window.grab().save(str(qa/(current['name']+'.png')));begin()
            QTimer.singleShot(50,finish)
    def progress(p):
        if p.stage and p.stage not in current['stages']:current['stages'].append(p.stage)
        if p.stage=='OCR' and not current['acted'] and current['name'] in ('pause','cancel'):
            current['acted']=True
            if current['name']=='pause':
                window.file_page.progress.pause.click()
                assert window.translation_service.state==JobState.PAUSED
                window.grab().save(str(qa/'paused.png'))
                QTimer.singleShot(500,window.file_page.progress.pause.click)
            else:window.file_page.progress.cancel.click()
        if p.stage=='OCR':window.grab().save(str(qa/'ocr.png'))
    window.translation_service.state_changed.connect(state)
    window.translation_service.progress_changed.connect(progress)
    window.translation_service.files.failed.connect(fail)
    timeout=QTimer(singleShot=True,interval=300000);timeout.timeout.connect(lambda:fail('timeout'));timeout.start()
    QTimer.singleShot(0,begin);app.exec();timeout.stop()
    (qa/'result.json').write_text(json.dumps(dict(scenarios=reports,errors=errors),ensure_ascii=False,indent=2),'utf-8')
    assert not errors,errors
    assert len(reports)==3
    print('3 actual file-page OCR scenarios passed: mixed folder, pause/resume, cancel')


if __name__=='__main__':main()
