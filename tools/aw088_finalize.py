"""Evidence-bound local delivery; never claims perfect whole-corpus translation."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import re,sys
from zipfile import ZipFile,ZIP_DEFLATED
import xml.etree.ElementTree as ET
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from tools.aw088_prepare import QA,ROOT,SOURCE,ZIP,save
from app.documents.zip_archive import digest
from app.documents.control import JobControl

def read(name):return json.loads((QA/name).read_text('utf8'))


def package():
    folder=ROOT/'output/aw088/comparison';run=read('sample_pdf_e2e.json');held=read('representative_holdout.json')['documents']
    failed={r['member'] for r in run['failures']};accepted=[d for d in held if d['member'] not in failed]
    original=folder/'CN7C_тест_16_файлов.zip';translated=folder/'CN7C_переводы_программы.zip';pairs=[]
    with ZipFile(folder/'CN7C_test_originals.zip') as inputs,ZipFile(original,'w',ZIP_DEFLATED) as outputs:
        for d in accepted:outputs.writestr(d['member'],inputs.read(d['member']))
    with ZipFile(translated,'w',ZIP_DEFLATED) as outputs:
        for path in map(Path,run['outputs']):
            index=int(re.search(r'sample-(\d+)',path.name)[1]);doc=held[index]
            member=Path(doc['member']);name=(member.parent/(member.stem+'_ru.pdf')).as_posix()
            outputs.write(path,name);pairs.append(dict(source=doc['member'],source_sha256=doc['sha256'],translated=name,output_sha256=sha256(path.read_bytes()).hexdigest()))
    assert len(pairs)==len(accepted)==16
    for path in [original,translated]:
        with ZipFile(path) as archive:assert archive.testzip() is None
    instructions='''# CN7C: эталон и контрольный прогон

1. Для первого теста добавьте **CN7C_тест_16_файлов.zip** прямо в TreeTranslate.
2. Выберите китайский → русский, область Auto, профиль Auto. Перевод имён и папок отключите для удобства сопоставления.
3. **Эталон_CN7C.pdf** — независимо написанный смысловой эталон для 18 документов. **Эталон_CN7C.tsv** содержит исходник, эталон, результат программы и оценку каждого из 157 фрагментов.
4. **CN7C_переводы_программы.zip** — фактические результаты текущей программы, не эталон правильности. Сверяйте текст, действия, отрицания, детали, числа и обозначения, а не бинарный хеш PDF.
5. **CN7C_test_originals.zip** содержит все 18 исходников. Два файла пока отклоняются строгим обработчиком: схема с недоступным текстом и таблица с разнесёнными обозначениями. Они перечислены в manifest.json; в ZIP для первого теста их нет.

База расширена с 494 до 1405 записей; 1113 полных грамматических форм, 179 шаблонов. Нейросетевые веса не переобучались. Перевод сложных инструкций пока имеет серьёзные ошибки: в тесте по строкам две старые ошибки «снять ремень → отрезать» сохранены и отмечены CATASTROPHIC. Эталон содержит правильное «снимите», не эти результаты. Исходные неоднозначные подписи отмечены прямо в эталоне.

Для анализа в ChatGPT приложите свой результат, Эталон_CN7C.pdf / TSV и исходный тестовый ZIP. Попросите сравнить действия, объекты, условия, отрицания, единицы, обозначения, ссылки и сохранённый китайский текст; отдельно перечислить PASS / MINOR / MAJOR / CATASTROPHIC. Журналы вашего прогона сохраняются штатным логированием TreeTranslate.

Эталон предназначен только для оценки: его нельзя импортировать обратно в словарь или TM, иначе контрольный набор перестанет быть независимым. Это локальные пользовательские документы; пакет не опубликован.
'''
    (folder/'ПРОЧИТАЙ_МЕНЯ.md').write_text(instructions,'utf8')
    manifest=dict(corpus_id='CN7C_2022_REPAIR_MAINTENANCE',pack_entries=read('knowledge_after.json')['entries'],
        runtime_knowledge_sha256=read('knowledge_after.json')['sha256'],accepted_documents=16,reference_documents=18,
        reference_segments=157,reference_author='Codex; not human/OEM certified',reference_import_forbidden=True,
        parameters=dict(source='zh',target='ru',domain='auto',profile='automatic',translate_directories=False,translate_filenames=False),
        failed_documents=run['failures'],pairs=pairs)
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf8')
    bundle=folder/'CN7C_эталон_и_тесты.zip'
    names=['ПРОЧИТАЙ_МЕНЯ.md','manifest.json','Эталон_CN7C.pdf','Эталон_CN7C.tsv',original.name,translated.name,'CN7C_test_originals.zip']
    with ZipFile(bundle,'w',ZIP_DEFLATED) as archive:
        for name in names:archive.write(folder/name,name)
        archive.write(QA/'holdout_semantic_review.json','holdout_semantic_review.json')
    with ZipFile(bundle) as archive:assert archive.testzip() is None
    save('delivery_artifacts.json',dict(bundle=str(bundle),test_zip=str(original),reference_pdf=str(folder/'Эталон_CN7C.pdf'),
        reference_tsv=str(folder/'Эталон_CN7C.tsv'),translated_zip=str(translated),
        files=[dict(name=name,sha256=sha256((folder/name).read_bytes()).hexdigest(),bytes=(folder/name).stat().st_size) for name in names]))
    return bundle


def report(bundle):
    inventory=read('archive_inventory.json');split=read('corpus_split.json');after=read('knowledge_after.json');before=read('knowledge_before.json')
    held=read('holdout_semantic_review.json');old=read('old_holdout_regression.json');coolant=read('coolant_regression.json')
    scan=read('archive_scan_benchmark.json');scale=read('scale_benchmark.json');snap=read('snapshot_metrics.json')
    forms=read('grammar_forms.json');templates=json.loads((ROOT/'assets/config/knowledge-templates.json').read_text('utf8'))['templates']
    suite=ET.parse(QA/'regression.xml').getroot();tests=sum(int(r.attrib.get('tests',0)) for r in suite.iter('testsuite'))
    assert sum(int(r.attrib.get('failures',0))+int(r.attrib.get('errors',0)) for r in suite.iter('testsuite'))==0 and tests==809
    current=digest(SOURCE,JobControl());assert current==inventory['sha256_before'];save('source_integrity_final.json',dict(source=str(SOURCE),sha256=current,unchanged=True))
    sealed=read('holdout_after_production.json')['knowledge_hashes']
    assert all(sha256((ROOT/name).read_bytes()).hexdigest()==value for name,value in sealed.items())
    save('final_knowledge_seal.json',dict(hashes=sealed,unchanged_since_final_holdout=True,tests=tests,quality_gate='NOT_PASSED_FOR_UNATTENDED_WHOLE_CORPUS_TRANSLATION'))
    by_type='\n'.join(f'| {kind} | {n} |' for kind,n in after['types'].items())
    by_domain='\n'.join(f'| {kind} | {n} |' for kind,n in after['subdomains'].items())
    sections=[
    ('Результат и граница готовности',f'Большой ZIP проходит scanner READY; база и контрольный эталон созданы. **Полное качество автоматического перевода корпуса не принято.** Новых моделей, обучения весов, установщика, AW0.8.9 и автоматического commit нет. Полный regression: {tests} passed.'),
    ('Подлинность источника',f'Пользовательский источник — RAR5, {inventory["bytes"]:,} bytes, SHA256 `{current}`. Оригинал не менялся до/после конверсии и в финале. Источник USER_PROVIDED, corpus permission CANDIDATES_ONLY; независимые русские цели AUTHORED. Корпус не помещён в assets и не опубликован.'),
    ('Инвентаризация',f'{inventory["entries"]:,} entries, 17 211 PDF, 3 JSON, 5 622 directories. Unpacked {inventory["unpacked_bytes"]:,} bytes; largest member {inventory["largest_member"]:,}. Native inventory: 27 732 pages, 17 199 documents with native text; отсутствие native-текста не всегда означает скан.'),
    ('RAR → ZIP',f'Локальная утилита UnRAR читала один stdout-поток; границы членов заданы метаданными, ошибка/CRC обязательны. ZIP_STORED + force ZIP64. Сохранён `{ZIP}`. rarfile 4.5 установлен только для developer intake; production RAR не добавлен. Ни одна команда из архива не выполнялась.'),
    ('Лимиты большого ZIP','Compressed 4 GiB; unpacked 16 GiB; 100 000 members; 2 GiB/member; ratio 200; path 1024; depth 32. Это ограничения входа. Trusted generated output имеет отдельные bounds 32 GiB / 4 GiB per member, без обхода containment/composition/CRC.'),
    ('Защита имён','Сохранены traversal, absolute/drive/UNC, ADS, обратные слеши, reserved devices, trailing spaces/dots, Unicode NFC/casefold duplicates, file/directory conflicts, link/special/reparse, encryption and containment guards. Реальный архив прошёл; небезопасные fixtures отклоняются.'),
    ('ZIP64 и CRC','Тест генерирует реальный ZIP64 с локальными заголовками, central directory и ZIP64 EOCD, проверяет CRC; для граничных размеров используются также metadata fixtures. Scanner делает полный CRC-read с checkpoint по членам; выбранные члены вновь читаются при переводе.'),
    ('Потоковая обработка','Один открытый input ZIP и output ZIP. По одному документу: extract → штатный DocumentJob → append → удалить исходник и временный перевод. Assets передаются потоком. В RAM остаются метаданные, а не содержимое архива. Нет распаковки всех 16 GiB и повторного открытия central directory на каждый member.'),
    ('Дисковый бюджет','Preflight: оценка результата 1.5× input archive bytes + 128 KiB/document + 1 KiB/member, один largest member, rendering max(256 MiB, 2×largest), reserve 512 MiB. Для разных volumes бюджеты раздельны. Это оценка, не жёсткая гарантия роста перевода: ENOSPC остаётся atomic failure.'),
    ('Отмена и публикация','Cancel проверяется при metadata/CRC/copy/extract/pack. Финальный архив публикуется только после composition/CRC/source-hash validation. При ошибке/cancel финальный partial ZIP не появляется. Resume внутри архива не реализован: retry начинает архив заново; это явно сохранённая граница цикла.'),
    ('Scanner и UX',f'На настоящем ZIP {scan["files"]:,} PDF достигли READY за {scan["seconds"]:.2f}s; progress (0,0) → ({scan["entries_checked"]},{scan["entries_checked"]}). Использован существующий progress panel, без нового компонента/редизайна. Во время исходного hash — indeterminate; затем реальные CRC members. Две новые status/error строки добавлены во все 8 UI catalogs.'),
    ('Карта корпуса','Сохранена карта по реальным папкам/нативному тексту. Старая конфигурация дала automotive 14 015 / general 3 196; это не ручная классификация каждого файла. Реальные steering/fuel/emissions/restraint/interior families дали новые cues. Нельзя подменять исходные strata задним числом или считать весь general automotive без доказательств.'),
    ('Development / holdout',f'{split["development"]:,} development / {split["holdout"]:,} held ({split["holdout_percent"]:.2f}%). 6 800 logical groups. Полные документы с одинаковыми PDF SHA или нормализованным текстом сгруппированы до builds; hash/text overlap=0. Native-cache SHA привязан к immutable manifests; development Harvester не принимает held documents.'),
    ('Candidate intake','Существующий Knowledge Harvester расширен, второго pipeline/UI нет. 40 561 raw monolingual hypotheses из 13 717 development documents; doc/total/subdomain frequency, segment context, evidence SHA/offset and explainable priority factors. Raw candidates не bilingual assertions; automatic VERIFIED=0.'),
    ('Верификация и provenance','Русские targets и полные формы написаны независимо. Developer reviewer=Codex, не human-certified и не OEM-certified. Старые rejected/deprecated revisions сохранены в отдельных reviewer stores. NMT output и OCR suggestions не верифицировались автоматически; неоднозначные cap/left-right wheel/transaxle assertions отложены.'),
    ('Рост Knowledge',f'Entries {before["entries"]} → {after["entries"]}: +{after["entries"]-before["entries"]}, {after["concepts"]} concept identifiers, {after["aliases"]} aliases. Никакого заполнения квоты до 1500/3000 декартовыми комбинациями. Production DB {after["bytes"]:,} bytes.\n\n| Тип entries | После |\n|---|---:|\n'+by_type),
    ('Области Knowledge','Counts пересекаются по scope и не равны числу уникальных слов.\n\n| Scope | Entries |\n|---|---:|\n'+by_domain),
    ('Concept-first, aliases, polysemy','Одинаковые meaning+context объединены в concept с aliases. Прежние 494 assertions сохранены. Different overlapping targets fail closed/defer; body не получает engine/brakes/HVAC-specific rows без body scope. Две старые engine/body shared assertions легитимно остаются. Неоднозначная 冷却水箱盖 исключена вместо принудительной крышки расширительного бачка.'),
    ('Actions и шаблоны',f'157 → {len(templates)} verified templates (+22 evidence-backed patterns). Новые actions/предметы допускаются закрытыми whitelist; negative relation и safety conditions проверяются. Diagnostic labels отдельно от prose; FULL_SEGMENT осталось 12, не главный путь покрытия. Actions/templates лежат в существующих configs, не искусственно прибавлены к entries.'),
    ('Grammar forms',f'236 → {len(forms)} reviewed source forms с полными NOM/GEN/ACC. Позиционные определения привязаны к двери/сиденью/стойке, а не к головному слову облицовка. Исправлены спинка заднего сиденья, преднатяжитель заднего ремня со стороны водителя. 拆下 не создает «нижний»; частичный 下散热器 перед 软管 исключён.'),
    ('References, labels, units','Cross-reference classification выделен; closed references связывают два известных объекта. DOT/ID/torque numbers сохраняются. Capacity parser не выдумывает conversion для 美升 и 加仑/夸脱: оставляет исходное число с annotation. Numeric unit-only ranges protected. Unit-map content исключён из UI catalog discovery как перевод документа, не строка интерфейса.'),
    ('Выборочная pre-holdout проверка','353 новые surfaces: deterministic random 25/domain или все при меньшем числе, 16 domains. Проверены noun meanings/полные case forms; есть MINOR style issues. До финального holdout удалены unsafe abstract composition, verb-position collision, remote-wheel truncation, cap ambiguity and transaxle ambiguity. Это sampling, не сертификация каждой строки корпуса.'),
    ('Native / OCR probe','Native-first весь corpus inventory; OCR ограничен двумя development PDFs через production Auto/region policy. Один EMPTY_PDF, второй low-confidence OCR: structure/GPU route и load/inference metadata сохранены; network attempts=0. Распознанный ненадёжный текст не обучал Knowledge. Нет заявления, что все сканы корпуса теперь читаются.'),
    ('Holdout: методика','18 целых коротких held PDFs / 157 native text lines заморожены до build. Первоначальная line-engine диагностика сохранена отдельно: она не воспроизводила numbered PDF normalization. Корректное сравнение before_production/after_production использует штатный PDF translation helper и исходную domain profile. Baseline реконструирован из prebuild 494-pack/config snapshots; код PDF/units текущий. Отдельно проведён реальный writer-run, результаты нельзя смешивать со строковыми оценками.'),
    ('Holdout: покрытие и смысл',f'В production-normalized line benchmark bare model 95 → 75, glossary 49 → 60, template 1 → 10, protected 12 → 12. После: {held["after_grades"]}. Две CATASTROPHIC — старое «снять ремень → отрезать», new CATA=0. Это не успешный semantic gate. Ошибки final holdout не использованы для дообучения. Duplicate held documents присутствуют в representative set; это не 18 независимых уникальных text groups.'),
    ('Эталон и реальные PDF',f'Авторский PDF-эталон: 18 pages; TSV содержит все 157 source/reference/output/grade. Gold никогда не импортируется в production/TM. Production writer сохранил 16/18 PDFs. Два blockers: нечитабельная native схема и discontiguous preserved table labels. Первоначальный ZIP18 был корректно отклонён без финального partial output. Native bullet ↔ middle-dot visual equivalence исправлена; другие символы не ослаблены.\n\nПакет: `{bundle}`.'),
    ('Старые holdout regressions',f'AW085/AW086 40: {old["evaluations"][0]["grades"]}, все outputs неизменны от AW087. AW087 120: {old["evaluations"][1]["grades"]}; одно улучшение imperative водяного насоса. Profiler 8/8. Ошибка pretensioner старого prose-06 не обучалась по held source. Все frozen references SHA сохранены.'),
    ('Body regression','22 → 22 pages, 419/419 protected values, 10/10 reviewed instructions PASS, 0 OCR continuation. Геометрия/изображения сохранены, canonical published concepts 117/131. Wall 185.49s получен при параллельных тяжёлых QA jobs: не сравнивать как чистый speed benchmark и не включать в ETA calibration.'),
    ('Coolant regression',f'4 → 5 pages; bare fallback осталось 5. Полная semantic review: {coolant["before_grades"]} → {coolant["after_grades"]}. Две source-unit MAJOR стали MINOR с ambiguity annotation; один старый запрет ITM получил MINOR из-за русского падежа. CATA=0. Это небольшая грамматическая регрессия, не замалчиваемая как «не ухудшилось». Whole-file perfection не достигнута.'),
    ('Snapshots и scale',f'{snap["documents"]} development snapshots; max entries {snap["max_entries"]}, body {snap["body_entries"]}, forbidden specific terms=0. Actual production SQL benchmark {[(r["total_entries"],r["active_entries"],round(r["snapshot_median_seconds"]*1000,2)) for r in scale["rows"]]} (total, active, ms). Inactive synthetic scale rows не затронули source pack; это benchmark индекса, не NMT throughput и не реальная база 25k approved terms.'),
    ('Тесты, visual QA и времена',f'{tests} passed, regression.xml. Новые archive/Knowledge/PDF tests; строгие CRC/layout validators не отключены. Rendered все 24 machine PDFs + 18-page gold; просмотрены contact sheets и gold pages. Видимы intentionally preserved Chinese и continuation pages; это quality limitations, не пустые страницы без причины. Timings содержит run/stage/process. Concurrent QA wall times не подходят для калибровки ETA. Старый historical test исправлен: frozen AW087 reference проверяется по своему SHA, а не требует вечного совпадения нового production DB.'),
    ('Ограничения и завершение цикла','Не готово: безошибочный сплошной перевод длинной prose/conditions, две формы PDF, полное OCR corpus coverage, archive resume, human/OEM certification. База заметно расширена, локальный эталон и набор для прогона готовы. AW0.8.8 implementation проверена; semantic acceptance всего корпуса НЕ пройдена. AW0.8.9 и новые модели не начаты. Старые cleanup файлы не удалялись; transient failed scale DB не является runtime dependency. Commit не сделан.')]
    assert len(sections)==32
    path=ROOT/'docs/AW0.8.8_LARGE_CORPUS_REPORT.md'
    path.write_text('# TreeTranslate AW0.8.8 — Large Corpus & Knowledge Scale-Up\n\n'+'\n\n'.join(f'## {i}. {title}\n\n{body}' for i,(title,body) in enumerate(sections,1))+'\n','utf8')
    (QA/'FINAL_RESULTS.md').write_text(f'# AW0.8.8\n\nRegression: **{tests} passed**. Entries: **494 → 1405**.\n\nSemantic acceptance whole corpus: **NOT PASSED**; baseline limitations and blockers are explicit.\n\n[Report](../../docs/AW0.8.8_LARGE_CORPUS_REPORT.md).\n\nDelivery: `{bundle}`.\n','utf8')
    journal=ROOT/'docs/DEVELOPMENT_JOURNAL.md';text=journal.read_text('utf8')
    if '## AW0.8.8 — Large Corpus' not in text:
        journal.write_text(text+'\n\n## AW0.8.8 — Large Corpus\n\nRAR immutable → ZIP64, READY 17 211 PDFs; streamed archive job and disk budget. Development-only Harvester; 494 → 1405 entries, 1113 forms, 179 templates. Independent reference PDF/TSV and test ZIP16 delivered. 809 tests passed. Semantic gate of whole corpus NOT PASSED; two PDF blockers and long-prose errors remain. No AW0.8.9 / new models / commit. Details: [report](AW0.8.8_LARGE_CORPUS_REPORT.md).\n','utf8')
    next_path=ROOT/'docs/NEXT_CYCLE.md';previous=next_path.read_text('utf8')
    first=previous.split('\n\n',1)[1]
    next_path.write_text('# Новый цикл TreeTranslate\n\nТекущая рабочая база: **AW0.8.8 — Large Corpus & Knowledge Scale-Up**. [Отчёт](AW0.8.8_LARGE_CORPUS_REPORT.md). 809 passed; база 1405 entries. Пакет эталона и тестов готов. **Смысловое качество полного корпуса не принято**: long prose и два PDF blockers требуют последующего задания; AW0.8.9 не начат.\n\n'+first,'utf8')
    print('FINAL',tests,after['entries'],bundle,flush=True)


if __name__=='__main__':report(package())
