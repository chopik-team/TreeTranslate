"""Static, offline UI catalogs. Document text never goes through this layer."""
import json
import re
import weakref
from pathlib import Path

LOCALES = {'ru-RU':'Русский', 'en-US':'English (US)', 'en-GB':'English (UK)',
           'de-DE':'Deutsch', 'es-ES':'Español', 'fr-FR':'Français', 'zh-CN':'中文', 'ja-JP':'日本語'}
ROOT = Path(__file__).resolve().parents[2]/'assets/locales'


class Localization:
    def __init__(self):
        self.locale = 'ru-RU'
        self.catalog = {}
        self.templates = []
        self.prefixes = []
        self.widgets = weakref.WeakSet()

    def use(self, locale):
        locale = locale if locale in LOCALES else 'ru-RU'
        self.locale = locale
        path = ROOT/(locale+'.json')
        self.catalog = json.loads(path.read_text('utf-8')) if path.is_file() else {}
        self.templates = []
        self.prefixes = sorted((k for k in self.catalog if not re.search(r'\{\d+\}',k)),key=len,reverse=True)
        for source, target in self.catalog.items():
            if re.search(r'\{\d+\}', source):
                parts = re.split(r'(\{\d+\})',source.strip())
                pattern = ''.join('(.*?)' if re.fullmatch(r'\{\d+\}',p) else re.escape(p) for p in parts)
                self.templates.append((re.compile('^'+pattern+'$',re.S),target.strip()))
        for widget in tuple(self.widgets):
            try:
                widget.retranslate()
            except RuntimeError:
                pass  # Qt may already have deleted a dialog whose Python wrapper remains.

    def text(self, source):
        if not source or self.locale == 'ru-RU':
            return source
        if source in self.catalog:
            return self.catalog[source]
        if source != source.strip():
            return source[:len(source)-len(source.lstrip())]+self.text(source.strip())+source[len(source.rstrip()):]
        for key in self.prefixes:
            if len(key)>1 and source.startswith(key):
                tail=source[len(key):]
                if tail.startswith(': ') or (key.endswith(('.', '!', '?')) and tail.startswith(' ')):
                    return self.catalog[key]+(': '+self.text(tail[2:]) if tail.startswith(': ') else self.text(tail))
        if '\n' in source:
            return '\n'.join(self.text(line) for line in source.split('\n'))
        if source.startswith(('• ', '🔒 ')):
            prefix = source[:2]
            return prefix + self.text(source[2:])
        if ' · ' in source and '<' not in source:
            return ' · '.join(self.text(part) for part in source.split(' · '))
        for pattern,target in self.templates:
            match = pattern.fullmatch(source)
            if match:
                return re.sub(r'\{(\d+)\}',lambda m: match.group(int(m[1])+1),target)
        # Rich labels contain app-owned text nodes; tags, URLs and CSS stay intact.
        if '<' in source and '>' in source:
            return re.sub(r'(^|>)([^<>]+)(?=<|$)',lambda m:m[1]+self.text(m[2]),source)
        # Composite resource captions / safe status fragments. Do not touch paths.
        if ': ' in source and not re.search(r'[\\/]',source):
            return ': '.join(self.catalog.get(part,part) for part in source.split(': '))
        return source


localization = Localization()
def tr(source):
    return localization.text(source)


def saved_locale(settings):
    value = str(settings.value('general/ui_language','ru-RU'))
    aliases = {v:k for k,v in LOCALES.items()}
    return value if value in LOCALES else aliases.get(value,'ru-RU')
