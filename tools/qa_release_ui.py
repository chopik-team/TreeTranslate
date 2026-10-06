"""Local UI startup, real worker heartbeat, memory sequence and cancellation QA."""
from time import perf_counter, sleep
START=perf_counter()
import argparse
import json
import os
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
os.environ['TREETRANSLATE_TM_PATH']=str(ROOT/'build/aw08/qa-tm.db')
os.environ['TREETRANSLATE_GLOSSARY_PATH']=str(ROOT/'build/aw08/qa-glossary.db')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['baseline','final'],required=True);args=parser.parse_args()
    from PySide6.QtCore import QTimer,QSettings
    from PySide6.QtWidgets import QApplication
    from app.gui.main_window import MainWindow
    from app.gui.dialogs.about_dialog import AboutDialog
    from app.gui.dialogs.settings_dialog import SettingsDialog
    from app.config.settings import PerformanceSettings
    from app.documents.job import DocumentConfig
    from app.engine.types import DevicePreference
    from app.gui.styles.theme import load_stylesheet
    import psutil
    app=QApplication([]);app.setOrganizationName('TreeTranslate-AW08-QA');app.setApplicationName('isolated')
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(ROOT/'build/aw08/settings'))
    app.setStyleSheet(load_stylesheet());window=MainWindow();window.show();app.processEvents()
    process=psutil.Process();report={'startup_to_ui_ms':(perf_counter()-START)*1000,'idle_rss_mb':process.memory_info().rss/1024**2,'dialogs':{},'workloads':[]}
    for name,cls in [('about',AboutDialog),('settings',SettingsDialog)]:
        values=[]
        for _ in range(3):
            tick=perf_counter();dialog=cls(window);dialog.show();app.processEvents();values.append((perf_counter()-tick)*1000)
            report['dialogs'][name]={'samples_ms':values,'median_ms':statistics.median(values),'size':[dialog.width(),dialog.height()]}
            dialog.close();dialog.deleteLater();app.processEvents()
    service=window.translation_service;ticks=[];timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(perf_counter()));timer.start()
    def wait_until(predicate,timeout=120):
        start=perf_counter()
        while not predicate():
            if perf_counter()-start>timeout:raise RuntimeError('UI QA timed out')
            app.processEvents();sleep(.002)
        app.processEvents()
    policy=PerformanceSettings(device='GPU',mode='Баланс',unload_model=False)
    for i in range(5):
        ticks.clear();start=perf_counter()
        service.submit_text('Did she check both valves yesterday? Do not start the pump.','en','ru',policy,str(i))
        wait_until(lambda:not service.text_busy)
        report['workloads'].append({'kind':'text','iteration':i,'seconds':perf_counter()-start,'heartbeat_ticks':len(ticks),
                                    'max_heartbeat_gap_ms':max([b-a for a,b in zip(ticks,ticks[1:])],default=0)*1000,
                                    'rss_mb':process.memory_info().rss/1024**2})
    for name,path in [('docx','quality.docx'),('pdf','native.pdf'),('ocr','scan.pdf')]:
        service.scan([ROOT/'build/aw08'/path]);wait_until(lambda:not service.files.busy)
        service.files.config=DocumentConfig(source='en',target='ru',device=DevicePreference.GPU,output=ROOT/'build/aw08'/f'ui-{args.phase}')
        ticks.clear();start=perf_counter();service.start();service.start()  # repeated Start must stay one job
        wait_until(lambda:not service.files.busy)
        report['workloads'].append({'kind':name,'state':str(service.state),'seconds':perf_counter()-start,
                                   'heartbeat_ticks':len(ticks),'max_heartbeat_gap_ms':max([b-a for a,b in zip(ticks,ticks[1:])],default=0)*1000,
                                   'rss_mb':process.memory_info().rss/1024**2})
    service.submit_text(('Save the file before restarting the application. '*40+'\n')*20,'en','ru',policy,'cancel')
    app.processEvents();sleep(.05);start=perf_counter();service.cancel_text();wait_until(lambda:not service.text_busy)
    report['cancel_text_seconds']=perf_counter()-start
    report['rss_after_cancel_mb']=process.memory_info().rss/1024**2
    start=perf_counter();window.close();report['idle_close_seconds']=perf_counter()-start
    report['rss_after_close_mb']=process.memory_info().rss/1024**2
    timer.stop()
    (ROOT/f'docs/qa/aw08/ui-{args.phase}.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
