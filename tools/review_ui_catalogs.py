"""Apply versioned editorial overrides to static UI catalogs; no inference."""
import json
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[1]


def main():
    rows=[line.split('|') for line in (ROOT/'tools/ui_catalog_review.tsv').read_text('utf-8').splitlines() if line]
    assert all(len(row)==7 for row in rows)
    for i,locale in enumerate(('en-US','de-DE','es-ES','fr-FR','zh-CN','ja-JP')):
        path=ROOT/'assets/locales'/f'{locale}.json'
        values=json.loads(path.read_text('utf-8'))
        for row in rows:
            values[row[0]]=row[i+1]
            for key in list(values):
                if key.strip()==row[0]:
                    values[key]=key[:len(key)-len(key.lstrip())]+row[i+1]+key[len(key.rstrip()):]
        values['Документы .DOCX и .PDF\nПапки проверяются вместе с вложенными каталогами'] = (
            values['Документы .DOCX и .PDF']+'\n'+values['Папки проверяются вместе с вложенными каталогами'])
        # These are developer regexes, not user-facing messages.
        for key in list(values):
            if key.startswith('(?') or '\\b' in key or '<unk>' in values[key]:
                if key.startswith('Добавлены WordNet'):
                    values[key]={'zh-CN':'已添加 WordNet 和 OpenRussian：147 765 个英语词条和 45 238 个俄语词条。'}.get(locale,values[key].replace('<unk>',''))
                else:values.pop(key)
        path.write_text(json.dumps(values,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        if locale=='en-US':
            british={k:v.replace('Licenses','Licences').replace('licenses','licences').replace('Cancelled','Cancelled') for k,v in values.items()}
            (path.parent/'en-GB.json').write_text(json.dumps(british,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    keys=set(json.loads((ROOT/'assets/locales/en-US.json').read_text('utf-8')))
    (ROOT/'assets/locales/ru-RU.json').write_text(json.dumps({k:k for k in sorted(keys)},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
