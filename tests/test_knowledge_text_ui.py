import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from pathlib import Path
from time import monotonic, sleep
from unittest.mock import Mock
import json
import pytest
from PySide6.QtWidgets import QApplication,QTextBrowser
from PySide6.QtCore import QSettings, QUrl
from PySide6.QtTest import QTest
from app.engine.router.translation_router import TranslationRouter
from app.engine.types import TranslationResult
from app.glossary.engine import GlossaryEngine
from app.glossary.bundled import bundled_paths
from app.translation_memory.engine import TranslationMemoryEngine
from app.translation_memory.knowledge import TranslationKnowledgeEngine
from app.services.hybrid_translation_service import HybridTranslationService
from app.services.settings_service import SettingsService
from app.gui.main_window import MainWindow
from app.gui.dialogs.about_dialog import AboutDialog


def wait_for(predicate):
    deadline=monotonic()+5
    while not predicate() and monotonic()<deadline:
        QApplication.processEvents()
        sleep(.01)  # Let the real SQLite worker reacquire the GIL between Qt events.
    assert predicate()


def test_plain_text_page_domain_bundled_glossary_and_tm_override(tmp_path,monkeypatch):
    app=QApplication.instance() or QApplication([])
    settings=SettingsService(QSettings(str(tmp_path/'settings.ini'),QSettings.Format.IniFormat))
    monkeypatch.setattr('app.gui.main_window.SettingsService',lambda:settings)
    g=GlossaryEngine(tmp_path/'g.db',builtin_paths=bundled_paths());tm=TranslationMemoryEngine(tmp_path/'tm.db')
    router=TranslationRouter({})
    router.translate=Mock(side_effect=lambda r,c:TranslationResult('модель',r.source_language,r.target_language,'fake','cpu',0,'test',False,r.request_id))
    engine=TranslationKnowledgeEngine(router,tm,g)
    window=MainWindow(translation_service=HybridTranslationService(engine=engine));page=window.text_page
    try:
        sample='охлаждающая жидкость и коленчатые валы'
        window.preferences.set_languages('Русский','Китайский')
        page.source.editor.setPlainText(sample);page._translate_timer.stop()
        window.translation.translate_text(sample)
        wait_for(lambda:page.result.editor.toPlainText()=='модель')
        assert not hasattr(page, 'domain_combo')
        assert not hasattr(window.file_page, 'domain_combo')
        assert router.translate.call_args.args[0].domain=='automotive'
        assert settings.value('translation/domain','auto')=='auto'
        calls=router.translate.call_count
        tm.remember_translation(sample,'用户确认的翻译','ru','zh',domain='automotive')
        window.translation.translate_text(sample)
        wait_for(lambda:page.result.editor.toPlainText()=='用户确认的翻译')
        assert page.engine_status.text()=='Перевод завершён'
        assert router.translate.call_count==calls
        assert list(g.repository.rows())==[]
    finally:window.close()


def test_about_license_catalog_and_full_notice_links(monkeypatch):
    opened=Mock(return_value=True)
    monkeypatch.setattr('app.gui.dialogs.about_dialog.QDesktopServices.openUrl',opened)
    app=QApplication.instance() or QApplication([]);dialog=AboutDialog()
    try:
        browser=dialog.findChild(QTextBrowser,'licenseBrowser');text=browser.toPlainText()
        for name in ('PySide6','PaddleOCR','CC0-1.0','CC-BY-SA-4.0','CC-BY-SA-3.0','SIL OFL-1.1','NVIDIA','не определена однозначно'):
            assert name.casefold() in text.casefold()
        assert not browser.openExternalLinks()
        assert browser.document().baseUrl().isLocalFile()
        browser.anchorClicked.emit(QUrl('THIRD_PARTY_NOTICES.md'))
        opened.assert_called_once()
        resolved=opened.call_args.args[0]
        assert resolved.isLocalFile() and Path(resolved.toLocalFile()).is_file()
    finally:dialog.close()


def test_bundled_manifest_paths_and_checksums_fail_closed(tmp_path):
    (tmp_path/'manifest.json').write_text(json.dumps({'version':1,'packs':[{'file':'../outside.db','sha256':'0'*64}]}),'utf-8')
    assert bundled_paths(tmp_path)==()


@pytest.mark.integration
def test_real_text_service_uses_generated_pack(tmp_path):
    from app.engine.factory import create_translation_engine
    from app.config.settings import PerformanceSettings
    app=QApplication.instance() or QApplication([])
    tm=TranslationMemoryEngine(tmp_path/'tm.db')
    g=GlossaryEngine(tmp_path/'g.db',builtin_paths=bundled_paths())
    engine=create_translation_engine(memory=tm,glossary=g)
    service=HybridTranslationService(engine=engine);results=[];errors=[]
    service.text_completed.connect(results.append);service.text_failed.connect(lambda *args:errors.append(args))
    try:
        service.submit_text('更换冷却剂。','Китайский','Русский',PerformanceSettings(),'generated-pack',domain='automotive')
        deadline=monotonic()+40
        while not results and not errors and monotonic()<deadline:
            QApplication.processEvents();sleep(.01)
        assert not errors and results
        assert results[0].constraint_status=='enforced'
        assert 'охлаждающая жидкость' in results[0].translated_text
        assert results[0].domain=='automotive' and results[0].pack_ids
        assert tm.stats()['total_units']==0 and list(g.repository.rows())==[]
    finally:service.shutdown()
