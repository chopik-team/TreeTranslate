"""Write diagnostic live-run readiness only after operational/visual evidence."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.aw081_large_zip import production_hashes
from app.documents.run_metrics import file_hash
QA=ROOT/'qa/aw081/iterations/15_diagnostic_live_readiness'

def run():
    operational=json.loads((QA/'operational/execution.json').read_text('utf8'))
    visual=json.loads((QA/'operational/cata_publication_review.json').read_text('utf8'))
    preflight=json.loads((QA/'large_zip_preflight.json').read_text('utf8'))
    execution=json.loads((QA/'full_pytest_final/execution.json').read_text('utf8'))
    suite=ET.parse(QA/'full_pytest_final/junit.xml').getroot()
    tests=sum(int(s.attrib.get('tests',0)) for s in suite.iter('testsuite'))
    errors=sum(int(s.attrib.get('errors',0))+int(s.attrib.get('failures',0)) for s in suite.iter('testsuite'))
    assert execution['returncode']==0 and not errors and execution['production_unchanged']
    assert production_hashes()==execution['production_hashes_after']
    assert operational['processed']==46 and operational['fatal']==0
    assert operational['crc']=='PASS' and operational['source_immutable'] and operational['successful_member_bytes_unchanged']
    assert visual['known_cata_remaining']==0 and visual['published_cases_reviewed']==4
    assert preflight['technical_preflight']=='READY' and not preflight['translation_started']
    summary=operational['summary'];translated=operational['translated'];failed=operational['failed_source_preserved']
    assert translated+failed==46 and summary['logging_status']=='COMPLETE'
    changed=[row for row in operational['previous_successful_semantics'] if not row['unchanged']]
    unchanged=len(operational['previous_successful_semantics'])-len(changed)
    previous_failures='\n'.join(f"| {row['index']} | {row['old_error']} | {row['new_status']} |" for row in operational['previous_failures'])
    readiness=f'''# TreeTranslate AW0.81 — готовность диагностического живого прогона

**DIAGNOSTIC LIVE RUN READY.** Готовность безопасно собрать данные, а не подтверждение качества перевода или готовности релиза.

| Проверка | Итог |
|---|---|
| Четыре известных CATA Diagnostic A | **0 осталось**; проверены исходные полные блоки и опубликованные PDF |
| Full pytest | **PASS — {tests} тестов**, 0 failures/errors |
| 46 PDF: processed | **46 / 46** |
| TRANSLATED | **{translated}** |
| FAILED_SOURCE_PRESERVED | **{failed}**; оригинальные пути и байты сохранены |
| FATAL_ARCHIVE_FAILURE | **0** |
| Итоговый тестовый ZIP / CRC / inventory / source immutable | **PASS** |
| Logging / новые статусы и счётчики | **PASS** |
| Continue on document error | **PASS**; отмена и глобальные ошибки остаются фатальными |
| Большой ZIP preflight | **PASS**; 17 211 PDF, полный CRC будет при GUI scan |
| Большой ZIP переведён | **НЕТ** |

Ошибки документов дают `COMPLETED_WITH_FAILURES`. Они не считаются переводом; GUI показывает «Завершено с ошибками; оригиналы сохранены». Нарушения безопасности/целостности, изменение источника, ENOSPC и ошибки финальной проверки/публикации ZIP останавливают прогон без публикации непроверенного архива.

Известные наложения текста в таблицах остаются открытыми, записываются в warnings и отдельную выборку; layout PASS им не присвоен. 361 исторический MAJOR не исправлен и не переоценён. Новые неизвестные CATA на большом корпусе не исключены. Frozen B не создавался; независимая оценка качества не проводилась.

Запуск выполняете вы через обычный GUI текущей рабочей версии: `C:\\TreeTranslate\\run_dev.bat`. Итоговый ZIP появится в выбранной папке результата либо рядом с источником. Полные журналы: `C:\\Users\\PC\\AppData\\Local\\CHOPIK Team\\TreeTranslate\\logs\\document_runs\\<run_id>\\`.

После запуска передайте итоговый ZIP, всю папку журналов этого run_id и выбранные настройки/наблюдения о скорости. При глобальном сбое передайте журналы даже без итогового ZIP.

[Подробный pre-run отчёт](C:/TreeTranslate/docs/AW0.81_LARGE_ZIP_PRERUN_REPORT.md) · [46-document evidence](C:/TreeTranslate/qa/aw081/iterations/15_diagnostic_live_readiness/operational/execution.json).

**STOP:** большой ZIP не запускался автоматически. AW0.82, PHASE B/C, installer и UI redesign не выполнялись.
'''
    details=f'''# TreeTranslate AW0.81 — LARGE ZIP PRE-RUN REPORT

**DIAGNOSTIC LIVE RUN READY.** Цель этой итерации — первый живой диагностический прогон через GUI с сохранением результатов и данных при ошибке отдельного PDF. Это не semantic quality PASS, не исправление 361 MAJOR, не Frozen B PASS и не release-ready translation.

## Изменение относительно предыдущего отчёта

Историческая первая оценка A сохранена: 342 PASS, 512 MINOR, 361 MAJOR, 4 CATA, 11 document processing failures; один exact BODY overlap. После разрешения пользователя A используется как development/diagnostic data. Исправлены только четыре известные CATA через проверяемые действия, объекты и отношения; полный semantic review 1219 блоков не повторялся. Старый pre-run отчёт сохранён в `qa/aw081/iterations/15_diagnostic_live_readiness/before/docs/`.

PHASE A DEV / LEVEL 3 сохраняют прежние результаты. Текущий full pytest: **{tests} PASS**, 0 failures/errors; {execution['seconds']:.2f} seconds. Production hashes до/после совпали, и совпадают с текущим кодом. [execution.json](C:/TreeTranslate/qa/aw081/iterations/15_diagnostic_live_readiness/full_pytest_final/execution.json).

## Четыре известных CATA

Системные причины: потеря домкрата и пространственного отношения при поддержке агрегата; потеря затяжки винта прокачки; инверсия нажатия/удержания педали. Расширен существующий closed-directives composer: проверенные полные noun slots, отдельные падежные формы, повторное действие, максимальная отметка жидкости и последовательность действий одного помощника. Неизвестные объекты, хвосты, условия и разные педали отклоняются целиком. Guards отвергают утрату инструмента, отношения «под», затяжки и удержания нажатой педали. Не добавлены полные предложения в Knowledge и не изменён NMT.

Добавлены два терминологических concepts — домкрат и винт прокачки; существующие concepts поддона, transaxle и бачка переиспользованы. `油盘` ограничен контекстом домкрата; `储液箱` — контекстом тормозной жидкости. Automatic frontier остаётся unverified, автоматически Knowledge не меняет.

Итог: **из четырёх известных CATA осталось 0**. Проверены реальные полные PDF и видимость опубликованных действий/объектов. Это проверка известных случаев, не гарантия отсутствия других CATA. [publication review](C:/TreeTranslate/qa/aw081/iterations/15_diagnostic_live_readiness/operational/cata_publication_review.json).

## Archive error policy

Внутри обработки одного member ошибки перевода, PDF parsing/extraction/OCR, writer/validation, IndexError и иная неподдерживаемая структура сохраняют оригинальный member **с точным исходным путём и байтами**. Статус `FAILED_SOURCE_PRESERVED`; ошибка записывается, следующий member обрабатывается. Успешные документы имеют `TRANSLATED`; failed не передаются callback, помечающему файл переведённым. Права на исходные имена/вложенные каталоги резервируются заранее, чтобы перевод имени не занял путь сохранения оригинала.

Фатальными остаются archive security/unsafe path, input CRC/integrity, изменение source/member, OSError (включая ENOSPC), критическая ошибка archive writer, финальная валидация и публикация. Отмена остаётся отменой. Archive failures дают `FATAL_ARCHIVE_FAILURE`, отмена `CANCELLED`. Временные файлы убираются; результат публикуется атомарно и без перезаписи только после полного CRC/inventory/source immutability checks. Hard crash может оставить staging/temp; automatic retry/resume нет.

При хотя бы одном сохранённом ошибочном документе run = `COMPLETED_WITH_FAILURES`, а не SUCCESS. Summary содержит `total_documents`, `translated_documents`, `failed_documents`, `source_preserved_documents`, `skipped_non_documents`, `fatal_errors`, `document_error_categories`; для завершённого archive selected-documents `translated + source_preserved = total`. Все выбранные 46 PDF проверены этой инвариантой.

## Реальный operational regression: 46 PDF

Normal scanner, DocumentJob, ArchiveJob, production router/NMT/PDF writer; изолированные пользовательские базы QA, только 46 ранее выделенных PDF из Diagnostic A. Подготовленный ZIP из этих документов — не большой архив 17 211 PDF. Полный semantic review не проводился.

Processed **46**, translated **{translated}**, failed/source-preserved **{failed}**, fatal **0**. Run status `{operational['status']}`, logging `COMPLETE`; время {operational['seconds']:.2f} seconds. Итоговый ZIP существует и открывается, CRC PASS, содержит ровно 46 PDF и вспомогательный JSON; каждый failed PDF побайтно совпадает с входным member, source archive SHA неизменен. Byte SHA всех успешных members совпадает с нормальным результатом child DocumentJob: политика recovery и упаковка не меняют успешный PDF. Targeted A/B test дополнительно сравнил текст и pixels следующего успешного PDF с/без предшествующей ошибки, logging on/off — те же content/pixels.

Предыдущие 11 failures, индексы нулевые:

| Index A | До | Сейчас |
|---|---|---|
{previous_failures}

Сопоставление с первой оценкой A: {unchanged} предыдущих успешных документов имеют одинаковые candidate translations, {len(changed)} имеют изменения. Это **не новый semantic grade**: CATA grammar/guards и обычный archive context отличаются от прежних отдельных jobs. Список различий сохранён в execution.json и не использован для исправления остальных MAJOR. Проверка неизменности на границе archive policy выполнена отдельно по точным SHA успешных child outputs и targeted A/B tests.

ZIP: `{operational['output_archive']}`. SHA: `{operational['output_archive_sha256']}`.

Logs QA: `{operational['logs']}`. [Operational evidence](C:/TreeTranslate/qa/aw081/iterations/15_diagnostic_live_readiness/operational/execution.json).

QA receipt восстанавливался из final SQLite bindings: первоначальный postprocessor ошибочно ожидал final member path в раннем JSONL checkpoint. Исходный stderr сохранён; processing run завершился штатно, translation не повторялся. Все CRC/байтовые/SHA проверки выполнены повторно по финальным привязкам. Это ошибка QA postprocessing, не дополнительный document/archive failure.

## Layout остаётся открытым

Известные table overlap документов A 24/25 занесены в source-SHA advisory registry. В GUI run warnings и `quality_sample_manifest.json/known_layout_overlap` сохраняют связь с final member, layout = `WARNING_KNOWN_OVERLAP`. Registry не является detector остальных страниц. Structural PDF validation PASS не превращается в layout PASS; прочие документы имеют `NOT_EVALUATED`. Переписывание layout и исправления всех наложений не выполнялись.

## Logging

Offline local JSONL и SQLite WAL; flush после документа и регулярные checkpoints. Failed document: document_id, member path, source SHA, stage, primary/secondary categories, exception type, elapsed, preserved yes/no, безопасные stack locations и числовые PDF diagnostics. Полный document text, exception messages и locals не записываются в application logs. QA captures/reference PDFs для регрессии хранятся отдельно от production logs.

Статусы `TRANSLATED`, `FAILED_SOURCE_PRESERVED`, `FATAL_ARCHIVE_FAILURE` и run `COMPLETED_WITH_FAILURES` проверены. Sample включает failed documents и known overlap, а также прежние random/domain/model/unknown/warnings/OCR/table/slow/page changes. Frontier автоматически не публикуется. Coverage и model fallback не являются quality score. Peak VRAM остаётся unavailable, если существующий allocator не инициализирован.

`TRANSLATED` означает успешно созданный и структурно проверенный документ, не semantic/layout acceptance всех блоков: отдельные unsafe blocks могут сохранить китайский source. Legacy `translated_mb_per_hour` использует общий output_bytes, включая original-preserved bytes; точную скорость только переведённых PDF следует вычислять по размерам записей со статусом `TRANSLATED`. При ручном выборе части архива `skipped_non_documents` включает невыбранные members; при выбранном целом CN7C ZIP это три JSON assets. Эти поля не следует использовать как доказательство полного перевода.

Исторический benchmark предыдущей итерации: median logging overhead **1,51%** на двух небольших DEV native PDF. Это не свежая оценка стоимости нового archive recovery и не прогноз скорости 17k mixed/OCR corpus. В этой итерации logging on/off проверен по semantic text и pixel output, без повторного большого performance benchmark.

## Большой CN7C ZIP: только preflight

Источник: `{preflight['source_archive']}`. SHA `{preflight['source_sha256']}`. Размер {preflight['archive_bytes']:,} bytes; members {preflight['members']:,}, directories {preflight['directories']:,}, files {preflight['file_members']:,}, **17 211 PDF +3 JSON**. Полное число страниц неизвестно. Security central-directory PASS; полный input CRC **NOT RUN** и будет проверен обычным GUI scan.

Disk budget: production {preflight['disk_budget']['required']:,} bytes; logs allowance {preflight['estimated_log_allowance_bytes']:,} bytes. Оценки — не hard upper bounds. Combined C: need {preflight['disk_volumes']['C:'+chr(92)]['required_bytes']:,} bytes; free {preflight['disk_volumes']['C:'+chr(92)]['free_bytes']:,} bytes. Disk READY, CUDA available; Auto может использовать CPU fallback. Temp хранит только текущий member/результат и растущий staging ZIP; external OCR caches учитываются отдельно. [Fresh preflight](C:/TreeTranslate/qa/aw081/iterations/15_diagnostic_live_readiness/large_zip_preflight.json).

## Ваш ручной запуск

Откройте текущую рабочую версию через `C:\\TreeTranslate\\run_dev.bat`, выберите большой ZIP, Chinese→Russian, обычный device/threads и папку результата; запустите обычной кнопкой. Старый exe/другая копия могут не содержать изменений. Прогон через Codex или CLI не нужен. GUI использует обычные пользовательские базы, в operational QA они были изолированы.

Результат — выбранная GUI output folder либо папка source ZIP; collision-safe имя покажет приложение. Полные GUI logs: `C:\\Users\\PC\\AppData\\Local\\CHOPIK Team\\TreeTranslate\\logs\\document_runs\\<run_id>\\`. Один translation run_id связывает весь archive; предварительный scan имеет отдельный связанный scan_run_id и scan_seconds, время ожидания кнопки не включается в translation wall time.

После своего запуска передайте итоговый ZIP, всю папку run_id журналов, выбранные настройки и наблюдения о скорости/зависаниях/подозрительных страницах. На этой машине достаточно абсолютных путей. При глобальном сбое final ZIP может отсутствовать — журналы всё равно пригодны для анализа.

**STOP: большой ZIP не запускался.** Изменены только AW0.81, четыре известных CATA, archive failure policy и диагностика/тесты. Новых экранов/компонентов и UI redesign нет; существующая progress panel получила честный статус завершения с ошибками. AW0.82, PHASE B/C, Frozen B, installer и остальные MAJOR не выполнялись.
'''
    for name,content in [('AW0.81_LIVE_RUN_READINESS.md',readiness),('AW0.81_LARGE_ZIP_PRERUN_REPORT.md',details)]:
        (ROOT/'docs'/name).write_text(content,'utf8')
    state_path=ROOT/'qa/aw081/work_state.json'
    state=json.loads(state_path.read_text('utf8'))
    xml_path=QA/'full_pytest_final/junit.xml'
    skipped=sum(int(s.attrib.get('skipped',0)) for s in suite.iter('testsuite'))
    pytest_seconds=sum(float(s.attrib.get('time',0)) for s in suite.iter('testsuite'))
    state.setdefault('tests_history',[]).append(dict(state['tests'],scope='Historical iteration 14 PHASE A full pytest'))
    state['tests']=dict(tests=tests,failures=0,errors=0,skipped=skipped,seconds=pytest_seconds,
        xml_path=str(xml_path.relative_to(ROOT)),xml_sha256=file_hash(xml_path))
    state['latest_full_suite']=dict(state['tests'])
    state['full_suite_gate']='PASS: complete suite for iteration 15 diagnostic live-run preparation; not semantic release acceptance.'
    import sqlite3
    with sqlite3.connect(ROOT/'assets/knowledge/aw083-body-repair-zh-ru.db') as database:
        knowledge=list(database.execute('SELECT notes,variants FROM entries'))
    state['knowledge_entries']=len(knowledge)
    state['knowledge_concepts']=len({json.loads(notes or '{}').get('concept_id') for notes,_ in knowledge})
    state['aliases']=sum(len(json.loads(variants or '[]')) for _,variants in knowledge)
    state['forms']=len(json.loads((ROOT/'assets/config/automotive-slot-forms.json').read_text('utf8'))['forms'])
    state['templates']=len(json.loads((ROOT/'assets/config/knowledge-templates.json').read_text('utf8'))['templates'])
    state['latest_accepted_iteration']='15_diagnostic_live_readiness (operational scope only)'
    state['final_holdout_A']='Historical FAIL; now authorised Diagnostic A; four known CATA repaired, no full semantic regrade.'
    state['pending_user_questions']=None
    state['current_task_progress_estimate_percent']=100
    state['large_zip_overall_readiness']='DIAGNOSTIC_LIVE_RUN_READY; translation quality not accepted'
    state['next']='STOP. User runs the large ZIP through ordinary TreeTranslate GUI. Do not create Frozen B or start PHASE B/C in this task.'
    state['readiness_report']='docs/AW0.81_LIVE_RUN_READINESS.md'
    state['latest_mechanism_checkpoint']='15: four known CATA and archive operational reliability; all other MAJOR remain outside scope.'
    state.update(status='DIAGNOSTIC_LIVE_RUN_READY',current_task_status='READINESS_REPORT_COMPLETE_STOPPED',
        latest_iteration='15_diagnostic_live_readiness',live_run_readiness=dict(verdict='DIAGNOSTIC LIVE RUN READY',
            known_cata_remaining=0,scope='FOUR_KNOWN_DIAGNOSTIC_A_CASES_ONLY',full_pytest=tests,
            operational_processed=46,translated=translated,failed_source_preserved=failed,fatal=0,
            archive_policy='CONTINUE_ON_DOCUMENT_ERROR',large_zip_started=False,release_ready=False,
            frozen_B_started=False,semantic_grades_not_refreshed=True),completed=False)
    state_path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n','utf8')
    receipt=dict(verdict='DIAGNOSTIC LIVE RUN READY',completed_at_utc=datetime.now(timezone.utc).isoformat(),
        production_unchanged=production_hashes()==execution['production_hashes_after'],large_zip_started=False,
        reports={name:file_hash(ROOT/'docs'/name) for name in ['AW0.81_LIVE_RUN_READINESS.md','AW0.81_LARGE_ZIP_PRERUN_REPORT.md']},
        operational_sha256=file_hash(QA/'operational/execution.json'),pytest=tests,known_cata_remaining=0)
    (QA/'readiness_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))
if __name__=='__main__':run()
