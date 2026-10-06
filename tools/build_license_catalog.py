"""Build a local, readable license index from the actual pinned notices."""
from html import escape
import importlib.metadata as metadata
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]


def build():
    target=ROOT/'assets/licenses';target.mkdir(parents=True,exist_ok=True)
    sections=[]
    python_license=Path(sys.base_prefix)/'LICENSE.txt'
    saved_python_license=ROOT/'vendor/licenses/Python/LICENSE.txt'
    if python_license.is_file() and not saved_python_license.exists():
        saved_python_license.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(python_license,saved_python_license)
    runtime=[]
    names=[]
    for line in (ROOT/'requirements-runtime-lock.txt').read_text('utf-8').splitlines():
        if '==' in line and not line.startswith('#'):names.append(line.split('==')[0])
    names.extend(['argostranslate','nvidia-cublas-cu12','nvidia-cuda-nvrtc-cu12'])
    known={'argostranslate':'MIT','langid':'BSD-3-Clause','sacremoses':'MIT','colorama':'BSD-3-Clause',
           'pypdfium2':'Apache-2.0 OR BSD-3-Clause; PDFium и native notices отдельно',
           'lxml':'BSD-3-Clause; libxml2/libxslt notices отдельно'}
    for name in names:
        try:d=metadata.distribution(name)
        except metadata.PackageNotFoundError:continue
        value=known.get(name) or d.metadata.get('License-Expression') or d.metadata.get('License') or 'См. полный текст лицензии'
        if len(value)>240:value='См. полный текст лицензии (метаданные содержат полный текст)'
        if name.startswith('nvidia-'):value='NVIDIA proprietary license — отдельные условия CUDA'
        runtime.append((name,d.version,value))
        # Save wheel notices missing from the previous inventory; never overwrite existing files.
        for file in d.files or ():
            if '.dist-info/' in str(file) and ('license' in str(file).lower() or 'copying' in str(file).lower()):
                source=Path(d.locate_file(file))
                if source.is_file():
                    destination=ROOT/'vendor/licenses'/name/'wheel-notices'/Path(str(file).split('.dist-info/',1)[1])
                    if not destination.exists():destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,destination)
    sections.append(('Основное окружение',runtime))
    ocr=[]
    for row in json.loads((ROOT/'vendor/licenses/ocr-runtime/inventory.json').read_text('utf-8')):
        value=row.get('license')
        if not value or value=='UNKNOWN':
            values=[v.rsplit(' :: ',1)[-1] for v in row.get('classifiers',[]) if v.startswith('License ::')]
            value=' / '.join(values) or 'См. сохранённые LICENSE/NOTICE'
        if len(value)>240:value='См. полный текст лицензии'
        ocr.append((row['name'],row['version'],value))
    sections.append(('Изолированное окружение OCR — зависимости Paddle',ocr))
    models=[('M2M100 418M INT8','локальная конвертация','MIT по официальной карточке Meta; исходный fairseq LICENSE сохранён'),
            ('Argos EN→RU / RU→EN','1.9','Лицензия итоговых весов не определена однозначно; MIT программы не заменяет лицензию модели'),
            ('Argos ZH→EN / EN→ZH','1.9','CC-BY-4.0 для исходных OPUS моделей по README; отдельные package-wide условия не сформулированы')]
    for row in json.loads((ROOT/'vendor/model-metadata/ocr/models_manifest.json').read_text('utf-8'))['models']:
        models.append((row['id'],row['version'][:12],'Apache-2.0 по отдельной model card'))
    sections.append(('Веса моделей',models))
    sections.append(('Данные, шрифт и изображения',[
        ('FreeDict / WikDict EN↔RU','2025.11.23','CC-BY-SA-3.0 Unported; Karl Bartel / Wiktionary contributors via DBnary. TEI → SQLite, изменённые ключи поиска; производная база сохраняет CC-BY-SA-3.0'),
        ('Princeton WordNet','3.0','WordNet 3.0 License; определения, synsets и примеры преобразованы в общую SQLite'),
        ('OpenRussian','revision 50e210c','CC-BY-SA-4.0; OpenRussian.org contributors; леммы, формы и английские эквиваленты'),
        ('Tatoeba EN/RU examples','26.09.2026','CC-BY-2.0-FR; автор и sentence ID сохранены, записи отфильтрованы и ранжированы'),
        ('Учебные примеры TreeTranslate','assets/language/usage.json','CC0-1.0; собственные иллюстративные примеры'),
        ('TreeTranslate Sans / Noto Sans SC','статический экземпляр 400','SIL OFL-1.1; переименованный производный шрифт, embedding/subsetting'),
        ('Python','3.12.13','PSF License Agreement и включённые сторонние notices'),
        ('SQLite','в Python','Public domain; https://sqlite.org/copyright.html'),
        ('Иконки Flaticon / Icons8 / TreeTranslate Icon Pack','','Условия конкретных ресурсов; сохранён документ лицензии DOCX/PDF. Полный перечень авторов и прав остальных иконок в проекте пока не подтверждён.')]))
    catalog=json.loads((ROOT/'tools/knowledge_harvester/source_catalog.json').read_text('utf-8'))
    sections.append(('Источники Knowledge Harvester — developer/build, не автоматические runtime-загрузки',[
        (name,'проверка '+value['license_checked_at'],value['license']+' · '+value['redistribution_status']+' · '+value['attribution']) for name,value in catalog.items()]))
    sections.append(('Только подготовка и тестирование',[
        ('Transformers','4.57.6','Apache-2.0'),('PyTorch','2.10.0','BSD-style и bundled notices'),
        ('pytest','9.1.1','MIT'),('psutil','7.2.2','BSD-3-Clause'),('pypdf','6.19.0','BSD-3-Clause'),('Pillow','12.3.0','MIT-CMU; также используется в OCR environment')]))
    bundled=ROOT/'assets/knowledge/manifest.json'
    if bundled.is_file():
        packs=json.loads(bundled.read_text('utf-8'))['packs']
        pack_attribution={}
        for p in packs:
            sources={}
            with (ROOT/'assets/knowledge'/p['notice']).open(encoding='utf-8') as stream:
                for line in stream:
                    row=json.loads(line)
                    if 'sources' in row:sources.update(row['sources'])
            pack_attribution[p['pack_id']]='; '.join(sorted({s['attribution'] for s in sources.values()}))
        sections.append(('Встроенные терминологические пакеты — предварительная версия',[
            (p['pack_id'],str(p['entries'])+' терминов',p['license']+' · '+pack_attribution[p['pack_id']]+' Отбор и нормализация TreeTranslate; автоматические проверки не гарантируют перевод.') for p in packs]))
    html=['<h2>Лицензии и источники</h2><p>Лицензии программы, весов моделей, словарей и изображений различаются. Ниже — сведения из закреплённых metadata и сохранённых notices; названия не заменяют полные условия.</p>',
          '<p><a href="THIRD_PARTY_NOTICES.md">Общий файл THIRD_PARTY_NOTICES</a> · <a href="assets/icons/document-icons-license.pdf">Документ лицензии иконок</a> · <a href="assets/fonts/OFL-NotoSansSC.txt">Лицензия шрифта</a></p>',
          '<p>Qt for Python: установленные wheels декларируют LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only; также доступна отдельная коммерческая лицензия Qt. Условия зависят от выбранных модулей и способа распространения. <a href="https://doc.qt.io/qtforpython-6/licenses.html">Официальные условия Qt</a>.</p>']
    for title,rows in sections:
        html.append('<h3>'+escape(title)+'</h3><table cellspacing="8">')
        for name,version,license_name in rows:
            html.append('<tr><td><b>'+escape(name)+'</b> '+escape(version)+'</td><td>'+escape(license_name)+'</td></tr>')
        html.append('</table>')
    html.append('<h3>Полные тексты и атрибуция</h3><p>Включая транзитивные зависимости, native PDFium/NumPy notices и дополнения OCR.</p>')
    for path in sorted((ROOT/'vendor/licenses').rglob('*')):
        if path.is_file():
            relative=path.relative_to(ROOT).as_posix()
            html.append('<p><a href="'+escape(relative,quote=True)+'">'+escape(relative)+'</a></p>')
    for path in sorted((ROOT/'tools/knowledge_harvester/license-texts').glob('*.txt')):
        relative=path.relative_to(ROOT).as_posix();html.append('<p><a href="'+relative+'">'+path.stem+'</a></p>')
    for name,value in catalog.items():
        html.append('<p>'+escape(name)+': <a href="'+escape(value['license_url'],quote=True)+'">условия источника</a></p>')
    if bundled.is_file():
        html.append('<h3>Происхождение встроенных терминов</h3>')
        for p in packs:
            html.append('<p><a href="assets/knowledge/'+escape(p['notice'],quote=True)+'">'+escape(p['pack_id'])+' — NOTICE / источники</a></p>')
    (target/'third-party.html').write_text('\n'.join(html),'utf-8')
    (target/'catalog.json').write_text(json.dumps(dict(sections=sections),ensure_ascii=False,indent=2)+'\n','utf-8')
    print(f'License catalog: {sum(len(rows) for _,rows in sections)} component rows')


if __name__=='__main__':build()
