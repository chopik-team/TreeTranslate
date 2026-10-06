"""Render existing Qt pages and inspect live locale changes without user data."""
import json
import os
from pathlib import Path
import re
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
if sys.platform != 'win32':
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')


def main():
    from PySide6.QtWidgets import QApplication,QLabel,QAbstractButton,QTextBrowser
    from PySide6.QtCore import QSettings,Qt
    from app.localization import LOCALES,localization
    from app.gui.main_window import MainWindow
    from app.gui.dialogs.settings_dialog import SettingsDialog
    from app.gui.dialogs.about_dialog import AboutDialog
    from app.gui.styles.theme import load_stylesheet
    from app.services.settings_service import SettingsService
    from app.services.mock_translation_service import MockTranslationService
    from app.models.translation_job import JobState,TranslationProgress
    import app.gui.main_window as main_module
    app=QApplication.instance() or QApplication([])
    app.setStyleSheet(load_stylesheet())
    out=ROOT/'docs/qa/aw082';out.mkdir(parents=True,exist_ok=True)
    settings=SettingsService(QSettings(str(ROOT/'build/aw082/ui.ini'),QSettings.Format.IniFormat))
    main_module.SettingsService=lambda:settings
    rows=[]
    window=MainWindow(translation_service=MockTranslationService())
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen,True);window.show()
    dialog=SettingsDialog(window,settings,window.preferences)
    dialog.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen,True);dialog.show()
    about=AboutDialog(window)
    about.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen,True)
    try:
        for locale,label in LOCALES.items():
            dialog._change_locale(label);app.processEvents()
            residual=[]
            for widget in [window,dialog,about]:
                for child in widget.findChildren(QLabel)+widget.findChildren(QAbstractButton):
                    if re.search('[А-Яа-я]',child.text()):residual.append(child.text())
            rows.append({'locale':locale,'title':dialog.windowTitle(),'cyrillic_labels':sorted(set(residual))})
            if locale in ('ru-RU','en-US','de-DE','zh-CN'):
                for index,name in ((0,'general'),(2,'device'),(3,'interface')):
                    dialog.sections.setCurrentRow(index);app.processEvents()
                    dialog.grab().save(str(out/f'{locale}-settings-{name}.png'))
                window.stack.setCurrentIndex(1);app.processEvents()
                window.grab().save(str(out/f'{locale}-text.png'))
                window.stack.setCurrentIndex(0);app.processEvents()
                window.grab().save(str(out/f'{locale}-files.png'))
        localization.use('en-US');about.show();app.processEvents()
        about.grab().save(str(out/'en-US-about.png'))
        (out/'locale-render.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:about.close();dialog.close();window.close()


if __name__=='__main__':main()
