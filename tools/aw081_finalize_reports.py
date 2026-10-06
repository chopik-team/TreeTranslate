"""Final local evidence/report assembly; does not translate or publish Knowledge."""
from collections import Counter
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app.documents.run_metrics import file_hash
from tools.aw081_large_zip import production_hashes
QA=ROOT/'qa/aw081/iterations/14_phase_a_closure'
F=QA/'frozen_A_whole'
def read(p):return json.loads(p.read_text('utf8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf8')
def link(p):return f'[{p.name}]({p.resolve().as_posix()})'

def run():
    gate=read(QA/'acceptance_gate.json');frozen=read(F/'execution.json');review=read(F/'semantic_review.json')
    assert review['semantic_status']=='COMPLETE' and production_hashes()==frozen['production_hashes']==gate['production_hashes']
    manifest=read(ROOT/'qa/aw081/final_holdout_manifest.json')
    used={file_hash(p):str(p.relative_to(ROOT)) for p in (QA/'level3/render').glob('*-source.pdf')}
    diagnostic=read(ROOT/'qa/aw088/representative_holdout.json')
    used.update({d['sha256']:'Existing diagnostic whole PDF' for d in diagnostic['documents']})
    overlap=[dict(index=i,source_sha256=d['sha256'],previous_use=used[d['sha256']]) for i,d in enumerate(manifest['documents']) if d['sha256'] in used]
    independent=Counter(r['grade'] for r in review['rows'] if r['index'] not in {d['index'] for d in overlap})
    audit=dict(first_whole_production_evaluation=True,fully_independent=False,
        exact_source_overlaps=overlap,scope='BODY source PDFs and existing diagnostic whole PDFs; not a claim of exhaustive historical decontamination.',
        untouched_documents_within_this_audit=46-len(overlap),independent_subset_grades=dict(independent),
        before_development_guarantee_invalidated=True,required_next_set='Untouched Frozen B excluding all reviewed A groups and all DEV/BODY sources.')
    write(F/'independence_audit.json',audit)
    failed=[dict(index=d['index'],member=d['member'],exception=d['error_type'],
        message=d['error_message'],primary_category='UNIT_GUARD' if d['error_type']=='TranslationError' else 'UNKNOWN_INTERNAL_ERROR' if d['error_type']=='IndexError' else 'UNSUPPORTED_STRUCTURE',
        root_cause='Unresolved; no source-damage assertion based only on a public exception message.') for d in frozen['documents'] if d['validation']!='PASS']
    successful=[d for d in frozen['documents'] if d['validation']=='PASS']
    summary=read(Path(frozen['logs'])/'run_summary.json')
    result=dict(status='FAIL',documents=46,structural_success=len(successful),structural_failures=len(failed),
        source_pages=sum(d['pages'] for d in manifest['documents']),
        validated_source_pages=sum(d['source_pages'] for d in successful),
        validated_output_pages=sum(d['output_pages'] for d in successful),
        source_immutable=True,production_unchanged=True,semantic_grades=review['grades'],
        semantic_denominator=review['semantic_denominator'],failed_documents_excluded_from_semantic_denominator=True,
        routing_denominator_note='Run counters include completed segments from failed documents and use a different eligibility definition. They are not the published-block semantic denominator.',
        independence_audit=audit,failures=failed,metrics=summary,
        visual_review=dict(rendered_selected_pages=4,reviewed_selected_pages=4,
            confirmed_table_overlap_documents=[24,25],new_layout_failure=True,
            all_77_output_pages_visually_reviewed=False,
            severe_instruction_failures_visible_in_render=[5,9]),
        large_zip_started=False,fixes_after_first_frozen_review=False,next_set='FROZEN_B',
        evaluation_seconds=frozen['seconds'])
    write(F/'final_evaluation.json',result)
    write(ROOT/'qa/aw081/frozen_A_first_use.json',dict(used_at_utc=datetime.now(timezone.utc).isoformat(),
        previous_set='FINAL_HOLDOUT_A',new_role='DIAGNOSTIC_A',manifest_unchanged=True,
        evaluation=str((F/'final_evaluation.json').relative_to(ROOT)),fixes_forbidden_in_current_task=True,
        next_independent_set='FROZEN_B',quality_gate='FAIL',independence_gate='FAIL'))
    benchmark=read(Path(gate['logging_benchmark_path']));pre=read(QA/'large_zip_preflight.json')
    pytest=read(QA/'full_pytest_final_gui/execution.json')
    suite=ET.parse(QA/'full_pytest_final_gui/junit.xml').getroot().find('testsuite')
    assert int(suite.attrib['tests'])==1138 and int(suite.attrib['failures'])==int(suite.attrib['errors'])==0
    for name in ('AW0.81_PHASE_A_CLOSURE_REPORT.md','AW0.81_LARGE_ZIP_PRERUN_REPORT.md'):
        shutil.copy2(ROOT/'docs'/name,QA/('interim_'+name))
    g=review['grades'];c=summary['counters']
    phase=f'''# TreeTranslate AW0.81 — завершение PHASE A и проверка допуска

Дата: {datetime.now(timezone.utc).isoformat()}. Текущая задача проверки завершена. **Релиз и полный большой ZIP не получили допуск: Frozen A FAIL.** Оценка Codex, без независимой человеческой сертификации.

| Gate | Результат |
|---|---|
| PHASE A, проверенный DEV acceptance scope | PASS |
| LEVEL 3, BODY/coolant regression | PASS |
| Общий pytest после GUI logging | PASS: 1138 тестов |
| Первый whole-production Frozen A | FAIL: семантика, обработка PDF, layout, независимость |
| Локальные журналы, включая обычный GUI | READY |
| Полный ZIP | Не запускался; общий допуск NOT READY |

## История и 18 фрагментов

Исторические raw-line grades **108 PASS / 31 MINOR / 18 MAJOR / 0 CATA** не изменены. Это не новая оценка целых документов. Каждый из 18 MAJOR связан с конкретным полным native parent, SHA исходника, parent/output SHA и семью условиями допустимой переклассификации. Новая классификация **NOT_EVALUABLE_FRAGMENT: 18**, не PASS. {link(QA/'parents_final_fixed/parent_evidence.json')}.

Свежая production reconstruction/translation проверила **16 полных parent blocks: 16 PASS, 0 MAJOR/CATA**, без вызова модели. Общий pytest проверил операции, вопросы, отрицания, электрические величины, условия, сравнения и ограничения контекста. Дополнительный полный exhaust PDF: **7 semantic PASS**, 2 защищённых WCC/UCC label; одна операция REMOVE для узла «каталитический нейтрализатор и центральный глушитель в сборе». Компоненты остаются отдельными concepts. {link(QA/'exhaust_assembly/semantic_review.json')}.

Не объединяем старые 157 raw fragments, новые 16 parents, BODY labels и whole-PDF semantic blocks в искусственный общий процент качества. Остальные исторические 31 MINOR не объявляются автоматически свежими whole-PDF PASS. PHASE A PASS относится к ранее принятому DEV scope и проверенным полным parents; это не обещание корректного перевода любого OEM документа.

## LEVEL 3

Свежий BODY: **7 PDF, 22→22 страницы, 365 segments, 419/419 protected values**, 10/10 известных инструкций PASS. Canonical concept translation 130/131, publication 117/131; strict совпадения 110/131 и 100/131. **23 старых Chinese residue labels сохранены**; новые изменения semantic output относительно принятой BODY baseline — 0. Исходный ZIP immutable, итоговый CRC PASS. Время 176,60 s не является logging overhead: исторический запуск имел другое состояние runtime/OCR caches.

Свежий coolant: реальный native+OCR PDF **4→5 страниц, 108 segments**. Семантическая оценка: **84 PASS / 5 MINOR / 0 MAJOR / 0 CATA**, denominator 89; отдельно **4 SOURCE_AMBIGUOUS, 1 SOURCE_DAMAGED, 14 OCR-noise exclusions**. Неоднозначные units/thresholds не названы PASS. Оборванная cross-reference восстановлена через явное пользовательское OEM-уточнение и остаётся SOURCE_DAMAGED в учёте.

Четыре cross references и три EVAP/GPF candidate translations исправлены. **Две длинные EVAP подписи не публикуются внутри изображения: source сохранён из-за нехватки места.** Всего восемь компактных OCR labels имеют эту publication limitation. Поэтому публикация, отдельно от смыслового candidate result: **76 PASS / 13 MINOR**, те же source/noise exclusions. GPF label опубликован. Предупреждения, отрицания, последовательность операций, числа и continuation page проверены.

Poppler отрендерил все **27 output pages**, сравнение с 26 source pages просмотрено на 11 sheets; новый layout damage в BODY/coolant не обнаружен. Также просмотрен полный exhaust output. {link(QA/'level3/visual_review.json')}, {link(QA/'level3/coolant_semantic_review.json')}, {link(QA/'level3/execution.json')}.

Эта production LEVEL 3 предшествовала только подключению уже проверенного observer к кнопке GUI и записи времени scan. Translation/segmentation/OCR/writer поведение после неё не менялось. Затем повторены весь pytest и logging equivalence benchmark на текущем коде. Нет заявления о новом полном LEVEL 3 после GUI wiring.

## Общий pytest и logging

**1138 passed**, 0 failed/error/skipped; pytest 266,18 s, wrapper {pytest['seconds']:.2f} s. Два исторических падения исправлены и проходят именно в общей suite. Git HEAD/status, staged/unstaged diff, JUnit, stdout/stderr, timing и production hashes сохранены. Никаких commits/reset. {link(QA/'full_pytest_final_gui/execution.json')}, {link(QA/'full_pytest_final_gui/junit.xml')}.

Обычный GUI run испытан на ZIP с двумя DOCX: source SHA unchanged, final archive CRC, два document records, sample manifest, scan link и content-safe logs. Совместно 14 GUI/service/observer tests PASS. Пять пар logging off/on: median overhead **{benchmark['overhead_percent']:.2f}%**, цель <5% выполнена. PDF text, normalized objects и pixel rendering совпадают; raw PDF SHA отличаются только случайными PDFium trailer IDs и записаны отдельно. {link(Path(gate['logging_benchmark_path']))}.

## Frozen A — результаты первого полного production прогона

Все **46 PDF / 46 groups / 2651 historical native-line strings** обработаны отдельными обычными DocumentJobs; переведены только эти 46 выбранных PDF, не архив из 17k PDF. Source 69 pages. Из **46** документов writer validation прошли **35**, упали **11**. Для успешных документов **52 source pages →77 validated output pages**; validation не равен semantic/layout PASS. Четыре selected output pages дополнительно отрендерены и просмотрены: таблицы PDF 24/25 имеют наложения текста и порогов. Все 77 output pages визуально не просмотрены.

| Semantic grade, опубликованные successful-document blocks | Число |
|---|---:|
| PASS | {g['PASS']} |
| MINOR | {g['MINOR']} |
| MAJOR | {g['MAJOR']} |
| CATA | {g['CATA']} |
| SOURCE_AMBIGUOUS | {g['SOURCE_AMBIGUOUS']} |
| SOURCE_DAMAGED | {g['SOURCE_DAMAGED']} |
| NOT_EVALUABLE_FRAGMENT | {g.get('NOT_EVALUABLE_FRAGMENT',0)} |
| Protected identifiers/values и OCR noise, вне denominator | {g['EXCLUDED_PROTECTED_OR_OCR_NOISE']} |

Semantic denominator **{review['semantic_denominator']}**; 11 failed documents не названы PASS и не включены в этот denominator. Предварительный мини-отчёт содержал 360 MAJOR/513 MINOR; после render подтверждена дополнительная ошибка читаемости порога: итог **361 MAJOR/512 MINOR**. Предварительная версия сохранена.

CATA evidence: PDF 5 теряет домкрат/правильную поддержку двигателя и трансмиссии перед снятием опор; PDF 9 заменяет затяжку bleed screw на нажимание и нажатие/удержание педали на её поднятие. MAJOR: wrong ground/relay/valve nouns, неверные quantity relations, dropped diagnostic questions/No, source-preserved whole prose, split source sentences, writer overlap. Ошибки обработки: 3 TranslationError (negative-sign guard), 7 PdfError и 1 IndexError. Причины PdfError ещё не установлены; публичное сообщение «файл повреждён» не доказывает SOURCE_DAMAGED.

Проверка независимости обнаружила **{len(overlap)} exact source overlap** с BODY: PDF 13. Поэтому утверждение «все 46 полностью untouched» неверно. По данному audit независимый subset **{46-len(overlap)} PDF**; его grade counts: `{dict(independent)}`. Это не исчерпывающий audit всех исторических источников. {link(F/'independence_audit.json')}.

Logs: model fallback **{c['model_fallback_segments']}/{c['semantic_segments']} = {summary['model_fallback_rate']*100:.2f}%**; materially knowledge-constrained **{c['knowledge_segments']}/{c['eligible_semantic_segments']} = {summary['knowledge_coverage']*100:.2f}%**. Direct known {c['direct_known_segments']}, glossary {c['glossary_segments']}, templates {c['template_segments']}, composition {c['composition_segments']}, model calls {c['model_calls']}; route counts могут пересекаться. Эти denominators включают completed segments failed documents и отличаются от ручного published-block denominator; **не являются качеством**. Warnings {c['warnings']}, protected/noise {c['protected_or_noise_segments']}, unit guards {c['unit_guard_events']}, negation guards {c['negation_guard_events']}, object guards {c['object_guard_events']}, action guards {c['action_guard_events']}; некоторые показатели detectors unavailable, не ноль. Время выбранного QA прогона **{frozen['seconds']:.2f} s** не прогноз большого ZIP и не GUI benchmark.

{link(F/'final_evaluation.json')}, {link(F/'semantic_review.json')}, {link(F/'execution.json')}.

## Решение

**PHASE A DEV и LEVEL 3 regression приняты; общий release/large ZIP quality gate FAIL.** A переведён в роль Diagnostic A, manifest/history не изменены. Никаких исправлений из A в текущей задаче; следующий цикл исправлений потребует нового untouched Frozen B. PHASE B/C не начинались, AW0.82 не создан, NMT не заменён, UI screens не переделаны, installer не добавлен. Текущая задача остановлена после отчётов; большой ZIP не запускался.
'''
    prerun=f'''# TreeTranslate AW0.81 — LARGE ZIP PRE-RUN REPORT

**Instrumentation READY, общий допуск NOT READY.** PHASE A DEV / LEVEL 3 / 1138 pytest PASS; Frozen A FAIL: {g['MAJOR']} MAJOR, {g['CATA']} CATA, 11 document processing failures, table overlaps и exact BODY overlap. Большой ZIP не запускался. Этот документ не даёт автоматического запуска или обещания завершения архива.

## Corpus и диск

Исходник: `{pre['source_archive']}`. SHA-256: `{pre['source_sha256']}`. Размер **1 945 071 930 bytes**; **22 836 members =5 622 dirs +17 214 files**, из них **17 211 PDF и 3 JSON**, DOCX 0. Uncompressed 1 933 957 260 bytes. Полное число страниц неизвестно: весь corpus не извлекался.

Central-directory/security preflight PASS; полный CRC **ещё не запускался для большого ZIP**. Обычный GUI scan проверяет CRC всех members, а production inventory повторяет security checks; guards не ослаблены. Исходники не изменяются; публикация ZIP atomic и collision-safe, выбранные не-PDF assets сохраняются.

Оценки: final output allowance 5 196 872 151 bytes, current working member 8 400 159, rendering 268 435 456, reserve 536 870 912; production requirement **6 010 578 678 bytes (~5,60 GiB)**. Отдельный log allowance **4 511 760 384 bytes**; общий C: budget **10 522 339 062 bytes (~9,80 GiB)**. На момент preflight свободно 157 275 770 880 bytes (~146,47 GiB). Это estimates, не hard bounds. Temp: `{pre['temporary_directory']}`, один текущий member и растущий staging ZIP; external OCR caches не входят в peak-temp measure. {link(QA/'large_zip_preflight.json')}.

## Ваш сценарий: обычный интерфейс TreeTranslate

Запуск выполняет пользователь в приложении. Откройте текущую рабочую версию через `C:\\TreeTranslate\\run_dev.bat`, выберите ZIP, Chinese→Russian, нужный CPU/GPU/Auto режим, папку результата и обычную кнопку «Перевести». Старый exe/другая копия не гарантирует наличие этих изменений. Перевод через Codex или специальный translation CLI для вашего сценария не требуется.

Source/target и device берутся из GUI; Auto использует существующий runtime, CUDA была available на preflight, fallback CPU сохраняется. Реальное GPU/CPU использование пишется по сегментам. Сохраните выбранные настройки режима, потоков, перевода имён/папок для сравнения скорости. Не меняйте Knowledge/TM во время измеряемого run. GUI использует обычные сохранённые пользовательские базы; Frozen QA использовала изолированные базы, поэтому это не идентичные условия.

**Результат GUI:** выбранная в настройках output folder, либо рядом с source ZIP; фактическое collision-safe имя показывает «Показать результат». Фиксированный `C:\\TreeTranslate\\output\\aw081\\large_corpus` относится к optional CLI helper, не принудительно к GUI.

**Подробные GUI logs:** `C:\\Users\\PC\\AppData\\Local\\CHOPIK Team\\TreeTranslate\\logs\\document_runs\\<run_id>\\`. Общие runtime logs: родительская `logs` folder. Один translation run_id объединяет весь выбранный архив. GUI scan начинается до кнопки «Перевести»: его отдельный scan_run_id и measured scan_seconds связаны в manifest; время ожидания пользователя не выдаётся за translation time. Stage `archive_scan_before_start` хранит scan time отдельно от total run wall time.

Архив может остановиться на первой ошибке: Frozen уже содержит 11 failing documents. Тогда final translated ZIP может отсутствовать; не удаляйте журналы failed run. Это полноценный материал для анализа live reliability, но не полный результат всего corpus. Допуск сейчас NOT READY из-за фактических ошибок, а не из-за отсутствия instrumentation.

## Локальные журналы

Offline, без telemetry/cloud/network reporting. Потоковые JSONL и SQLite WAL/NORMAL, 64 KiB buffers, flush после документа и не реже секунды при новых events. Не хранится весь corpus в RAM. Общие runtime logs не содержат document prose; structured logs используют IDs/SHA, paths, безопасные categories. Frontier содержит только ограниченные technical nominal proposals/candidates, unverified; автоматического добавления в VERIFIED нет. File paths и короткие терминологические candidates являются локальной диагностикой, поэтому папка журналов может содержать такие данные.

Файлы каждого run: `run_manifest.json`, `run_summary.json`, `documents.jsonl`, `stages.jsonl`, `routing.jsonl`, `warnings.jsonl`, `errors.jsonl`, `knowledge_frontier.jsonl`, `resource_samples.jsonl`, `archive_events.jsonl`, `index.sqlite3`, `quality_sample_manifest.json`, `README.txt`.

Для документа: source/member identity и SHA, bytes/type, native/OCR/mixed, pages/regions/confidence, profiler domain/subdomain/context, blocks/segments, protected values, routing/guards/warnings, timing, publication status, output SHA, immutable source check. Archive binding связывает document с final ZIP member. JSONL может хранить ранний staging path; SQLite/sample manifest содержит final archive mapping.

Stage timings: scan/extraction/open/native/OCR/layout/profiler/classification/snapshot/glossary/templates/TM/model/guards/reconstruction/writer/validation/archive append/cleanup. Times inclusive: нельзя суммировать вложенные этапы. Aggregate: wall time, docs/pages per hour, segments/sec, source/output MB per hour, median/p90/p95/max document time. Model fallback и knowledge coverage используют completed eligible segment counts, а не число lookup calls, и не являются semantic quality score.

OCR/source/layout metrics: native/image-only/mixed, pages/regions, low confidence/empty, continuation/page changes, warning/error taxonomy. Automatic missing-content/reading-order/table-quality detection не заменяет reviewer: unavailable/null не выдаётся за zero. Category registry содержит SOURCE_DAMAGED/AMBIGUOUS, extraction/OCR/segmentation/reading order/table, Knowledge/router/template/model, action/negation/condition/object/unit guards, writer/validation/archive/security/IO/OOM/internal error; primary и secondary categories.

Resources: RSS/peak RSS, available RAM, device/CUDA/fallback/OOM; peak VRAM только если существующий allocator initialized, иначе unavailable. CTranslate2 не обязан инициализировать torch allocator, поэтому VRAM может остаться unavailable даже при GPU translation.

## Self-test и стоимость

Crash test через hard exit: завершённые JSONL checkpoints и SQLite integrity сохраняются. Проверены leakage больших private strings, исправность counters, source hashes, final ZIP mapping, fail-open logging errors, deterministic sampling и обычный GUI ZIP run.

Пять paired trials на двух DEV native PDF, alternating order, после GUI wiring: **median overhead {benchmark['overhead_percent']:.2f}%**, aggregate {benchmark['aggregate_overhead_percent']:.2f}%. Цель <5% met. Semantic text/objects и pixel rendering совпадают on/off; raw bytes различаются случайными PDFium trailer IDs, сохранёнными в SHA evidence. Маленький benchmark не прогнозирует полный OCR corpus. {link(Path(gate['logging_benchmark_path']))}.

## Ошибки, recovery и sampling

Production archive fail-fast; автоматических retries/resume нет. Final ZIP публикуется только после validation/CRC/source immutability checks. При обычном исключении временные файлы убираются; cleanup errors записываются. Hard crash может оставить staging/temp files, RUNNING manifest и неполный последний JSONL record; ранее flushed documents остаются. In-flight unfinished stage/document может не иметь финального checkpoint. Повторный GUI запуск — новый run_id и новое collision-safe output имя, не автоматическое продолжение.

Deterministic sample manifest: random, highest model fallback, unknown terms, warnings, OCR-heavy, tables/schematics, major automotive domains, slowest и page-count changes. Source/output/events/routing/warnings/timing связываются через document_id. Это план ручной оценки, не автоматический scorer. Совпадение protected tokens не доказывает правильность numeric relations или читаемость после writer.

## Что передать после своего запуска

1. Итоговый translated ZIP, если он создан.
2. Всю папку `document_runs/<run_id>` этого запуска; можно упаковать её через Проводник.
3. Source ZIP или путь к нему; текущий source уже есть на этом компьютере, повторная загрузка не нужна.
4. Выбранные GUI настройки и наблюдения: зависания, остановки, фактическое время, несколько подозрительных страниц.

На этой машине достаточно абсолютных путей к результату и журналам. После получения будет создан `docs/AW0.81_LARGE_ZIP_RUN_REPORT.md` с фактическими performance/reliability metrics и quality sample. Сейчас такого отчёта фактического большого прогона нет, поскольку он не выполнялся.

Optional CLI только для сравнимого отдельного QA, не ваш основной маршрут: `.\\.venv\\Scripts\\python.exe -X utf8 tools/aw081_large_zip.py --run`. Его output `C:\\TreeTranslate\\output\\aw081\\large_corpus`, logs `C:\\TreeTranslate\\qa\\aw081\\large_corpus\\<run_id>`. Без `--run` helper делает только read-only preflight. **Команда перевода здесь не выполнена.**

| Readiness | Решение |
|---|---|
| Source identity / central-directory security / estimated disk | READY; full input CRC будет при scan |
| Streaming local logging / GUI wiring / sampling / privacy self-test | READY |
| DEV semantic gate / BODY-coolant regression / common pytest | PASS |
| Whole-corpus semantic assurance | NOT READY: Frozen MAJOR/CATA |
| Robust completion of 17k ZIP | NOT READY: 11 observed document failures, fail-fast |
| General writer layout assurance | NOT READY: overlap in unseen diagnostic tables |
| Frozen A independence | FAIL: one exact BODY overlap |
| Full large ZIP execution | NOT STARTED |

Дальнейшие semantic/router/writer fixes из A в этой задаче запрещены пользовательским правилом; A теперь Diagnostic A, потребуется untouched B. UI layout не переделан, installer/NMT/AW0.82/PHASE B/C не добавлены. **STOP после pre-run отчёта.**
'''
    (ROOT/'docs/AW0.81_PHASE_A_CLOSURE_REPORT.md').write_text(phase,'utf8')
    (ROOT/'docs/AW0.81_LARGE_ZIP_PRERUN_REPORT.md').write_text(prerun,'utf8')
    state_path=ROOT/'qa/aw081/work_state.json';shutil.copy2(state_path,QA/'work_state_before_final_report.json');state=read(state_path)
    state.update(status='PHASE_A_DEV_CLOSED_FROZEN_A_FAILED',current_task_status='PRE_RUN_REPORT_COMPLETE_STOPPED',
        completed=False,phase_A='PASS_DEV_SCOPE',level_3='PASS_DEV_REGRESSION',
        final_holdout_A='FAIL; first whole evaluation consumed A; one BODY overlap; now Diagnostic A; no fixes this task',
        latest_accepted_iteration='14_phase_a_closure',knowledge_entries=1505,templates=223,
        tests=dict(tests=1138,failures=0,errors=0,skipped=0,seconds=266.18,
            xml_path=str((QA/'full_pytest_final_gui/junit.xml').relative_to(ROOT)),xml_sha256=file_hash(QA/'full_pytest_final_gui/junit.xml')),
        final_report='docs/AW0.81_PHASE_A_CLOSURE_REPORT.md',pre_run_report='docs/AW0.81_LARGE_ZIP_PRERUN_REPORT.md',
        frozen_A_result=str((F/'final_evaluation.json').relative_to(ROOT)),large_zip_translation_started=False,
        instrumentation='READY_GUI_AND_CLI',large_zip_overall_readiness='NOT_READY',
        next='STOP. User owns any future live GUI run. Future semantic fixes require a new untouched Frozen B.',pending_oem_question=None)
    write(state_path,state)
    write(QA/'final_report_hashes.json',dict(production_unchanged=production_hashes()==frozen['production_hashes'],
        reports={n:file_hash(ROOT/'docs'/n) for n in ('AW0.81_PHASE_A_CLOSURE_REPORT.md','AW0.81_LARGE_ZIP_PRERUN_REPORT.md')},
        evaluation_sha256=file_hash(F/'final_evaluation.json'),large_zip_started=False))
    print('REPORTS_WRITTEN_STOP',g,'structural',len(successful),len(failed),'overlap',len(overlap),flush=True)

if __name__=='__main__':run()
